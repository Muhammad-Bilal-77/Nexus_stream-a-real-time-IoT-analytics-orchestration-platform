"""
Integration Test — End-to-End Pipeline Verification
=====================================================
Tests the full pipeline with a running docker-compose environment.

Prerequisites (run before this test):
    docker-compose up --build -d

What this tests:
  1. All service health checks return 200
  2. Ingestion service is publishing to Redis (packets on iot:metrics)
  3. Analytics service is receiving + processing packets
  4. Metrics endpoint returns per-device data (pipeline is running)
  5. Anomalies endpoint is reachable
  6. WebSocket endpoint delivers real-time metric events
  7. Stats show packets are being processed

Run with:
    pytest tests/test_integration.py -v --timeout=60

Or as a script:
    python tests/test_integration.py
"""

import asyncio
import json
import sys
import time
import pytest
import httpx
import websockets


# ---------------------------------------------------------------------------
# Configuration — matches .env defaults for docker-compose
# ---------------------------------------------------------------------------
INGESTION_URL    = "http://localhost:3001"
AUTH_URL         = "http://localhost:3002"
ANALYTICS_URL    = "http://localhost:8001"
DASHBOARD_URL    = "http://localhost:8002"
ANALYTICS_WS_URL = "ws://localhost:8001/ws/analytics"

STARTUP_TIMEOUT  = 60   # seconds to wait for services to be healthy
PACKET_WAIT_S    = 5    # seconds to wait for packets to flow through pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def wait_for_service(url: str, timeout: int = STARTUP_TIMEOUT) -> bool:
    """Poll a /health endpoint until it returns 200 or timeout."""
    deadline = time.time() + timeout
    async with httpx.AsyncClient(timeout=5) as client:
        while time.time() < deadline:
            try:
                resp = await client.get(f"{url}/health")
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(2)
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestServiceHealth:

    async def test_ingestion_service_health(self):
        """Ingestion service should be healthy."""
        assert await wait_for_service(INGESTION_URL), \
            f"Ingestion service not reachable at {INGESTION_URL}"

    async def test_analytics_service_health(self):
        """Analytics service should be healthy (process alive)."""
        assert await wait_for_service(ANALYTICS_URL), \
            f"Analytics service not reachable at {ANALYTICS_URL}"

    async def test_auth_service_health(self):
        """Auth service should be healthy."""
        assert await wait_for_service(AUTH_URL), \
            f"Auth service not reachable at {AUTH_URL}"

    async def test_dashboard_service_health(self):
        """Dashboard service should be healthy."""
        assert await wait_for_service(DASHBOARD_URL), \
            f"Dashboard service not reachable at {DASHBOARD_URL}"


@pytest.mark.asyncio
class TestAnalyticsPipeline:

    async def test_analytics_ready_endpoint(self):
        """
        /ready verifies Redis and InfluxDB are reachable from analytics container.
        Should return 200 once both are up.
        """
        async with httpx.AsyncClient(timeout=10) as client:
            # Retry a few times in case InfluxDB is still initializing
            for _ in range(6):
                resp = await client.get(f"{ANALYTICS_URL}/ready")
                if resp.status_code == 200:
                    data = resp.json()
                    assert data["redis"] == "ok"
                    assert data["influxdb"] == "ok"
                    return
                await asyncio.sleep(5)
            pytest.fail("Analytics /ready never returned 200 within 30s")

    async def test_metrics_endpoint_receives_data(self):
        """
        After waiting for packets to flow through the pipeline,
        /metrics/summary should contain per-device data.
        """
        # Wait for the pipeline to process some packets
        print(f"\nWaiting {PACKET_WAIT_S}s for packets to flow through pipeline...")
        await asyncio.sleep(PACKET_WAIT_S)

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{ANALYTICS_URL}/metrics/summary")
            assert resp.status_code == 200
            data = resp.json()

            assert "total_devices" in data
            assert "packets_processed" in data
            assert data["packets_processed"] > 0, \
                "No packets processed yet — check ingestion-service and Redis connection"
            assert data["total_devices"] > 0, \
                f"No devices tracked. packets_processed={data['packets_processed']}"

            print(f"  ✓ {data['total_devices']} devices tracked, "
                  f"{data['packets_processed']} packets processed")

    async def test_anomalies_endpoint_reachable(self):
        """
        /anomalies/recent should return a list (may be empty if no anomalies yet).
        With ANOMALY_RATE=0.05, anomalies should appear after ~20 packets/device.
        """
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{ANALYTICS_URL}/anomalies/recent?limit=10")
            assert resp.status_code == 200
            data = resp.json()
            assert "anomalies" in data
            print(f"  ✓ Anomalies endpoint OK ({len(data['anomalies'])} in cache)")

    async def test_stats_endpoint_shows_activity(self):
        """Pipeline stats should show packets received and processed."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{ANALYTICS_URL}/stats")
            assert resp.status_code == 200
            data = resp.json()

            assert "packets_processed" in data
            assert "subscriber" in data
            assert data["subscriber"]["total_received"] > 0, \
                "Subscriber received 0 messages — Redis channel may not be active"
            print(f"  ✓ Stats: received={data['subscriber']['total_received']}, "
                  f"processed={data['packets_processed']}, "
                  f"influx_written={data['influx_writer']['total_written']}")

    async def test_websocket_delivers_metric_events(self):
        """
        Connect to /ws/analytics and verify metric events are received
        within a short window.
        """
        received_events = []
        timeout_s = 10   # Should receive events within 10 seconds

        async with websockets.connect(ANALYTICS_WS_URL) as ws:
            deadline = asyncio.get_event_loop().time() + timeout_s
            while asyncio.get_event_loop().time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    event = json.loads(raw)
                    if event.get("event") == "metric":
                        received_events.append(event)
                        if len(received_events) >= 3:
                            break   # We got enough
                except asyncio.TimeoutError:
                    continue

        assert len(received_events) >= 3, \
            f"Expected ≥3 metric events from WebSocket, got {len(received_events)}"

        # Verify event structure
        for e in received_events:
            assert "device_id" in e
            assert "raw_value" in e
            assert "moving_avg" in e
            assert "is_anomaly" in e
            assert "timestamp" in e

        print(f"  ✓ Received {len(received_events)} metric events via WebSocket")
        print(f"    Sample: device={received_events[0]['device_id']}, "
              f"value={received_events[0]['raw_value']}, "
              f"avg={received_events[0]['moving_avg']}, "
              f"anomaly={received_events[0]['is_anomaly']}")


@pytest.mark.asyncio
class TestResilience:

    async def test_ingestion_websocket_live(self):
        """
        Connect to ingestion-service WebSocket (/ws) and verify raw packets arrive.
        This confirms the ingestion → Redis pipeline is live before analytics.
        """
        INGESTION_WS_URL = "ws://localhost:3001/ws"
        received = []

        async with websockets.connect(INGESTION_WS_URL) as ws:
            for _ in range(5):
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    pkt = json.loads(raw)
                    received.append(pkt)
                except asyncio.TimeoutError:
                    break

        assert len(received) >= 1, "No packets received from ingestion WebSocket"
        pkt = received[0]
        assert "device_id" in pkt
        assert "metric_value" in pkt
        assert "timestamp" in pkt
        print(f"  ✓ Ingestion WS: {len(received)} packets received. "
              f"Sample device: {pkt['device_id']}")


# ---------------------------------------------------------------------------
# Script-mode runner (python tests/test_integration.py)
# ---------------------------------------------------------------------------
async def run_all_tests():
    """Run all integration tests and print results."""
    print("\n" + "="*60)
    print("NexusStream Integration Tests")
    print("="*60)

    tests = [
        ("Service Health — Ingestion",  TestServiceHealth().test_ingestion_service_health),
        ("Service Health — Analytics",  TestServiceHealth().test_analytics_service_health),
        ("Service Health — Auth",       TestServiceHealth().test_auth_service_health),
        ("Service Health — Dashboard",  TestServiceHealth().test_dashboard_service_health),
        ("Analytics /ready",            TestAnalyticsPipeline().test_analytics_ready_endpoint),
        ("Metrics pipeline active",     TestAnalyticsPipeline().test_metrics_endpoint_receives_data),
        ("Anomalies endpoint",          TestAnalyticsPipeline().test_anomalies_endpoint_reachable),
        ("Pipeline stats",              TestAnalyticsPipeline().test_stats_endpoint_shows_activity),
        ("WebSocket metric events",     TestAnalyticsPipeline().test_websocket_delivers_metric_events),
        ("Ingestion WebSocket live",    TestResilience().test_ingestion_websocket_live),
    ]

    passed = failed = 0
    for name, coro in tests:
        print(f"\n▶ {name}")
        try:
            await coro()
            print(f"  ✅ PASSED")
            passed += 1
        except AssertionError as ae:
            print(f"  ❌ FAILED: {ae}")
            failed += 1
        except Exception as exc:
            print(f"  ❌ ERROR: {exc}")
            failed += 1

    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
