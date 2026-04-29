import httpx

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
BASE_URL = 'https://v1.baseball.api-sports.io'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=30)

# Use 2024 season (within free plan range)
LEAGUE_ID = 1
SEASON = 2024

print("=== MLB Games 2024 (Free Plan) ===")

# Try from/to range
resp = client.get(f'{BASE_URL}/games', params={
    'league': LEAGUE_ID,
    'season': SEASON,
    'from': '2024-09-01',
    'to': '2024-09-05'
})
result = resp.json()
print(f'From/To (Sep 1-5): {result.get("results", 0)} games')
if result.get('response'):
    for g in result['response'][:3]:
        print(f"  {g.get('date')}: {g.get('homeTeam', {}).get('name')} vs {g.get('awayTeam', {}).get('name')}")

# Try different date range 
resp = client.get(f'{BASE_URL}/games', params={
    'league': LEAGUE_ID,
    'season': SEASON,
    'from': '2024-07-15',
    'to': '2024-07-20'
})
result = resp.json()
print(f'\nFrom/To (Jul 15-20): {result.get("results", 0)} games')
if result.get('response'):
    for g in result['response'][:3]:
        print(f"  {g.get('date')}: {g.get('homeTeam', {}).get('name')} vs {g.get('awayTeam', {}).get('name')}")

# Get odds for a game!
print("\n=== Getting Odds ===")
if result.get('response'):
    game = result['response'][0]
    game_id = game.get('id')
    print(f'Game ID: {game_id}')
    print(f'Match: {game.get("homeTeam", {}).get("name")} vs {game.get("awayTeam", {}).get("name")}')
    
    # Try odds endpoint
    odds_resp = client.get(f'{BASE_URL}/odds', params={
        'game': game_id
    })
    odds = odds_resp.json()
    print(f'\nOdds Status: {odds_resp.status_code}')
    print(f'Odds Results: {odds.get("results", 0)}')
    
    if odds.get('response'):
        print(f'\nOdds found! {len(odds["response"])} bookmakers:')
        for bm in odds['response'][:3]:
            print(f"  {bm.get('id')}: {bm.get('name')}")
            for market in bm.get('odds', [])[:2]:
                print(f"    {market.get('label')}: {market.get('value')}")

client.close()