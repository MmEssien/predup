import httpx

print("Testing apiKey format...")
client = httpx.Client(timeout=15)

# Try apiKey (camelCase) as query param
resp = client.get('https://api.the-odds-api.com/v4/sports', params={'apiKey': 'dca7069462322213519c88f447526adc'})
print(f'Status: {resp.status_code}')

if resp.status_code == 200:
    print("SUCCESS!")
    sports = resp.json()
    print(f"Found {len(sports)} sports")
    mlb = [s for s in sports if 'baseball' in s.get('key', '').lower()]
    print(f"MLB keys: {[s.get('key') for s in mlb[:3]]}")
    
    # Try to get odds
    if mlb:
        sport_key = mlb[0].get('key')
        print(f"\nGetting odds for {sport_key}...")
        resp2 = client.get(f'https://api.the-odds-api.com/v4/sports/{sport_key}/odds', 
                        params={'apiKey': 'dca7069462322213519c88f447526adc', 'regions': 'us', 'markets': 'h2h'})
        print(f"Odds status: {resp2.status_code}")
        if resp2.status_code == 200:
            data = resp2.json()
            print(f"Found {len(data)} games")
            if data:
                g = data[0]
                print(f"Game: {g.get('home_team')} vs {g.get('away_team')}")
                bm = g.get('bookmakers', [])
                if bm:
                    print(f"Bookmaker: {bm[0].get('title')}")
                    for m in bm[0].get('markets', []):
                        if m.get('key') == 'h2h':
                            for o in m.get('outcomes', []):
                                print(f"  {o.get('name')}: {o.get('price')}")
        credits = resp2.headers.get('X-odds-api-credits-remaining', 'N/A')
        print(f"Credits: {credits}")
else:
    print(f"Error: {resp.text[:300]}")

client.close()