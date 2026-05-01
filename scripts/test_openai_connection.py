#!/usr/bin/env python3
"""Test Gemini connection (same model listing as backend /api/gpt-models)."""
import os
import sys

# Load .env from project root
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(root, ".env")
if os.path.isfile(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if v.startswith('"') and v.endswith('"'):
                    v = v[1:-1]
                elif v.startswith("'") and v.endswith("'"):
                    v = v[1:-1]
                os.environ.setdefault(k, v)

try:
    import requests
except ImportError:
    print("Error: requests not installed. Run: pip install requests")
    sys.exit(1)

api_key = os.getenv("GEMINI_API_KEY")
url = "https://generativelanguage.googleapis.com/v1beta/models"

def main():
    print(f"GEMINI_API_KEY: {'(set)' if api_key else '(not set)'}")
    if not api_key:
        print("FAIL: GEMINI_API_KEY is not set")
        sys.exit(1)
    print(f"GET {url}")
    try:
        r = requests.get(
            url,
            params={"key": api_key},
            timeout=15,
        )
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            models = data.get("models", [])
            print(f"OK: Connection successful. Models listed: {len(models)}")
            if models:
                names = [m.get("name", "?") for m in models[:5]]
                print(f"Sample: {names}")
            sys.exit(0)
        print(f"Response: {r.text[:500]}")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"FAIL: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
