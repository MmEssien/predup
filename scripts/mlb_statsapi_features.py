"""
MLB Real Feature Fetcher
Fetches real features from StatsAPI with caching
"""

import sys
from pathlib import Path
_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")
sys.path.insert(0, str(_root))

import os
import logging
import json
import hashlib
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import httpx
from dotenv import load_dotenv

load_dotenv(_root / ".env")
logger = logging.getLogger(__name__)

CACHE_DIR = _root / "cache"
CACHE_DIR.mkdir(exist_ok=True)

CACHE_TTL = {
    "team_stats": 24 * 3600,    # 24 hours
    "standings": 12 * 3600,      # 12 hours
    "probable_pitchers": 2 * 3600,  # 2 hours
    "schedule": 1 * 3600,        # 1 hour
}


class Cache:
    """Simple file-based cache with TTL"""
    
    @staticmethod
    def _get_path(key: str) -> Path:
        safe_key = hashlib.md5(key.encode()).hexdigest()
        return CACHE_DIR / f"{safe_key}.json"
    
    @staticmethod
    def get(key: str, ttl: int) -> Optional[Dict]:
        path = Cache._get_path(key)
        if not path.exists():
            return None
        
        age = datetime.now().timestamp() - path.stat().st_mtime
        if age > ttl:
            return None
        
        try:
            with open(path) as f:
                return json.load(f)
        except:
            return None
    
    @staticmethod
    def set(key: str, data: Dict):
        path = Cache._get_path(key)
        try:
            with open(path, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")
    
    @staticmethod
    def invalidate(prefix: str = None):
        for f in CACHE_DIR.glob("*.json"):
            if prefix is None or prefix in f.stem:
                f.unlink(missing_ok=True)


class MLBStatsAPIClient:
    """Real StatsAPI client for MLB features with caching"""
    
    def __init__(self, use_cache: bool = True):
        self.base_url = "https://statsapi.mlb.com/api/v1"
        self._client: Optional[httpx.Client] = None
        self.use_cache = use_cache
        self._fallback_used = False
        self._team_stats_cache: Dict = {}
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30)
        return self._client
    
    def close(self):
        if self._client:
            self._client.close()
            self._client = None
    
    @property
    def fallback_used(self) -> bool:
        return self._fallback_used
    
    def reset_fallback_flag(self):
        self._fallback_used = False
    
    def get_todays_games(self) -> List[Dict]:
        """Get today's games with probable pitchers"""
        cache_key = f"schedule_today_{datetime.now().strftime('%Y%m%d')}"
        
        if self.use_cache:
            cached = Cache.get(cache_key, CACHE_TTL["schedule"])
            if cached:
                return cached
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        try:
            resp = self.client.get(
                f"{self.base_url}/schedule",
                params={
                    "sportId": 1,
                    "date": today,
                    "hydrate": "probablePitcher,team"
                }
            )
            resp.raise_for_status()
            data = resp.json()
            
            games = []
            for date_obj in data.get("dates", []):
                for game in date_obj.get("games", []):
                    if game.get("gameType") == "R":
                        games.append(game)
            
            if self.use_cache and games:
                Cache.set(cache_key, games)
            
            return games
        except Exception as e:
            logger.error(f"Get today's games error: {e}")
            return []
    
    def _fetch_all_team_stats(self, season: int = 2024) -> Dict[int, Dict]:
        """Fetch all team hitting stats at once"""
        if self._team_stats_cache.get("_season") == season and self._team_stats_cache.get("_data"):
            return self._team_stats_cache.get("_data", {})
        
        cache_key = f"all_team_stats_{season}"
        
        if self.use_cache:
            cached = Cache.get(cache_key, CACHE_TTL["team_stats"])
            if cached:
                self._team_stats_cache = {"_season": season, "_data": cached}
                return cached
        
        try:
            resp = self.client.get(
                f"{self.base_url}/teams/stats",
                params={
                    "season": season,
                    "group": "hitting",
                    "stats": "season",
                    "sportId": 1
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                team_stats = {}
                
                for split in data.get("stats", [{}])[0].get("splits", []):
                    team = split.get("team", {})
                    team_id = team.get("id")
                    if team_id:
                        team_stats[team_id] = split.get("stat", {})
                
                if self.use_cache:
                    Cache.set(cache_key, team_stats)
                
                self._team_stats_cache = {"_season": season, "_data": team_stats}
                return team_stats
        except Exception as e:
            logger.warning(f"All team stats fetch error: {e}")
        
        return {}
    
    def get_team_stats(self, team_id: int, season: int = 2024) -> Dict:
        """Get team hitting stats for a specific team"""
        all_stats = self._fetch_all_team_stats(season)
        stat = all_stats.get(team_id, {})
        
        if stat:
            return {"stats": [{"splits": [{"stat": stat}]}]}
        return {}
    
    def get_pitcher_stats(self, pitcher_id: int, season: int = 2024) -> Dict:
        """Get pitcher stats"""
        cache_key = f"pitcher_stats_{pitcher_id}_{season}"
        
        if self.use_cache:
            cached = Cache.get(cache_key, CACHE_TTL["probable_pitchers"])
            if cached:
                return cached
        
        try:
            resp = self.client.get(
                f"{self.base_url}/people/{pitcher_id}/stats",
                params={
                    "season": season,
                    "stats": "season",
                    "group": "pitching"
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                if self.use_cache:
                    Cache.set(cache_key, data)
                return data
        except Exception as e:
            logger.warning(f"Pitcher stats error for {pitcher_id}: {e}")
        
        return {}
    
    def get_recent_games(self, team_id: int, days: int = 10) -> List[Dict]:
        """Get team's recent games for form calculation"""
        cache_key = f"recent_games_{team_id}_{days}_{datetime.now().strftime('%Y%m%d')}"
        
        if self.use_cache:
            cached = Cache.get(cache_key, CACHE_TTL["schedule"])
            if cached:
                return cached
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        try:
            resp = self.client.get(
                f"{self.base_url}/schedule",
                params={
                    "sportId": 1,
                    "startDate": start_date.strftime("%Y-%m-%d"),
                    "endDate": end_date.strftime("%Y-%m-%d"),
                    "teamId": team_id
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                games = []
                for date_obj in data.get("dates", []):
                    for game in date_obj.get("games", []):
                        games.append(game)
                
                if self.use_cache and games:
                    Cache.set(cache_key, games)
                
                return games
        except Exception as e:
            logger.warning(f"Recent games error for {team_id}: {e}")
        
        return []


def extract_pitcher_features(pitcher_data: Dict, use_fallback: bool = False) -> Tuple[Dict, bool]:
    """Extract pitcher features from API response
    
    Returns: (features_dict, used_fallback)
    """
    fallback = {
        "era": 4.50,
        "whip": 1.35,
        "k_rate": 0.20,
        "ip": 0
    }
    
    stats = pitcher_data.get("stats", [])
    if not stats:
        return fallback, True
    
    splits = stats[0].get("splits", [])
    if not splits:
        return fallback, True
    
    stat = splits[0].get("stat", {})
    if not stat:
        return fallback, True
    
    ip_str = str(stat.get("inningsPitched", "0"))
    try:
        ip = float(ip_str.split(".")[0]) if "." in ip_str else float(ip_str)
    except:
        ip = 0
    
    so = int(stat.get("strikeOuts", 0) or 0)
    k_rate = so / ip if ip > 0 else 0.20
    
    features = {
        "era": float(stat.get("era")) if stat.get("era") else 4.50,
        "whip": float(stat.get("whip")) if stat.get("whip") else 1.35,
        "k_rate": k_rate,
        "ip": ip
    }
    
    if features["era"] == 0:
        return fallback, True
    
    return features, False


def extract_team_features(team_data: Dict, use_fallback: bool = False) -> Tuple[Dict, bool]:
    """Extract team features from API response
    
    Returns: (features_dict, used_fallback)
    """
    fallback = {
        "ops": 0.750,
        "avg": 0.250,
        "runs": 0,
        "home_runs": 0,
        "hits": 0,
        "strikeouts": 0,
        "walks": 0
    }
    
    try:
        stats = team_data.get("stats", [])
        if not stats:
            return fallback, True
        
        split = stats[0].get("splits", [])
        if not split:
            return fallback, True
        
        stat = split[0].get("stat", {})
        if not stat:
            return fallback, True
        
        features = {
            "ops": float(stat.get("ops")) if stat.get("ops") else 0.750,
            "avg": float(stat.get("avg")) if stat.get("avg") else 0.250,
            "runs": int(stat.get("runs")) if stat.get("runs") else 0,
            "home_runs": int(stat.get("homeRuns")) if stat.get("homeRuns") else 0,
            "hits": int(stat.get("hits")) if stat.get("hits") else 0,
            "strikeouts": int(stat.get("strikeOuts")) if stat.get("strikeOuts") else 0,
            "walks": int(stat.get("walks")) if stat.get("walks") else 0
        }
        
        if features["ops"] == 0:
            return fallback, True
        
        return features, False
    except:
        return fallback, True


def calculate_recent_form(recent_games: List[Dict]) -> float:
    """Calculate recent form from last N games"""
    if not recent_games:
        return 0.50
    
    wins = 0
    total = 0
    
    for game in recent_games[:10]:
        teams = game.get("teams", {})
        home = teams.get("home", {})
        away = teams.get("away", {})
        
        home_score = home.get("score")
        away_score = away.get("score")
        
        if home_score is not None and away_score is not None:
            total += 1
            if home_score > away_score:
                wins += 1
    
    return wins / max(1, total)


def generate_fallback_features() -> Dict:
    """Generate simulated features for fallback"""
    import numpy as np
    np.random.seed(None)
    
    return {
        "home_era": np.random.normal(4.0, 1.0),
        "away_era": np.random.normal(4.0, 1.0),
        "home_whip": np.random.normal(1.35, 0.20),
        "away_whip": np.random.normal(1.35, 0.20),
        "home_k_rate": np.random.normal(0.20, 0.05),
        "away_k_rate": np.random.normal(0.20, 0.05),
        "home_ops": np.random.normal(0.750, 0.080),
        "away_ops": np.random.normal(0.750, 0.080),
        "home_run_diff": np.random.normal(0, 30),
        "away_run_diff": np.random.normal(0, 30),
        "home_recent": np.random.uniform(0.3, 0.7),
        "away_recent": np.random.uniform(0.3, 0.7),
        "home_rest": np.random.choice([0, 1, 2]),
        "away_rest": np.random.choice([0, 1, 2]),
        "home_bullpen": 0.4,
        "away_bullpen": 0.4,
        "home_adv": 1
    }


def get_game_features(client: MLBStatsAPIClient, game: Dict, season: int = 2024) -> Optional[Dict]:
    """Get all features for a game with fallback support
    
    Args:
        client: MLBStatsAPIClient instance
        game: Game dict from schedule API
        season: Season year for stats (2024 for historical, 2025 for current)
    
    Returns:
        Dict with features, or None if game data invalid
    """
    
    try:
        teams = game.get("teams", {})
        home = teams.get("home", {})
        away = teams.get("away", {})
        
        home_team = home.get("team", {})
        away_team = away.get("team", {})
        
        home_id = home_team.get("id")
        away_id = away_team.get("id")
        
        if not home_id or not away_id:
            return None
        
        home_pitcher = home.get("probablePitcher", {})
        away_pitcher = away.get("probablePitcher", {})
        
        home_pitcher_id = home_pitcher.get("id")
        away_pitcher_id = away_pitcher.get("id")
        
        home_pitcher_stats, home_pitcher_fallback = {"era": 4.50, "whip": 1.35, "k_rate": 0.20, "ip": 0}, True
        away_pitcher_stats, away_pitcher_fallback = {"era": 4.50, "whip": 1.35, "k_rate": 0.20, "ip": 0}, True
        
        if home_pitcher_id:
            stats = client.get_pitcher_stats(home_pitcher_id, season)
            if stats:
                home_pitcher_stats, home_pitcher_fallback = extract_pitcher_features(stats)
        
        if away_pitcher_id:
            stats = client.get_pitcher_stats(away_pitcher_id, season)
            if stats:
                away_pitcher_stats, away_pitcher_fallback = extract_pitcher_features(stats)
        
        home_team_stats = client.get_team_stats(home_id, season)
        away_team_stats = client.get_team_stats(away_id, season)
        
        home_team_features, home_team_fallback = extract_team_features(home_team_stats)
        away_team_features, away_team_fallback = extract_team_features(away_team_stats)
        
        home_recent = calculate_recent_form(client.get_recent_games(home_id))
        away_recent = calculate_recent_form(client.get_recent_games(away_id))
        
        any_fallback = home_pitcher_fallback or away_pitcher_fallback or home_team_fallback or away_team_fallback
        client._fallback_used = any_fallback
        
        return {
            "home_team": home_team.get("name"),
            "away_team": away_team.get("name"),
            "home_pitcher": home_pitcher.get("fullName", "TBD"),
            "away_pitcher": away_pitcher.get("fullName", "TBD"),
            "home_era": home_pitcher_stats["era"],
            "away_era": away_pitcher_stats["era"],
            "home_whip": home_pitcher_stats["whip"],
            "away_whip": away_pitcher_stats["whip"],
            "home_k_rate": home_pitcher_stats["k_rate"],
            "away_k_rate": away_pitcher_stats["k_rate"],
            "home_ops": home_team_features["ops"],
            "away_ops": away_team_features["ops"],
            "home_run_diff": home_team_features["runs"] - 400,
            "away_run_diff": away_team_features["runs"] - 400,
            "home_recent": home_recent,
            "away_recent": away_recent,
            "home_rest": 1,
            "away_rest": 1,
            "home_adv": 1,
            "data_source": "simulated" if any_fallback else "statsapi",
            "pitcher_fallback": home_pitcher_fallback or away_pitcher_fallback,
            "team_fallback": home_team_fallback or away_team_fallback
        }
    
    except Exception as e:
        logger.error(f"Get game features error: {e}")
        return None


def features_to_array(features: Dict) -> List[float]:
    """Convert feature dict to model input array"""
    return [
        features["home_era"],
        features["away_era"],
        features["home_whip"],
        features["away_whip"],
        features["home_k_rate"],
        features["away_k_rate"],
        features["home_ops"],
        features["away_ops"],
        features["home_run_diff"],
        features["away_run_diff"],
        features["home_recent"],
        features["away_recent"],
        features["home_rest"],
        features["away_rest"],
        features.get("home_bullpen", 0.4),
        features.get("away_bullpen", 0.4),
        features["home_adv"]
    ]


def test_stats_api():
    """Test the StatsAPI integration"""
    print("="*70)
    print("  STATSAPI INTEGRATION TEST")
    print("="*70)
    
    client = MLBStatsAPIClient(use_cache=False)
    
    print("\n[1] Getting today's games...")
    games = client.get_todays_games()
    print(f"    Found {len(games)} games")
    
    if games:
        print("\n[2] Getting features for first game...")
        features = get_game_features(client, games[0])
        
        if features:
            print(f"\n    {features['home_team']} vs {features['away_team']}")
            print(f"    Data source: {features['data_source']}")
            print(f"\n    Pitchers:")
            print(f"      Home: {features['home_pitcher']} (ERA: {features['home_era']:.2f})")
            print(f"      Away: {features['away_pitcher']} (ERA: {features['away_era']:.2f})")
            print(f"\n    Team Stats:")
            print(f"      Home OPS: {features['home_ops']:.3f}")
            print(f"      Away OPS: {features['away_ops']:.3f}")
            print(f"\n    Form:")
            print(f"      Home recent: {features['home_recent']:.1%}")
            print(f"      Away recent: {features['away_recent']:.1%}")
            
            if features["data_source"] == "simulated":
                print("\n    WARNING: Using SIMULATED data for some features")
                if features.get("pitcher_fallback"):
                    print("      - Pitcher stats are simulated")
                if features.get("team_fallback"):
                    print("      - Team stats are simulated")
        else:
            print("    Could not get features")
    else:
        print("    No games today (might be off-season)")
    
    client.close()
    
    print("\n" + "="*70)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_stats_api()