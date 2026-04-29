import httpx

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
BASE_URL = 'https://v1.baseball.api-sports.io'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=30)

# MLB is league ID 1
LEAGUE_ID = 1
SEASON = 2024

# Get teams in MLB
print("=== MLB Teams ===")
resp = client.get(f'{BASE_URL}/teams', params={'league': LEAGUE_ID, 'season': SEASON})
result = resp.json()
print(f'Teams: {result.get("results", 0)}')

# Find Yankees and Dodgers
teams = result.get('response', [])
yankees = next((t for t in teams if 'Yankees' in t.get('name', '')), None)
dodgers = next((t for t in teams if 'Dodgers' in t.get('name', '')), None)
cubs = next((t for t in teams if 'Cubs' in t.get('name', '')), None)

print(f'Yankees ID: {yankees.get("id") if yankees else "NOT FOUND"}')
print(f'Dodgers ID: {dodgers.get("id") if dodgers else "NOT FOUND"}')
print(f'Cubs ID: {cubs.get("id") if cubs else "NOT FOUND"}')

# Get games with TIMEZONE
print("\n=== MLB Games ===")
resp = client.get(f'{BASE_URL}/games', params={
    'league': LEAGUE_ID,
    'season': SEASON,
    'date': '2024-09-15'
})
result = resp.json()
print(f'Status: {resp.status_code}')
print(f'Results: {result.get("results", 0)}')

# Try with timezone in date
print("\nTrying date with timezone...")
resp = client.get(f'{BASE_URL}/games', params={
    'league': LEAGUE_ID,
    'season': SEASON,
    'date': '2024-09-15',
    'timezone': 'America/New_York'
})
result = resp.json()
print(f'With timezone: {result.get("results", 0)}')

# Try with from/to
print("\nTrying from/to range...")
resp = client.get(f'{BASE_URL}/games', params={
    'league': LEAGUE_ID,
    'season': SEASON,
    'from': '2024-09-01',
    'to': '2024-09-10'
})
result = resp.json()
print(f'From/To: {result.get("results", 0)}')

# Try with just round
print("\nTrying round=Regular Season...")
resp = client.get(f'{BASE_URL}/games', params={
    'league': LEAGUE_ID,
    'season': SEASON,
    'round': 'Regular Season'
})
result = resp.json()
print(f'Regular Season: {result.get("results", 0)}')
if result.get('response'):
    for g in result['response'][:3]:
        print(f"  {g.get('date')}: {g.get('homeTeam', {}).get('name')} vs {g.get('awayTeam', {}).get('name')}")
        
        # Try to get odds for this game
        game_id = g.get('id')
        odds_resp = client.get(f'{BASE_URL}/odds', params={'game': game_id})
        odds = odds_resp.json()
        if odds.get('response'):
            print(f"    Odds found! {len(odds['response'])} bookmakers")
        else:
            print(f"    No odds: {odds.get('message', 'unknown')}")

client.close()