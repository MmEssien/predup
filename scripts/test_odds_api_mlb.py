import httpx
import os
from dotenv import load_dotenv

load_dotenv('PredUp/.env')

api_key = os.getenv('ODDS_API_KEY')
print(f'API Key found: {bool(api_key)}')

# Test The Odds API for MLB
client = httpx.Client(headers={'apikey': api_key}, timeout=15)

# Check sports
try:
    resp = client.get('https://api.the-odds-api.com/v4/sports')
    print(f'Status: {resp.status_code}')
    sports = resp.json()
    
    # Find MLB-related
    mlb = [s for s in sports if 'baseball' in s.get('key', '').lower() or 'mlb' in s.get('key', '').lower()]
    print('\nMLB Sports available:')
    for s in mlb[:5]:
        print(f"  {s.get('key')}: {s.get('title')} - active: {s.get('active')}")
    
    # Try to get MLB odds
    if mlb:
        sport_key = mlb[0]['key']
        print(f'\nFetching odds for {sport_key}...')
        odds_resp = client.get(f'https://api.the-odds-api.com/v4/sports/{sport_key}/odds', 
                               params={'regions': 'us', 'markets': 'h2h'})
        print(f'Odds Status: {odds_resp.status_code}')
        
        if odds_resp.status_code == 200:
            data = odds_resp.json()
            print(f'Games found: {len(data)}')
            if data:
                print(f'Sample: {data[0].get("home_team")} vs {data[0].get("away_team")}')
                # Show odds
                bookmakers = data[0].get('bookmakers', [])
                if bookmakers:
                    bm = bookmakers[0]
                    print(f'  Bookmaker: {bm.get("title")}')
                    for market in bm.get('markets', []):
                        print(f'    Market: {market.get("key")}')
                        for outcome in market.get('outcomes', []):
                            print(f'      {outcome.get("name")}: {outcome.get("price")}')
        
        # Check credits
        remaining = odds_resp.headers.get('X-odds-api-credits-remaining')
        print(f'\nAPI Credits remaining: {remaining}')
        
except Exception as e:
    print(f'Error: {e}')

client.close()