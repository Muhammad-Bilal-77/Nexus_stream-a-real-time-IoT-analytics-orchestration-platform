#!/usr/bin/env python3
"""
NexusStream — Dashboard WebSocket CLI Client
==============================================
Connects to the Dashboard WebSocket endpoint (/ws/dashboard).
Allows testing role-based filtering (viewer vs analyst vs admin).

Usage:
  python scripts/ws_dashboard_client.py --role viewer
  python scripts/ws_dashboard_client.py --role analyst
  python scripts/ws_dashboard_client.py --role admin
"""

import asyncio
import json
import argparse
import sys

try:
    import websockets
    import jwt
except ImportError:
    print("Please install required packages: pip install websockets pyjwt")
    sys.exit(1)


DASHBOARD_WS_URL = "ws://localhost:8002/ws/dashboard"
JWT_SECRET = "nexusstream-dev-jwt-secret-change-in-prod"
JWT_ALG = "HS256"

# ANSI colors
RED    = "\033[91m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
DIM    = "\033[2m"
RESET  = "\033[0m"


def generate_token(role: str) -> str:
    """Generate a valid JWT token for the given role."""
    payload = {
        "sub": f"test_{role}",
        "username": f"{role.capitalize()} User",
        "roles": [role]
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def connect(role: str):
    token = generate_token(role)
    url = f"{DASHBOARD_WS_URL}?token={token}"

    print(f"Connecting to Dashboard WS as {CYAN}{role.upper()}{RESET}...")
    
    try:
        async with websockets.connect(url) as ws:
            print(f"{GREEN}✓ Connected successfully.{RESET}\n")
            print("Listening for realtime metric events (filtered by your role).")
            print("Press Ctrl+C to exit.\n")
            
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                
                if data.get("event") == "ping":
                    continue
                
                # Format based on event type
                is_anomaly = data.get("is_anomaly", False)
                ts = data.get("timestamp", "")[-13:-1]
                
                color = RED if is_anomaly else GREEN
                status = "⚠ ANOMALY" if is_anomaly else "OK"
                
                # Print raw JSON for analyst/admin, simplified for viewer
                print(f"[{ts}] {color}{data.get('device_id')} | {status}{RESET}")
                
                # Show exactly which fields we received to verify RBAC
                fields_received = list(data.keys())
                print(f"  {DIM}Fields received: {', '.join(fields_received)}{RESET}")
                
                if role in ["analyst", "admin"]:
                    val = data.get("raw_value")
                    avg = data.get("moving_avg")
                    print(f"  {DIM}Metric: {val:.2f} (Avg: {avg:.2f}){RESET}")
                    
                if role == "admin":
                    count = data.get("packet_count")
                    print(f"  {DIM}Packet Count: {count}{RESET}")
                
                print("-" * 50)
                
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"{RED}✗ Connection failed: HTTP {e.status_code}{RESET}")
        if e.status_code == 403:
            print("This usually means your token was rejected.")
    except Exception as e:
        print(f"{RED}✗ Error: {e}{RESET}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dashboard WS Client")
    parser.add_argument("--role", choices=["viewer", "analyst", "admin"], default="viewer",
                        help="The RBAC role to simulate (determines event field visibility)")
    args = parser.parse_args()
    
    try:
        asyncio.run(connect(args.role))
    except KeyboardInterrupt:
        print("\nDisconnected.")
