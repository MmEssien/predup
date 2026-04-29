import httpx
API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=30)

# Try exactly what the API suggests: 2026-04-26 to 2026-04-28
print("Testing suggested dates...")
for date in ['2026-04-26', '2026-04-27', '2026-04-28']:
    resp = client.get('https://v1.baseball.api-sports.io/games', params={'league': 1, 'season': 2026, 'date': date})
    result = resp.json()
    print(f'{date}: {result.get("results", 0)} games')
    if result.get('response'):
        for g in result['response'][:3]:
            print(f'  {g.get("date")}: {g.get("homeTeam", {}).get("name")} vs {g.get("awayTeam", {}).get("name")}')

# Try to get odds for a game
print("\n=== Trying Odds ===")
resp = client.get('https://v1.baseball.api-sports.io/games', params={'league': 1, 'season': 2026, 'date': '2026-04-27'})
result = resp.json()
if result.get('response'):
    game = result['response'][0]
    game_id = game.get('id')
    print(f'Game ID: {game_id}')
    
    odds_resp = client.get('https://v1.baseball.api-sports.io/odds', params={'game': game_id})
    odds = odds_resp.json()
    print(f'Odds status: {odds_resp.status_code}, results: {odds.get("results", 0)}')
    if odds.get('response'):
        for bm in odds['response'][:3]:
            print(f'  {bm.get("name")}')
            if bm.get('odds'):
                for o in bm['odds'][:3]:
                    print(f'    {o.get("label")}: {o.get("value")}')

client.close()