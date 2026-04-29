import httpx

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
BASE_URL = 'https://v1.baseball.api-sports.io'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=30)

# Try 2026 season (current)
dates = ['2026-04-25', '2026-04-26', '2026-04-27']

for date in dates:
    resp = client.get(f'{BASE_URL}/games', params={
        'date': date,
        'league': 1, 
        'season': 2026
    })
    result = resp.json()
    print(f'Date {date}: {result.get("results", 0)} games')
    if result.get('response'):
        game = result['response'][0]
        print(f'  First: {game.get("homeTeam", {}).get("name")} vs {game.get("awayTeam", {}).get("name")}')

# Get games by page
resp = client.get(f'{BASE_URL}/games', params={
    'league': 1, 
    'season': 2026,
    'page': 1
})
result = resp.json()
print(f'\nPage 1: {result.get("results", 0)} games')
if result.get('response'):
    for g in result['response'][:3]:
        print(f'  {g.get("date")}: {g.get("homeTeam", {}).get("name")} vs {g.get("awayTeam", {}).get("name")}')

# Try to get odds for a game
if result.get('response'):
    game = result['response'][0]
    game_id = game.get('id')
    print(f'\nFetching odds for game {game_id}...')
    
    odds_resp = client.get(f'{BASE_URL}/odds', params={
        'game': game_id
    })
    odds_result = odds_resp.json()
    print(f'Odds status: {odds_resp.status_code}')
    print(f'Odds results: {odds_result.get("results", 0)}')
    
    if odds_result.get('response'):
        print(f'Odds sample: {odds_result["response"][0]}')

client.close()