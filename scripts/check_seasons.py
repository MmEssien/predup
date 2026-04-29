import httpx
import os
from datetime import datetime, timedelta

API_KEY = '7f7d0fcbf7fa4d5213acdcf6358d2d95'
BASE_URL = 'https://v1.baseball.api-sports.io'
client = httpx.Client(headers={'x-apisports-key': API_KEY}, timeout=30)

# Get available seasons
resp = client.get('https://v1.baseball.api-sports.io/leagues', params={'id': 1})
data = resp.json()
if data.get('response'):
    league = data['response'][0]
    seasons = league.get('seasons', [])
    print('Available seasons:')
    for s in seasons[-5:]:
        print(f'  {s}')

# Try different dates
dates_to_try = ['2024-09-15', '2024-07-15', '2024-05-15']

for date in dates_to_try:
    resp = client.get('https://v1.baseball.api-sports.io/games', params={
        'date': date,
        'league': 1, 
        'season': 2024
    })
    result = resp.json()
    print(f'Date {date}: {result.get("results", 0)} games')

# Try without specifying date
resp = client.get('https://v1.baseball.api-sports.io/games', params={
    'league': 1, 
    'season': 2024,
    'round': 'Regular Season'
})
result = resp.json()
print(f'\nRegular Season: {result.get("results", 0)} games')
if result.get('response'):
    print(f'First game: {result["response"][0]}')

client.close()