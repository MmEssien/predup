import httpx

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=30)

# Try Premier League
print("Testing football API-Sports...")
resp = client.get('https://v3.football.api-sports.io/fixtures', params={
    'league': 39,
    'date': '2026-04-25'
})
result = resp.json()
print(f'PL Status: {resp.status_code}')
print(f'Results: {result.get("results", 0)}')

# Try Bundesliga
print("\nTesting Bundesliga...")
resp2 = client.get('https://v3.football.api-sports.io/fixtures', params={
    'league': 78,
    'date': '2026-04-25'
})
result2 = resp2.json()
print(f'BL1 Status: {resp2.status_code}')
print(f'Results: {result2.get("results", 0)}')
if result2.get('response'):
    print(f'Sample: {result2["response"][0]}')

# Try baseball again with better query
print("\n\nTrying baseball with from/to dates...")
resp3 = client.get('https://v1.baseball.api-sports.io/games', params={
    'league': 1,
    'season': 2024,
    'from': '2024-09-01',
    'to': '2024-09-10'
})
result3 = resp3.json()
print(f'Baseball 2024-09: {result3.get("results", 0)}')

# Try MLB team games
print("\n\nTrying MLB team (NY Yankees, id=2)...")
resp4 = client.get('https://v1.baseball.api-sports.io/games', params={
    'league': 1,
    'season': 2024,
    'team': 2
})
result4 = resp4.json()
print(f'Yankees games: {result4.get("results", 0)}')
if result4.get('response'):
    for g in result4['response'][:2]:
        print(f'  {g.get("date")}: {g.get("homeTeam", {}).get("name")} vs {g.get("awayTeam", {}).get("name")}')

client.close()