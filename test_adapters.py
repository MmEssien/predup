"""Test API adapters without db initialization"""
import sys
from pathlib import Path

_root = Path(__file__).parent
sys.path.insert(0, str(_root))

# Load env
from dotenv import load_dotenv
load_dotenv(_root / ".env")

# Test Football API
print("=" * 60)
print("TESTING FOOTBALL API")
print("=" * 60)

try:
    from src.data.api_client import FootballAPIClient
    client = FootballAPIClient()
    
    # Get competitions
    comps = client.get_competitions()
    print(f"Competitions found: {len(comps.get('competitions', []))}")
    
    # Try to get today's matches
    from datetime import date, timedelta
    today = date.today().isoformat()
    print(f"\nChecking date: {today}")
    
    # Check next 3 days
    for d in range(3):
        check_date = (date.today() + timedelta(days=d)).isoformat()
        print(f"\n--- Date: {check_date} ---")
        
        total_matches = 0
        for comp in comps.get("competitions", [])[:5]:  # Check first 5 competitions
            code = comp.get("code", "")
            try:
                matches = client.get_matches(competition_code=code, date=check_date)
                match_list = matches.get("matches", [])
                if match_list:
                    print(f"  {code}: {len(match_list)} matches")
                    total_matches += len(match_list)
            except Exception as e:
                print(f"  {code}: Error - {str(e)[:50]}")
        
        print(f"  Total matches on {check_date}: {total_matches}")
    
    client.close()
    
except Exception as e:
    print(f"Football API Error: {e}")

print("\n" + "=" * 60)
print("TESTING NBA API")
print("=" * 60)

try:
    # Use correct class name from nba_client.py
    from src.data.nba_client import NBAApiSportsClient
    client = NBAApiSportsClient()
    
    # Get today's games using the adapter
    from src.data.nba_adapter import NBAAdapter
    adapter = NBAAdapter()
    games = adapter.get_todays_games()
    print(f"NBA today games: {len(games) if games else 0}")
    
    if games:
        for g in games[:3]:
            print(f"  - {g.get('home_team')} vs {g.get('away_team')}")
            
except Exception as e:
    print(f"NBA API Error: {e}")

print("\n" + "=" * 60)
print("TESTING MLB API")
print("=" * 60)

try:
    from src.data.mlb_client import MLBStatsClient
    client = MLBStatsClient()
    
    # Get today's games
    games = client.get_todays_games()
    print(f"MLB today games: {len(games.get('dates', [])) if games else 0}")
    
    if games and games.get("dates"):
        for date_obj in games["dates"][:1]:
            for g in date_obj.get("games", [])[:3]:
                print(f"  - {g.get('teams', {}).get('home', {}).get('team', {}).get('name')} vs "
                      f"{g.get('teams', {}).get('away', {}).get('team', {}).get('name')}")
                      
except Exception as e:
    print(f"MLB API Error: {e}")
