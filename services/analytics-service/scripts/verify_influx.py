#!/usr/bin/env python3
"""
NexusStream — InfluxDB Query Verification Script
=================================================
Queries the iot_metrics bucket to verify data is being written.

Usage:
    python scripts/verify_influx.py

Prerequisites:
    pip install influxdb-client
    docker-compose up -d
"""

import os
import sys
from datetime import datetime

try:
    from influxdb_client import InfluxDBClient
except ImportError:
    print("Install: pip install influxdb-client")
    sys.exit(1)

INFLUXDB_URL    = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN  = os.getenv("INFLUXDB_TOKEN", "nexusstream-super-secret-influx-token-change-me")
INFLUXDB_ORG    = os.getenv("INFLUXDB_ORG", "nexusstream-org")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "iot_metrics")


def run_query(client, flux_query: str, label: str):
    print(f"\n{'─'*60}")
    print(f"[{label}]")
    print(f"Flux: {flux_query[:100]}{'...' if len(flux_query) > 100 else ''}")

    result = client.query_api().query(flux_query, org=INFLUXDB_ORG)
    rows = []
    for table in result:
        for record in table.records:
            rows.append(record.values)

    if not rows:
        print("  ⚠  No data returned (analytics may not have written yet)")
    else:
        print(f"  ✓ {len(rows)} records returned")
        # Print first 3 rows
        for row in rows[:3]:
            device  = row.get("device_id", "?")
            dtype   = row.get("device_type", "?")
            value   = row.get("_value", "?")
            field   = row.get("_field", "?")
            anom    = row.get("is_anomaly", "?")
            ts      = row.get("_time", "?")
            print(f"    {device} [{dtype}] {field}={value:.4f} anomaly={anom} @ {ts}")

    return rows


def main():
    print(f"NexusStream InfluxDB Verification")
    print(f"  URL:    {INFLUXDB_URL}")
    print(f"  Org:    {INFLUXDB_ORG}")
    print(f"  Bucket: {INFLUXDB_BUCKET}")

    with InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG) as client:

        # 1. Recent metrics (last 5 minutes)
        run_query(client,
            f'from(bucket:"{INFLUXDB_BUCKET}") |> range(start:-5m) '
            f'|> filter(fn:(r) => r._measurement == "device_metrics") '
            f'|> limit(n:5)',
            "Recent metrics (last 5 min)")

        # 2. Moving average per device
        run_query(client,
            f'from(bucket:"{INFLUXDB_BUCKET}") |> range(start:-5m) '
            f'|> filter(fn:(r) => r._field == "moving_avg") '
            f'|> last()',
            "Latest moving_avg per device")

        # 3. Anomalies only
        run_query(client,
            f'from(bucket:"{INFLUXDB_BUCKET}") |> range(start:-5m) '
            f'|> filter(fn:(r) => r.is_anomaly == "true") '
            f'|> limit(n:5)',
            "Recent anomalies")

        # 4. Count per device type
        run_query(client,
            f'from(bucket:"{INFLUXDB_BUCKET}") |> range(start:-5m) '
            f'|> filter(fn:(r) => r._field == "raw_value") '
            f'|> group(columns:["device_type"]) '
            f'|> count()',
            "Packet count by device type")

    print(f"\n{'='*60}")
    print("Verification complete. Check results above.")
    print("If no data appeared, wait 10-20 seconds for the pipeline to write batches,")
    print("then re-run this script.")


if __name__ == "__main__":
    main()
