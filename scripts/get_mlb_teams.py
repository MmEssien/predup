import httpx
import os

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
BASE_URL = 'https://v1.baseball.api-sports.io'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=30)

print("=== MLB Team and Game Fetch ===")

# Get teams
resp = client.get(f'{BASE_URL}/teams', params={'league': 1, 'season': 2024})
result = resp.json()
print(f'\nTeams Status: {resp.status_code}, Results: {result.get("results", 0)}')
if result.get('response'):
    teams = result['response']
    print(f'Found {len(teams)} teams')
    # Print first 5
    for t in teams[:5]:
        print(f"  ID {t.get('id')}: {t.get('name')}")
    
    # Find a few well-known teams
    yankees = [t for t in teams if 'Yankees' in t.get('name', '')]
    dodgers = [t for t in teams if 'Dodgers' in t.get('name', '')]
    cubs = [t for t in teams if 'Cubs' in t.get('name', '')]
    
    print(f'\nYankees: {yankees}')
    print(f'Dodgers: {dodgers}')
    print(f'Cubs: {cubs}')

# Get games for a specific team in regular season
team_id = 2  # Yankees
resp = client.get(f'{BASE_URL}/games', params={
    'league': 1,
    'season': 2024,
    'team': team_id,
    'page': 1
})
result = resp.json()
print(f'\n\nYankees Games: {result.get("results", 0)}')
if result.get('response'):
    for g in result['response'][:5]:
        print(f"  {g.get('date')}: Home={g.get('homeTeam')}, Away={g.get('awayTeam')}")

# Try to get odds
print("\n\n=== Trying Odds ===")
if result.get('response'):
    game = result['response'][0]
    game_id = game.get('id')
    print(f'Getting odds for game {game_id}...')
    
    # Try different endpoints
    odds_resp = client.get(f'{BASE_URL}/odds', params={'game': game_id})
    print(f'Odds endpoint: {odds_resp.status_code}')
    if odds_resp.status_code == 200:
        odds = odds_resp.json()
        print(f'Odds results: {odds.get("results", 0)}')
        if odds.get('response'):
            print(f'Sample odds: {str(odds["response"][0])[:500]}')

client.close()