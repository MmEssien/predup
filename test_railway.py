"""Test script for Railway deployment - verifies API connectivity"""
import os
from dotenv import load_dotenv

# Load env
load_dotenv()

print("=" * 60)
print("TESTING APIS ON RAILWAY")
print("=" * 60)

# Check API keys
print("\n[API KEYS]")
print(f"FOOTBALL_DATA_KEY: {'SET' if os.getenv('FOOTBALL_DATA_KEY') else 'MISSING'}")
print(f"API_FOOTBALL_COM_KEY: {'SET' if os.getenv('API_FOOTBALL_COM_KEY') else 'MISSING'}")
print(f"ODDS_API_KEY: {'SET' if os.getenv('ODDS_API_KEY') else 'MISSING'}")
print(f"DATABASE_URL: {'SET' if os.getenv('DATABASE_URL') else 'MISSING'}")

# Test Football API
print("\n[FOOTBALL API]")
try:
    from src.data.api_client import FootballAPIClient
    client = FootballAPIClient()
    comps = client.get_competitions()
    print(f"✅ Football API working! Competitions: {len(comps.get('competitions', []))}")
    client.close()
except Exception as e:
    print(f"❌ Football API failed: {str(e)[:100]}")

# Test NBA API
print("\n[NBA API]")
try:
    from src.data.nba_adapter import NBAAdapter
    adapter = NBAAdapter()
    games = adapter.get_todays_games()
    print(f"✅ NBA API working! Games today: {len(games)}")
except Exception as e:
    print(f"❌ NBA API failed: {str(e)[:100]}")

# Test MLB API
print("\n[MLB API]")
try:
    from src.data.mlb_adapter import MLBAdapter
    adapter = MLBAdapter()
    games = adapter.get_todays_games()
    print(f"✅ MLB API working! Games today: {len(games)}")
except Exception as e:
    print(f"❌ MLB API failed: {str(e)[:100]}")

# Test The Odds API
print("\n[ODDS API]")
try:
    from src.data.unified_odds_engine import UnifiedOddsEngine
    engine = UnifiedOddsEngine()
    # Try to get odds for a sample match
    result = engine.get_odds("football", "Arsenal", "Chelsea")
    if result:
        print(f"✅ Odds API working! Source: {result.get('source')}")
    else:
        print(f"⚠️ Odds API returned no odds (may be no fixtures)")
    engine.close()
except Exception as e:
    print(f"❌ Odds API failed: {str(e)[:100]}")

# Test Database
print("\n[DATABASE]")
try:
    from src.data.connection import DatabaseManager
    db = DatabaseManager.get_instance()
    if db.is_connected():
        print("✅ Database connected!")
        session = db.get_session()
        from src.data.database import SportEvent
        count = session.query(SportEvent).count()
        print(f"   SportEvents in DB: {count}")
        session.close()
    else:
        print("❌ Database not connected")
except Exception as e:
    print(f"❌ Database failed: {str(e)[:100]}")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
