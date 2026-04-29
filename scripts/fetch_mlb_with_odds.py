import httpx
from datetime import datetime

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=60)

print("=== Fetching MLB Games 2024 (Free Plan) ===")

# Get first page of games
all_games = []
page = 1
per_page = 100  # Max typically allowed

while True:
    print(f"Fetching page {page}...")
    resp = client.get('https://v1.baseball.api-sports.io/games', params={
        'league': 1,
        'season': 2024,
        'page': page,
        'limit': per_page
    })
    result = resp.json()
    
    games = result.get('response', [])
    print(f"  Page {page}: {len(games)} games")
    
    if not games:
        break
        
    all_games.extend(games)
    page += 1
    
    if page > 30:  # Safety limit
        print("  Safety limit reached")
        break

print(f"\nTotal games fetched: {len(all_games)}")

# Find a game to get odds for
print("\n=== Sample Games ===")
sample_games = all_games[:5]
for g in sample_games:
    game_time = g.get('date', 'Unknown')
    home = g.get('homeTeam', {}).get('name', 'Unknown')
    away = g.get('awayTeam', {}).get('name', 'Unknown')
    status = g.get('status', {}).get('short', '?')
    print(f"  {game_time}: {home} vs {away} [{status}]")

# Try to get odds for a completed game
print("\n=== Getting Odds for Sample Game ===")
for g in all_games:
    if g.get('status', {}).get('short') == 'FT':  # Full Time - completed game
        game_id = g.get('id')
        home = g.get('homeTeam', {}).get('name')
        away = g.get('awayTeam', {}).get('name')
        
        print(f"Game {game_id}: {home} vs {away}")
        
        # Try odds
        odds_resp = client.get('https://v1.baseball.api-sports.io/odds', params={'game': game_id})
        odds = odds_resp.json()
        
        print(f"  Odds status: {odds_resp.status_code}, results: {odds.get('results', 0)}")
        
        if odds.get('response'):
            print(f"  Found {len(odds['response'])} bookmakers!")
            
            # Show sample odds
            bm = odds['response'][0]
            print(f"  Bookmaker: {bm.get('name')}")
            
            # Try different odds formats
            for odd in bm.get('odds', [])[:5]:
                print(f"    {odd.get('label')}: {odd.get('value')}")
            
            break  # Just get one
        else:
            print(f"  No odds available: {odds.get('errors')}")
        
        break  # Just try first completed game

client.close()