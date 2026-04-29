import httpx

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=30)

# Try with timezone America/New_York
from datetime import datetime

# Try multiple dates in 2024
test_dates = [
    '2024-04-15',
    '2024-05-15', 
    '2024-06-15',
    '2024-07-15',
    '2024-08-15',
    '2024-09-15',
    '2024-10-01'
]

print("=== Testing Different Dates in 2024 ===")
for date in test_dates:
    resp = client.get('https://v1.baseball.api-sports.io/games', params={
        'league': 1,
        'season': 2024,
        'date': date,
        'timezone': 'America/New_York'
    })
    result = resp.json()
    print(f'{date}: {result.get("results", 0)} games, errors: {result.get("errors")}')

# Try without league but with search
print("\n=== Trying Different Approaches ===")

# Try without specifying league
resp = client.get('https://v1.baseball.api-sports.io/games', params={
    'season': 2024,
    'date': '2024-09-15'
})
print(f'Without league: {resp.json().get("results", 0)} games')

# Try MLB Spring Training (ID 71)
resp = client.get('https://v1.baseball.api-sports.io/games', params={
    'league': 71,
    'season': 2024,
    'from': '2024-02-15',
    'to': '2024-02-28'
})
result = resp.json()
print(f'Spring Training: {result.get("results", 0)} games, errors: {result.get("errors")}')
if result.get('response'):
    for g in result['response'][:2]:
        print(f"  {g.get('date')}: {g.get('homeTeam', {}).get('name')} vs {g.get('awayTeam', {}).get('name')}")

# Try KBO (Korean Baseball) - ID 5
print("\n=== Trying KBO (South Korea) ===")
resp = client.get('https://v1.baseball.api-sports.io/games', params={
    'league': 5,
    'season': 2024,
    'from': '2024-09-01',
    'to': '2024-09-05'
})
result = resp.json()
print(f'KBO: {result.get("results", 0)} games, errors: {result.get("errors")}')
if result.get('response'):
    for g in result['response'][:3]:
        print(f"  {g.get('date')}: {g.get('homeTeam', {}).get('name')} vs {g.get('awayTeam', {}).get('name')}")

# Try NPB (Japan) - ID 2
print("\n=== Trying NPB (Japan) ===")
resp = client.get('https://v1.baseball.api-sports.io/games', params={
    'league': 2,
    'season': 2024,
    'from': '2024-09-01',
    'to': '2024-09-05'
})
result = resp.json()
print(f'NPB: {result.get("results", 0)} games, errors: {result.get("errors")}')
if result.get('response'):
    for g in result['response'][:3]:
        print(f"  {g.get('date')}: {g.get('homeTeam', {}).get('name')} vs {g.get('awayTeam', {}).get('name')}")

client.close()