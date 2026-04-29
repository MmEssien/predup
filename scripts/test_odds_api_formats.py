import httpx

BASE_URL = "https://api.the-odds-api.com/v4"

print("="*60)
print("  TESTING THE ODDS API FORMATS")
print("="*60)

client = httpx.Client(timeout=15)

# Test different header combinations
test_cases = [
    {"apikey": "dca7069462322213519c88f447526adc"},
    {"api-key": "dca7069462322213519c88f447526adc"},
    {"x-api-key": "dca7069462322213519c88f447526adc"},
]

for headers in test_cases:
    print(f"\nTrying headers: {list(headers.keys())[0]}")
    try:
        resp = client.get(f"{BASE_URL}/sports", headers=headers)
        print(f"  Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"  Response: {resp.text[:150]}")
    except Exception as e:
        print(f"  Error: {e}")

# Try as query param
print("\n\nTrying query parameter...")
try:
    resp = client.get(f"{BASE_URL}/sports", params={"apikey": "dca7069462322213519c88f447526adc"})
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"  SUCCESS! Found sports")
    else:
        print(f"  Response: {resp.text[:150]}")
except Exception as e:
    print(f"  Error: {e}")

# Try combined header + params
print("\n\nTrying header + params combined...")
try:
    resp = client.get(f"{BASE_URL}/sports/baseball_mlb/odds",
                  headers={"apikey": "dca7069462322213519c88f447526adc"},
                  params={"regions": "us", "markets": "h2h"})
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  SUCCESS! Found {len(data)} MLB games")
        if data:
            g = data[0]
            print(f"  {g.get('home_team')} vs {g.get('away_team')}")
            bm = g.get("bookmakers", [])
            if bm:
                for m in bm[0].get("markets", []):
                    if m.get("key") == "h2h":
                        for o in m.get("outcomes", []):
                            print(f"    {o.get('name')}: {o.get('price')}")
    else:
        print(f"  Response: {resp.text[:150]}")
except Exception as e:
    print(f"  Error: {e}")

client.close()