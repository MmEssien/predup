import httpx
import json

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=60)

# Get games
resp = client.get('https://v1.baseball.api-sports.io/games', params={'league': 1, 'season': 2024})
result = resp.json()
games = result.get('response', [])

# Print the raw structure of first game
print("=== Full First Game Object ===")
print(json.dumps(games[0], indent=2))

# Check teams structure
print("\n=== Checking Team Fields ===")
g = games[0]
print(f"All keys in game: {list(g.keys())}")
print(f"Home team: {g.get('homeTeam')}")
print(f"Away team: {g.get('awayTeam')}")
print(f"Teams (alternative): {g.get('teams')}")
print(f"League: {g.get('league')}")

# Try to get odds for multiple games
print("\n=== Trying Odds for Multiple Games ===")
for i, g in enumerate(games[:10]):
    game_id = g.get('id')
    
    odds_resp = client.get('https://v1.baseball.api-sports.io/odds', params={'game': game_id})
    odds = odds_resp.json()
    
    print(f"Game {game_id}: {odds.get('results', 0)} odds")
    
    if odds.get('results', 0) > 0:
        print(f"  Found odds! {len(odds['response'])} bookmakers")
        bm = odds['response'][0]
        print(f"  Bookmaker: {bm.get('name')}")
        print(f"  Odd items: {bm.get('odds', [])}")
        break

client.close()