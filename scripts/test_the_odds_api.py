import httpx

API_KEY = "dca7069462322213519c88f447526adc"
BASE_URL = "https://api.the-odds-api.com/v4"

print("="*60)
print("  TESTING THE ODDS API KEY")
print("="*60)

client = httpx.Client(timeout=15)

# Test 1: Check sports list
print("\n[1] Checking sports list...")
try:
    resp = client.get(f"{BASE_URL}/sports", headers={"apikey": API_KEY})
    print(f"    Status: {resp.status_code}")
    
    if resp.status_code == 401:
        print("    KEY INVALID - 401 Unauthorized")
        error = resp.json()
        print(f"    Message: {error.get('message', 'N/A')}")
    elif resp.status_code == 200:
        sports = resp.json()
        print("    KEY VALID")
        
        # Check for baseball
        mlb = [s for s in sports if "baseball" in s.get("key", "").lower()]
        print(f"    Found {len(mlb)} baseball sports:")
        for s in mlb[:5]:
            print(f"      {s.get('key')}: {s.get('title')}")
        
        # Check credits
        credits = resp.headers.get("X-odds-api-credits-remaining", "N/A")
        used = resp.headers.get("X-odds-api-credits-used", "N/A")
        print(f"    Credits used: {used}, remaining: {credits}")
except Exception as e:
    print(f"    Error: {e}")

# Test 2: Get MLB odds
print("\n[2] Getting MLB odds...")
try:
    resp = client.get(f"{BASE_URL}/sports/baseball_mlb/odds", 
                  headers={"apikey": API_KEY},
                  params={"regions": "us", "markets": "h2h"})
    print(f"    Status: {resp.status_code}")
    
    if resp.status_code == 401:
        print("    KEY INVALID")
    elif resp.status_code == 200:
        data = resp.json()
        print(f"    SUCCESS! Found {len(data)} games")
        
        if data:
            game = data[0]
            print(f"    Game: {game.get('home_team')} vs {game.get('away_team')}")
            
            # Show odds from first bookmaker
            bookmakers = game.get("bookmakers", [])
            if bookmakers:
                bm = bookmakers[0]
                print(f"    Bookmaker: {bm.get('title')}")
                
                for market in bm.get("markets", []):
                    if market.get("key") == "h2h":
                        print(f"    H2H odds:")
                        for outcome in market.get("outcomes", []):
                            print(f"      {outcome.get('name')}: {outcome.get('price')}")
        
        # Check remaining credits
        credits = resp.headers.get("X-odds-api-credits-remaining", "N/A")
        print(f"    Credits remaining: {credits}")
except Exception as e:
    print(f"    Error: {e}")

client.close()

print("\n" + "="*60)