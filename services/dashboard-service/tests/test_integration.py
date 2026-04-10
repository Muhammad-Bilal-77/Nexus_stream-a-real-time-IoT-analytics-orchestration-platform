"""
NexusStream Dashboard Service — Integration Tests
=================================================
Tests the dashboard API against the live docker-compose stack.

Run with:
    pytest tests/test_integration.py -v
"""

import pytest
import httpx
import websockets
import json
import asyncio
import jwt

DASHBOARD_URL = "http://localhost:8002"
WS_URL = "ws://localhost:8002/ws/dashboard"
JWT_SECRET = "nexusstream-dev-jwt-secret-change-in-prod"
JWT_ALG = "HS256"


def generate_token(role: str) -> str:
    payload = {"sub": f"test_{role}", "username": f"{role}_user", "roles": [role]}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

VIEWER_TOKEN = generate_token("viewer")
ANALYST_TOKEN = generate_token("analyst")
ADMIN_TOKEN = generate_token("admin")


@pytest.mark.asyncio
class TestDashboardE2E:
    async def test_health_and_ready(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{DASHBOARD_URL}/health")
            assert resp.status_code == 200
            
            resp = await client.get(f"{DASHBOARD_URL}/ready")
            assert resp.status_code in (200, 503) # 503 if influx/redis not fully up

    async def test_rbac_stats_overview(self):
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {VIEWER_TOKEN}"}
            resp = await client.get(f"{DASHBOARD_URL}/api/v1/stats/overview", headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "total_devices" in data

    async def test_rbac_anomalies_viewer_fails(self):
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {VIEWER_TOKEN}"}
            resp = await client.get(f"{DASHBOARD_URL}/api/v1/anomalies", headers=headers)
            assert resp.status_code == 403

    async def test_rbac_anomalies_analyst_succeeds(self):
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {ANALYST_TOKEN}"}
            resp = await client.get(f"{DASHBOARD_URL}/api/v1/anomalies", headers=headers)
            assert resp.status_code == 200
            assert "anomalies" in resp.json()

    async def test_rbac_admin_stats(self):
        async with httpx.AsyncClient() as client:
            headers_analyst = {"Authorization": f"Bearer {ANALYST_TOKEN}"}
            resp = await client.get(f"{DASHBOARD_URL}/api/v1/admin/stats", headers=headers_analyst)
            assert resp.status_code == 403

            headers_admin = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
            resp = await client.get(f"{DASHBOARD_URL}/api/v1/admin/stats", headers=headers_admin)
            assert resp.status_code == 200

    async def test_ws_connection_viewer(self):
        url = f"{WS_URL}?token={VIEWER_TOKEN}"
        try:
            async with websockets.connect(url, ping_timeout=10) as ws:
                # Wait for at least one message
                deadline = asyncio.get_event_loop().time() + 10
                while asyncio.get_event_loop().time() < deadline:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(msg)
                    if data.get("event") == "ping":
                        continue
                        
                    # viewer receives limited fields
                    assert "device_id" in data
                    assert "raw_value" not in data # Analyst+ only
                    break
        except Exception as e:
            pytest.fail(f"WebSocket connection failed: {e}")
