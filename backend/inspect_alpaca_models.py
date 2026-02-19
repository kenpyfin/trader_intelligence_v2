#!/usr/bin/env python3
"""
Quick script to inspect Alpaca data models for available fields
"""

import sys
import os
sys.path.append('src')

try:
    from alpaca.data.models import Quote, Trade, OptionSnapshot

    print("=== Quote Model Attributes ===")
    for attr in dir(Quote):
        if not attr.startswith('_'):
            print(f"  {attr}")

    print("\n=== Trade Model Attributes ===")
    for attr in dir(Trade):
        if not attr.startswith('_'):
            print(f"  {attr}")

    print("\n=== OptionSnapshot Model Attributes ===")
    for attr in dir(OptionSnapshot):
        if not attr.startswith('_'):
            print(f"  {attr}")

    # Check if these models have annotations
    print("\n=== Quote Annotations ===")
    if hasattr(Quote, '__annotations__'):
        for field, type_info in Quote.__annotations__.items():
            print(f"  {field}: {type_info}")

    print("\n=== Trade Annotations ===")
    if hasattr(Trade, '__annotations__'):
        for field, type_info in Trade.__annotations__.items():
            print(f"  {field}: {type_info}")

    print("\n=== OptionSnapshot Annotations ===")
    if hasattr(OptionSnapshot, '__annotations__'):
        for field, type_info in OptionSnapshot.__annotations__.items():
            print(f"  {field}: {type_info}")

except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure alpaca-py is installed")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()