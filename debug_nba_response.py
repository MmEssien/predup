"""Debug NBA API-Sports response"""
from dotenv import load_dotenv
load_dotenv()

from src.data.nba_client import NBAApiSportsClient

print("=== Debugging NBA API-Sports ===\n")

client = NBAApiSportsClient()
print(f"API Key: {client.api_key[:10]}...")
print(f"Season: 2024")

# Get games
print("\nFetching NBA games for 2024...")
data = client.get_games(season=2024)

print(f"Results: {data.get('results', 0)}")
print(f"Errors: {data.get('errors', {})}")
print(f"Response type: {type(data.get('response', []))}")

if data.get('response'):
    print(f"Number of games in response: {len(data['response'])}")
    if len(data['response']) > 0:
        sample = data['response'][0]
        print(f"\nSample game keys: {list(sample.keys())}")
        print(f"Sample game: {sample}")
        
        # Check teams structure
        teams = sample.get('teams', {})
        print(f"\nTeams structure: {teams}")
        if 'home' in teams:
            print(f"Home team: {teams['home']}")
        if 'visitors' in teams:
            print(f"Visitor team: {teams['visitors']}")

client.close()

print("\n=== Done ===")
