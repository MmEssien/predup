"""
OddsPortal Adapter - TERTIARY Fallback
===================================
Scrapes odds from OddsPortal using Playwright for JavaScript rendering.

Use as tertiary fallback when OddsAPI is unavailable.
Note: OddsPortal has complex JS rendering - may need updates as site changes.
"""

import logging
from datetime import datetime
from typing import Dict, Optional
import re

logger = logging.getLogger(__name__)


class OddsPortalAdapter:
    """
    OddsPortal scraper using Playwright.
    
    Use as tertiary fallback - works independently of OddsAPI.
    """
    
    BASE_URL = 'https://www.oddsportal.com'
    
    def __init__(self):
        self._browser = None
        self._page = None
        self._pw = None
        
        # Stats
        self._requests = 0
        self._success = 0
        self._failed = 0
    
    def _get_playwright(self):
        if self._pw is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
        return self._pw
    
    def _get_browser(self):
        if self._browser is None:
            pw = self._get_playwright()
            self._browser = pw.chromium.launch(
                headless=True,
                args=['--disable-gpu', '--no-sandbox']
            )
        return self._browser
    
    def _get_page(self):
        if self._page is None:
            browser = self._get_browser()
            self._page = browser.new_page()
            self._page.set_default_timeout(30000)
        return self._page
    
    def is_available(self) -> bool:
        try:
            page = self._get_page()
            page.goto(self.BASE_URL, timeout=15000)
            return True
        except:
            return False
    
    def get_odds(
        self,
        sport: str,
        home_team: str,
        away_team: str,
        league: str = None,
        use_cache: bool = True
    ) -> Optional[Dict]:
        """Scrape odds from OddsPortal."""
        from src.data.odds_cache import get_odds_cache
        cache = get_odds_cache()
        
        cache_key = f"oddsportal_{sport}_{home_team}_{away_team}"
        
        if use_cache:
            cached = cache.get(cache_key, "oddsportal")
            if cached:
                logger.debug(f"[ODDSPORTAL] Cache hit")
                return cached
        
        self._requests += 1
        
        try:
            odds_data = self._search_and_get_odds(home_team, away_team, sport, league)
            
            if odds_data:
                self._success += 1
                cache.set(cache_key, odds_data, "oddsportal")
                logger.info(f"[ODDSPORTAL] SUCCESS: {home_team} vs {away_team}")
            else:
                self._failed += 1
                logger.debug(f"[ODDSPORTAL] Not found: {home_team} vs {away_team}")
            
            return odds_data
            
        except Exception as e:
            self._failed += 1
            logger.warning(f"[ODDSPORTAL] Error: {e}")
            return None
    
    def _search_and_get_odds(self, home: str, away: str, sport: str, league: str) -> Optional[Dict]:
        """Search for match and extract odds"""
        page = self._get_page()
        
        try:
            # Try to navigate using known URL patterns
            slug_home = home.lower().replace(' ', '-')
            slug_away = away.lower().replace(' ', '-')
            
            # Try different URL patterns
            urls_to_try = [
                f'{self.BASE_URL}/search/{slug_home}-vs-{slug_away}/',
            ]
            
            for url in urls_to_try:
                page.goto(url, timeout=30000)
                page.wait_for_timeout(3000)
                
                # Scroll to trigger lazy load
                page.evaluate('window.scrollBy(0, 300)')
                page.wait_for_timeout(1000)
                
                odds = self._parse_current_page(page, home, away)
                if odds:
                    return odds
                
        except Exception as e:
            logger.debug(f"[ODDSPORTAL] Search error: {e}")
        
        return None
    
    def _parse_current_page(self, page, home: str, away: str) -> Optional[Dict]:
        """Parse odds from current page"""
        try:
            # Get page content
            html = page.content()
            
            # Try to find odds using patterns
            # Look for decimal odds (numbers like 1.5, 2.0, 3.5 etc)
            import re
            odds_pattern = re.compile(r'(\d+\.\d+)')
            
            # Search in page text
            text = page.locator('body').inner_text()
            
            # Find all decimal odds
            all_odds = [float(m) for m in odds_pattern.findall(text) 
                      if 1.0 < float(m) < 20.0]
            
            # Remove duplicates
            all_odds = list(dict.fromkeys(all_odds))
            
            if len(all_odds) >= 2:
                return {
                    "sport": self._map_sport(sport),
                    "home_team": home,
                    "away_team": away,
                    "home_odds": all_odds[0],
                    "away_odds": all_odds[1],
                    "draw_odds": None,
                    "overround": None,
                    "timestamp": datetime.now().isoformat(),
                    "source": "oddsportal",
                    "confidence": 0.6,
                    "cache_status": "fresh"
                }
                
        except Exception as e:
            logger.debug(f"[ODDSPORTAL] Parse error: {e}")
        
        return None
    
    def _map_sport(self, sport: str) -> str:
        mapping = {
            "football": "football",
            "nba": "basketball",
            "mlb": "baseball",
        }
        return mapping.get(sport.lower(), "football")
    
    def close(self):
        if self._page:
            self._page.close()
            self._page = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._pw:
            self._pw.stop()
            self._pw = None
    
    def get_stats(self) -> Dict:
        return {
            "requests": self._requests,
            "success": self._success,
            "failed": self._failed,
            "success_rate": self._success / max(self._requests, 1)
        }
    
    def __del__(self):
        self.close()