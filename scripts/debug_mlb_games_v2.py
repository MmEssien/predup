import httpx

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
BASE_URL = 'https://v1.baseball.api-sports.io'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=30)

# Use 2026 season (marked as current)
LEAGUE_ID = 1
SEASON = 2026

print("=== MLB Games 2026 ===")

# Check what date format works
dates = ['2026-04-25', '2026-04-26']

for date in dates:
    resp = client.get(f'{BASE_URL}/games', params={
        'league': LEAGUE_ID,
        'season': SEASON,
        'date': date
    })
    result = resp.json()
    print(f'{date}: {result.get("results", 0)} games')
    
if result.get('results', 0) == 0:
    # Try all possible params
    print("\n=== Trying ALL parameters ===")
    
    params_list = [
        {'league': LEAGUE_ID, 'season': SEASON, 'team': 25},  # Yankees
        {'league': LEAGUE_ID, 'season': SEASON, 'team': 18},  # Dodgers
        {'league': LEAGUE_ID, 'season': SEASON, 'page': 1},
        {'league': LEAGUE_ID, 'season': SEASON, 'page': 2},
        {'league': LEAGUE_ID, 'season': SEASON, 'status': '1'},  # TBD?
        {'league': LEAGUE_ID},
    ]
    
    for params in params_list:
        resp = client.get(f'{BASE_URL}/games', params=params)
        result = resp.json()
        print(f'{params}: {result.get("results", 0)} games')

# Check errors in response
print("\n=== Checking response details ===")
resp = client.get(f'{BASE_URL}/games', params={'league': LEAGUE_ID, 'season': SEASON})
result = resp.json()
print(f'Parameters sent: {result.get("parameters")}')
print(f'Errors: {result.get("errors")}')
print(f'Paging: {result.get("paging")}')

# Check odds endpoint
print("\n=== Odds endpoint test ===")

# First try to find a game with different approach - status lookup
print("Trying status values...")
for status in ['0', '1', '2', '3', 'NS', 'LIVE', 'FINISH', 'POSTPONE']:
    resp = client.get(f'{BASE_URL}/games', params={
        'league': LEAGUE_ID,
        'season': SEASON,
        'status': status
    })
    result = resp.json()
    if result.get('results', 0) > 0:
        print(f'  Status {status}: {result.get("results")} games')

# Try with search
print("\nTrying team search...")
resp = client.get(f'{BASE_URL}/games', params={
    'league': LEAGUE_ID,
    'season': SEASON,
    'search': 'Yankees'
})
result = resp.json()
print(f'  Search Yankees: {result.get("results")} games')
if result.get('response'):
    print(f'    {result["response"][0]}')

client.close()