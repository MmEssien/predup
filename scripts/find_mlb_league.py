import httpx

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
BASE_URL = 'https://v1.baseball.api-sports.io'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=30)

# Get all leagues
resp = client.get(f'{BASE_URL}/leagues')
result = resp.json()
print("=== All Baseball Leagues ===")
print(f'Status: {resp.status_code}, Results: {result.get("results", 0)}')
if result.get('response'):
    for league in result['response']:
        print(f"ID {league.get('id')}: {league.get('name')} ({league.get('country', {}).get('name')})")

# Try MLB specifically  
print("\n=== Trying MLB (id may be different) ===")

# Try with country filter
resp = client.get(f'{BASE_URL}/leagues', params={'country': 'USA'})
us_leagues = resp.json()
print(f"\nUSA Leagues: {us_leagues.get('results', 0)}")
if us_leagues.get('response'):
    for l in us_leagues['response']:
        print(f"  ID {l.get('id')}: {l.get('name')}")

# Try with search
resp = client.get(f'{BASE_URL}/leagues', params={'search': 'Major'})
search = resp.json()
print(f"\nSearch 'Major': {search.get('results', 0)}")
if search.get('response'):
    for l in search['response']:
        print(f"  ID {l.get('id')}: {l.get('name')}")

client.close()