#!/usr/bin/env python3
"""Test OddsPortal adapter"""
import sys
sys.path.insert(0, '/app')

try:
    from src.data.oddsportal_adapter import OddsPortalAdapter
    print("Import successful")
    
    adapter = OddsPortalAdapter()
    print("Testing is_available...")
    result = adapter.is_available()
    print(f"Result: {result}")
    adapter.close()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
