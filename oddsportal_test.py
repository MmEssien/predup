#!/usr/bin/env python3
"""Test OddsPortal scraper"""
import sys
sys.path.insert(0, '/app')

from src.data.oddsportal_adapter import OddsPortalAdapter

print("=== Testing OddsPortal Adapter ===")

adapter = OddsPortalAdapter()

print("Checking availability...")
available = adapter.is_available()
print(f"Available: {available}")

if available:
    print("\nTesting MLB odds scrape...")
    result = adapter.get_odds(
        sport="mlb",
        home_team="Yankees",
        away_team="Red Sox"
    )
    print(f"Result: {result}")

adapter.close()

print("\n=== TEST COMPLETE ===")