"""
Centralized Odds Cache Manager
Provides unified caching across all odds sources with configurable TTL
"""

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Any

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# Cache TTLs in minutes
DEFAULT_TTL = {
    "sportsgameodds": 5,      # 2-10 min cache
    "oddsapi": 45,           # 30-60 min cache  
    "oddsportal": 720,      # 6-24 hour cache
}

CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)


class OddsCacheManager:
    """
    Thread-safe centralized cache for odds data.
    Provides configurable TTL per source and disk/memory caching.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern for centralized management"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._memory: Dict[str, tuple] = {}  # key -> (cached_time, data)
        self._stats = {
            'hits': 0,
            'misses': 0,
            'saves': 0,
            'loads': 0,
            'by_source': {}
        }
        logger.info("OddsCacheManager initialized")
    
    def get(self, key: str, source: str = "default") -> Optional[Dict]:
        """Get cached odds if not expired"""
        ttl = self._get_ttl(source)
        
        if key in self._memory:
            cached_time, data = self._memory[key]
            if datetime.now() - cached_time < timedelta(minutes=ttl):
                self._stats['hits'] += 1
                self._increment_stat(source, 'hits')
                logger.debug(f"[CACHE] HIT: {key}")
                return data
            else:
                # Expired - remove from memory
                del self._memory[key]
        
        # Try disk cache
        disk_data = self._load_from_disk(key, source)
        if disk_data:
            self._stats['hits'] += 1
            self._stats['loads'] += 1
            self._increment_stat(source, 'hits')
            # Store in memory for next time
            self._memory[key] = (datetime.now(), disk_data)
            logger.debug(f"[CACHE] DISK HIT: {key}")
            return disk_data
        
        self._stats['misses'] += 1
        self._increment_stat(source, 'misses')
        logger.debug(f"[CACHE] MISS: {key}")
        return None
    
    def set(self, key: str, data: Dict, source: str = "default") -> None:
        """Cache odds data"""
        self._memory[key] = (datetime.now(), data)
        self._stats['saves'] += 1
        self._increment_stat(source, 'saves')
        
        # Save to disk asynchronously
        self._save_to_disk_async(key, data, source)
        
        logger.debug(f"[CACHE] SAVED: {key}")
    
    def _get_ttl(self, source: str) -> int:
        """Get TTL for source"""
        return DEFAULT_TTL.get(source, 10)
    
    def _increment_stat(self, source: str, stat: str) -> None:
        """Increment stats by source"""
        if source not in self._stats['by_source']:
            self._stats['by_source'][source] = {'hits': 0, 'misses': 0, 'saves': 0}
        if stat not in self._stats['by_source'][source]:
            self._stats['by_source'][source][stat] = 0
        self._stats['by_source'][source][stat] += 1
    
    def _get_cache_path(self, key: str, source: str) -> Path:
        """Get cache file path"""
        safe_key = key.replace('/', '_').replace(' ', '_')[:50]
        return CACHE_DIR / f"odds_{source}_{safe_key}.json"
    
    def _save_to_disk_async(self, key: str, data: Dict, source: str) -> None:
        """Save to disk (async wrapper)"""
        path = self._get_cache_path(key, source)
        try:
            with open(path, 'w') as f:
                json.dump({
                    'data': data,
                    'cached_at': datetime.now().isoformat(),
                    'source': source
                }, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"[CACHE] Disk save failed: {e}")
    
    def _load_from_disk(self, key: str, source: str) -> Optional[Dict]:
        """Load from disk cache"""
        path = self._get_cache_path(key, source)
        if not path.exists():
            return None
        
        try:
            with open(path, 'r') as f:
                cache_data = json.load(f)
            
            cached_at = datetime.fromisoformat(cache_data.get('cached_at', datetime.now().isoformat()))
            ttl = self._get_ttl(source)
            
            if datetime.now() - cached_at < timedelta(minutes=ttl):
                return cache_data.get('data')
        except Exception as e:
            logger.warning(f"[CACHE] Disk load failed: {e}")
        
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self._stats['hits'] + self._stats['misses']
        hit_rate = self._stats['hits'] / total if total > 0 else 0
        
        return {
            'hits': self._stats['hits'],
            'misses': self._stats['misses'],
            'saves': self._stats['saves'],
            'loads': self._stats['loads'],
            'hit_rate': hit_rate,
            'by_source': self._stats['by_source']
        }
    
    def clear(self, source: str = None) -> None:
        """Clear cache"""
        if source:
            # Clear by source
            keys_to_remove = [k for k in self._memory.keys() if k.startswith(source)]
            for k in keys_to_remove:
                del self._memory[k]
            logger.info(f"[CACHE] Cleared {source}")
        else:
            self._memory.clear()
            logger.info("[CACHE] Cleared all")


# Global singleton instance
_odds_cache = OddsCacheManager()


def get_odds_cache() -> OddsCacheManager:
    """Get global cache instance"""
    return _odds_cache