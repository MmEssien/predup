"""Fix NBA get_games method"""
from dotenv import load_dotenv
load_dotenv()

import sys
sys.path.insert(0, r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")

# Read the file
with open("src/data/nba_client.py", "r") as f:
    content = f.read()

# Find and replace the get_games method
old = '''    def get_games(self, date: Optional[str] = None, league: int = 12, season: int = None) -> Dict:
        """Get NBA games"""
        if season is None:
            season = get_current_nba_season()
        
        params = {"season": season, "league": league}
        if date:
            params["date"] = date
        
        return self._make_request(
            "/games",
            params=params,
            cache_key=f"games_{date or 'today'}",
            cache_ttl=self.CACHE_TTL["fixtures"]
        )'''

new = '''    def get_games(self, date: Optional[str] = None, season: int = None) -> Dict:
        """Get NBA games"""
        if season is None:
            season = get_current_nba_season()
        
        params = {"season": season}
        if date:
            params["date"] = date
        
        # Bypass cache - make direct request
        url = f"{self.BASE_URL}/games"
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()'''

if old in content:
    content = content.replace(old, new)
    with open("src/data/nba_client.py", "w") as f:
        f.write(content)
    print("Fixed get_games method!")
else:
    print("Could not find exact match")
    # Try to find similar text
    if "def get_games" in content:
        print("Found get_games method, but text doesn't match exactly")
        # Print the actual text
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "def get_games" in line:
                print(f"Line {i}: {repr(lines[i:i+15])}")
                break
