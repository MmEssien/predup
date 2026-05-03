"""Test Supabase PostgreSQL connection"""
from sqlalchemy import create_engine, text
import os

db_url = os.getenv("DATABASE_URL")
print(f"Testing connection to: {db_url[:60]}...")

engine = create_engine(db_url)

try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("✅ Supabase connection successful!")
        print(f"Result: {result.scalar()}")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print("\nTroubleshooting:")
    print("1. Check if Supabase project is active")
    print("2. Verify password in connection string")
    print("3. Try adding ?sslmode=require to URL")
