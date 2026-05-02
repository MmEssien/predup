"""Check what fixtures are available in the free plan date range"""
from dotenv import load_dotenv
load_dotenv()

from src.data.api_football_client import ApiFootballClient

print("Checking available fixtures (May 1-3, 2026)...")
client = ApiFootballClient()

# Check all dates in allowed range
dates = ['2026-05-01', '2026-05-02', '2026-05-03']

for d in dates:
    print(f"\n=== Date: {d} ===")
    data = client.get_fixtures(date=d)
    
    if data.get('errors'):
        print(f"Errors: {data['errors']}")
        continue
    
    results = data.get('results', 0)
    print(f"Total fixtures: {results}")
    
    if results > 0:
        leagues_found = {}
        for item in data.get('response', []):
            league_name = item.get('league', {}).get('name', 'Unknown')
            league_id = item.get('league', {}).get('id', 0)
            country = item.get('league', {}).get('country', 'Unknown')
            
            key = f"{league_name} (ID: {league_id})"
            if key not in leagues_found:
                leagues_found[key] = {
                    'country': country,
                    'count': 0,
                    'matches': []
                }
            leagues_found[key]['count'] += 1
            
            home = item.get('teams', {}).get('home', {}).get('name', '')
            away = item.get('teams', {}).get('away', {}).get('name', '')
            leagues_found[key]['matches'].append(f"{home} vs {away}")
        
        print(f"\nLeagues with fixtures:")
        for league, info in leagues_found.items():
            print(f"  {league} [{info['country']}]: {info['count']} fixtures")
            for match in info['matches'][:3]:  # Show first 3 matches
                print(f"    - {match}")

client.close()
print("\nDone!")
