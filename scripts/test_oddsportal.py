#!/usr/bin/env python3
"""Quick test script"""
import sys
sys.path.insert(0, '/app')

from src.data.oddsportal_adapter import OddsPortalAdapter

adapter = OddsPortalAdapter()
print("Testing OddsPortal is_available...")
try:
    result = adapter.is_available()
    print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

adapter.close()