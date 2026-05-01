import os
os.environ['DATABASE_URL'] = 'sqlite:///predup.db'

from src.data.api_client import FootballAPIClient
from datetime import datetime, timedelta

print("=== Testing Football API ===")
client = FootballAPIClient()
try:
    comps = client.get_competitions()
    print(f"Competitions: {len(comps.get('competitions', []))}")
    
    now = datetime.utcnow()
    dates = [now.date() + timedelta(days=d) for d in range(0, 3)]
    
    total_matches = 0
    for query_date in dates:
        for comp in comps.get('competitions', [])[:6]:
            code = comp.get('code', '')
            if code not in ['PL', 'BL1', 'FL1', 'PD', 'SA', 'EL']:
                continue
            try:
                matches = client.get_matches(competition_code=code, date=query_date.isoformat())
                match_list = matches.get('matches', [])
                scheduled = [m for m in match_list if m.get('status') in ['SCHEDULED', 'TIMED']]
                total_matches += len(scheduled)
                if scheduled:
                    print(f"{code} {query_date}: {len(scheduled)} fixtures")
            except Exception as e:
                print(f"Error {code}: {e}")
    
    print(f"\nTotal fixtures: {total_matches}")
    client.close()
except Exception as e:
    print(f"Error: {e}")

print("\n=== Testing NBA Adapter ===")
try:
    from src.data.nba_adapter import NBAAdapter
    adapter = NBAAdapter()
    games = adapter.get_todays_games()
    print(f"NBA today's games: {len(games)}")
except Exception as e:
    print(f"NBA Error: {e}")

print("\n=== Testing MLB Adapter ===")
try:
    from src.data.mlb_adapter import MLBAdapter
    adapter = MLBAdapter()
    games = adapter.get_todays_games()
    print(f"MLB today's games: {len(games)}")
except Exception as e:
    print(f"MLB Error: {e}")