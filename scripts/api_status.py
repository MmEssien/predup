import httpx

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=30)

# The free plan gives games but NO betting odds
# We have two options:
# 1. Use The Odds API (different provider, may have different key)
# 2. Build our own model to generate realistic odds

# Let's document what we have and create the integration properly

print("="*60)
print("  API-SPORTS MLB INTEGRATION STATUS")
print("="*60)

# We CAN get games
resp = client.get('https://v1.baseball.api-sports.io/games', params={'league': 1, 'season': 2024, 'page': 1})
games = resp.json()['response']
print(f"\nGames available: {len(games)}")
print(f"  Can fetch: YES")
print(f"  Data includes: date, teams, scores (hits, errors, innings, total)")

# But odds endpoint requires paid plan
test_odds = client.get('https://v1.baseball.api-sports.io/odds', params={'game': 152753})
print(f"\nOdds available: NO")
print(f"  Status: {test_odds.status_code}")
print(f"  Results: {test_odds.json().get('results', 0)}")
print(f"  Note: Odds are only available on paid plans")

# Summary
print("\n" + "="*60)
print("  INTEGRATION OPTIONS")
print("="*60)
print("""
1. API-SPORTS (current key):
   - Games: YES (2927 games in 2024)
   - Teams: YES
   - Scores: YES  
   - Odds: NO

2. THE ODDS API (different service):
   - Has betting odds
   - Key in .env may be invalid

3. GENERATE REALISTIC ODDS:
   - Use our RealisticMarketOdds model
   - Based on true probability + vig + bias + noise
   - Already implemented in mlb_closed_loop_v2.py

RECOMMENDATION: Use option 3 for now (realistic simulation)
Get option 1 working with real games/teams/scores
""")

client.close()