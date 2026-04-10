#!/usr/bin/env python3
"""
NexusStream — WebSocket Dashboard Client
=========================================
A terminal-based dummy client that connects to /ws/analytics and
prints live metric events with color-coded anomaly alerts.

Usage:
    python scripts/ws_client.py [--url ws://localhost:8001/ws/analytics]

Press Ctrl+C to disconnect.
"""

import asyncio
import json
import sys
import argparse
from datetime import datetime

WS_URL_DEFAULT = "ws://localhost:8001/ws/analytics"

# ANSI colors
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
DIM    = "\033[2m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


async def connect_and_stream(url: str):
    try:
        import websockets
    except ImportError:
        print("Install websockets: pip install websockets")
        sys.exit(1)

    print(f"{BOLD}NexusStream Analytics — Live Dashboard{RESET}")
    print(f"{DIM}Connecting to {url}{RESET}")
    print("─" * 70)

    retry_count = 0
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                retry_count = 0
                print(f"{GREEN}✓ Connected{RESET}")
                print(f"{'Time':<12} {'Device':<16} {'Type':<22} {'Value':>10} {'Avg':>10} {'Status':<10}")
                print("─" * 70)

                async for raw in ws:
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    if event.get("event") == "ping":
                        continue

                    ts_str = event.get("timestamp", "")[:19].replace("T", " ")[-8:]
                    device = event.get("device_id", "?")[-12:]
                    dtype  = event.get("device_type", "?")[:20]
                    value  = event.get("raw_value", 0)
                    avg    = event.get("moving_avg", 0)
                    is_anom = event.get("is_anomaly", False)
                    anom_src = event.get("anomaly_source", "none")

                    if is_anom:
                        color = RED if anom_src == "both" else YELLOW
                        status = f"⚠ ANOMALY ({anom_src})"
                    else:
                        color = CYAN
                        status = "ok"

                    print(
                        f"{DIM}{ts_str}{RESET}  "
                        f"{color}{device:<16}{RESET} "
                        f"{dtype:<22} "
                        f"{value:>10.3f} "
                        f"{avg:>10.3f} "
                        f"{color}{status:<25}{RESET}"
                    )

        except KeyboardInterrupt:
            print(f"\n{DIM}Disconnected by user.{RESET}")
            break
        except Exception as exc:
            retry_count += 1
            wait = min(2 ** retry_count, 30)
            print(f"{RED}Connection lost: {exc}. Reconnecting in {wait}s...{RESET}")
            await asyncio.sleep(wait)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NexusStream WebSocket dashboard client")
    parser.add_argument("--url", default=WS_URL_DEFAULT, help="WebSocket URL")
    args = parser.parse_args()
    asyncio.run(connect_and_stream(args.url))
