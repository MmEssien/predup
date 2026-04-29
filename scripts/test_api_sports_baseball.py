import httpx
import os
from datetime import datetime, timedelta

API_KEY = "7f7d0fcbf7fa4d5213acdcf6358d2d95"
BASE_URL = "https://v1.baseball.api-sports.io"

client = httpx.Client(
    headers={"x-apisports-key": API_KEY},
    timeout=30
)

# Test endpoints
print("="*60)
print("  API-SPORTS BASEBALL (MLB) TEST")
print("="*60)

# 1. Check leagues
try:
    resp = client.get(f"{BASE_URL}/leagues", params={"id": 1})
    print(f"\nLeagues Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"Response: {str(data)[:500]}")
    else:
        print(f"Error: {resp.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

# 2. Try games/fixtures
try:
    today = datetime.now().strftime("%Y-%m-%d")
    resp = client.get(f"{BASE_URL}/games", params={
        "date": today,
        "league": 1,
        "season": 2024
    })
    print(f"\nGames Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"Games found: {data.get('results', 0)}")
        if data.get('response'):
            for game in data['response'][:2]:
                print(f"  {game.get('date')}: {game.get('homeTeam', {}).get('name')} vs {game.get('awayTeam', {}).get('name')}")
    else:
        print(f"Error: {resp.text[:300]}")
except Exception as e:
    print(f"Error: {e}")

# 3. Try to get odds for a game
try:
    # First get some games
    resp = client.get(f"{BASE_URL}/games", params={
        "date": today,
        "league": 1, 
        "season": 2024
    })
    if resp.status_code == 200:
        data = resp.json()
        if data.get('response'):
            game_id = data['response'][0].get('id')
            print(f"\nFetching odds for game {game_id}...")
            
            odds_resp = client.get(f"{BASE_URL}/odds", params={
                "game": game_id,
                "bookmaker": 1
            })
            print(f"Odds Status: {odds_resp.status_code}")
            if odds_resp.status_code == 200:
                odds_data = odds_resp.json()
                print(f"Odds Response: {str(odds_data)[:500]}")
            else:
                print(f"Error: {odds_resp.text[:300]}")
except Exception as e:
    print(f"Error: {e}")

# 4. Try /fixtures/odds endpoint
try:
    resp = client.get(f"{BASE_URL}/fixtures/odds", params={
        "date": today,
        "league": 1,
        "season": 2024
    })
    print(f"\nFixtures/Odds Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"Results: {data.get('results', 0)}")
        if data.get('response'):
            print(f"Sample: {str(data['response'][0])[:500]}")
    else:
        print(f"Error: {resp.text[:300]}")
except Exception as e:
    print(f"Error: {e}")

client.close()