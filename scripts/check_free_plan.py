import httpx

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=30)

# Let's see what the free plan ACTUALLY gives us - no date constraints
print("=== Testing without date constraints ===")
resp = client.get('https://v1.baseball.api-sports.io/games', params={
    'league': 1,
    'season': 2024
})
result = resp.json()
print(f'Status: {resp.status_code}')
print(f'Results: {result.get("results", 0)}')
print(f'Paging: {result.get("paging")}')
print(f'Errors: {result.get("errors")}')
print(f'Parameters: {result.get("parameters")}')

# Try with season 2022
print("\n=== Testing season 2022 ===")
resp2 = client.get('https://v1.baseball.api-sports.io/games', params={
    'league': 1,
    'season': 2022
})
result2 = resp2.json()
print(f'2022 Results: {result2.get("results", 0)}')
print(f'2022 Errors: {result2.get("errors")}')

# Try season 2023
print("\n=== Testing season 2023 ===")
resp3 = client.get('https://v1.baseball.api-sports.io/games', params={
    'league': 1,
    'season': 2023
})
result3 = resp3.json()
print(f'2023 Results: {result3.get("results", 0)}')
print(f'2023 Errors: {result3.get("errors")}')

# Try different endpoint - fixtures instead of games
print("\n=== Testing /fixtures endpoint ===")
resp4 = client.get('https://v1.baseball.api-sports.io/fixtures', params={
    'league': 1,
    'season': 2024
})
result4 = resp4.json()
print(f'Fixtures 2024: {result4.get("results", 0)}')
print(f'Errors: {result4.get("errors")}')

# See if there's a way to get predictions/odds without games
print("\n=== Checking available endpoints ===")
endpoints_to_try = [
    '/predictions',
    '/h2h',
    '/statistics',
    '/players',
    '/standings'
]

for endpoint in endpoints_to_try:
    try:
        resp = client.get(f'https://v1.baseball.api-sports.io{endpoint}', params={'league': 1, 'season': 2024, 'team': 25})
        result = resp.json()
        print(f'{endpoint}: {result.get("results", 0)} results, errors: {result.get("errors")}')
    except Exception as e:
        print(f'{endpoint}: ERROR - {e}')

client.close()