"""ESPN Adapter - Free real-time NBA/MLB fixtures (no API key needed)"""
import httpx
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class ESPNAdapter:
    """ESPN API adapter for real-time NBA/MLB fixtures"""
    
    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"
    
    def __init__(self):
        self._client: Optional[httpx.Client] = None
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30)
        return self._client
    
    def close(self):
        if self._client:
            self._client.close()
            self._client = None
    
    def get_fixtures(self, sport: str, days_ahead: int = 3) -> List[Dict]:
        """
        Get fixtures for sport (basketball/nba or baseball/mlb)
        Returns today's games + next days_ahead days
        """
        sport_path = f"{sport}/scoreboard"
        url = f"{self.BASE_URL}/{sport_path}"
        
        # Calculate date range
        start_date = datetime.now()
        end_date = start_date + timedelta(days=days_ahead)
        
        # ESPN uses YYYYMMDD format
        dates = start_date.strftime("%Y%m%d")
        
        params = {"dates": dates}
        
        try:
            response = self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            fixtures = self._parse_scoreboard(data, sport)
            return fixtures
            
        except Exception as e:
            logger.error(f"ESPN API error for {sport}: {e}")
            return []
    
    def _parse_scoreboard(self, data: Dict, sport: str) -> List[Dict]:
        """Parse ESPN scoreboard response"""
        fixtures = []
        
        events = data.get("events", [])
        
        for event in events:
            try:
                # Get competitors (teams)
                competitions = event.get("competitions", [])
                if not competitions:
                    continue
                
                comp = competitions[0]
                competitors = comp.get("competitors", [])
                
                if len(competitors) < 2:
                    continue
                
                # Find home and away teams
                home = None
                away = None
                
                for c in competitors:
                    team_data = c.get("team", {})
                    if c.get("homeAway") == "home":
                        home = team_data
                    else:
                        away = team_data
                
                if not home or not away:
                    continue
                
                # Get scores if available
                home_score = 0
                away_score = 0
                if "score" in competitors[0]:
                    home_score = competitors[0].get("score", 0)
                    away_score = competitors[1].get("score", 0)
                
                fixtures.append({
                    "fixture_id": event.get("id", ""),
                    "home_team": home.get("displayName", home.get("name", "")),
                    "away_team": away.get("displayName", away.get("name", "")),
                    "home_team_short": home.get("abbreviation", ""),
                    "away_team_short": away.get("abbreviation", ""),
                    "start_time": event.get("date", ""),
                    "status": event.get("status", {}).get("type", {}).get("state", "SCHEDULED"),
                    "home_score": home_score,
                    "away_score": away_score,
                    "league": "NBA" if "nba" in sport else "MLB",
                    "sport": "nba" if "nba" in sport else "mlb"
                })
                
            except Exception as e:
                logger.warning(f"Error parsing event: {e}")
                continue
        
        return fixtures
    
    def get_nba_fixtures(self, days_ahead: int = 3) -> List[Dict]:
        """Get NBA fixtures"""
        return self.get_fixtures("basketball/nba", days_ahead)
    
    def get_mlb_fixtures(self, days_ahead: int = 3) -> List[Dict]:
        """Get MLB fixtures"""
        return self.get_fixtures("baseball/mlb", days_ahead)


# Test the adapter
if __name__ == "__main__":
    print("=== Testing ESPN Adapter (Real-Time 2026 Fixtures) ===\n")
    
    adapter = ESPNAdapter()
    
    # Test NBA
    print("1. NBA Fixtures (2026):")
    nba_games = adapter.get_nba_fixtures()
    print(f"   Found: {len(nba_games)} games")
    
    if nba_games:
        print("   Sample games:")
        for g in nba_games[:3]:
            print(f"   - {g['away_team']} @ {g['home_team']}")
            print(f"     Time: {g['start_time']}, Status: {g['status']}")
    
    # Test MLB
    print("\n2. MLB Fixtures (2026):")
    mlb_games = adapter.get_mlb_fixtures()
    print(f"   Found: {len(mlb_games)} games")
    
    if mlb_games:
        print("   Sample games:")
        for g in mlb_games[:3]:
            print(f"   - {g['away_team']} @ {g['home_team']}")
            print(f"     Time: {g['start_time']}, Status: {g['status']}")
    
    adapter.close()
    print("\n[COMPLETE]")
