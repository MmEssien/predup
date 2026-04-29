import httpx

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=60)

print("=== Fetching MLB Games 2024 ===")

# Get ALL games (no pagination params)
resp = client.get('https://v1.baseball.api-sports.io/games', params={
    'league': 1,
    'season': 2024
})
result = resp.json()

print(f'Status: {resp.status_code}')
print(f'Results: {result.get("results", 0)}')
print(f'Type: {type(result.get("response"))}')
print(f'Response length: {len(result.get("response", [])) if result.get("response") else 0}')

# Just get the first 10 directly
games = result.get('response', [])
print(f'\nTotal games: {len(games)}')

if games:
    print(f'\n=== First 5 Games ===')
    for g in games[:5]:
        game_time = g.get('date', 'Unknown')
        home = g.get('homeTeam', {}).get('name', 'Unknown')
        away = g.get('awayTeam', {}).get('name', 'Unknown')
        status = g.get('status', {}).get('short', '?')
        game_id = g.get('id')
        print(f"  [{game_id}] {game_time}: {home} vs {away} [{status}]")

    # Find completed games (FT = Full Time)
    print('\n=== Finding Completed Games ===')
    completed = [g for g in games if g.get('status', {}).get('short') == 'FT']
    print(f'Completed games: {len(completed)}')
    
    if completed:
        # Get odds for first completed game
        g = completed[0]
        game_id = g.get('id')
        home = g.get('homeTeam', {}).get('name')
        away = g.get('awayTeam', {}).get('name')
        
        print(f'\n=== Getting Odds for Game {game_id}: {home} vs {away} ===')
        
        odds_resp = client.get('https://v1.baseball.api-sports.io/odds', params={'game': game_id})
        print(f'Odds status: {odds_resp.status_code}')
        
        odds = odds_resp.json()
        print(f'Odds results: {odds.get("results", 0)}')
        print(f'Odds errors: {odds.get("errors")}')
        
        if odds.get('response'):
            print(f'\nFound {len(odds["response"])} bookmakers:')
            for bm in odds['response'][:5]:
                print(f'  {bm.get("name")}')
                # Show some odds
                for o in bm.get('odds', [])[:3]:
                    print(f'    {o.get("label")}: {o.get("value")}')

client.close()