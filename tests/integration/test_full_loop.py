"""
Integration Test: The Golden Loop

End-to-end test of the complete data pipeline:
Frontend -> API -> HAL -> Redis -> API -> WebSocket -> Frontend

Test Scenario:
1. Create a Run (API)
2. Connect via WebSocket (API)
3. Execute the Run (triggers HAL)
4. Verify telemetry frames arrive via WebSocket
5. Verify "Duck Shape" CV curve (voltage up, then down)
6. Trigger emergency stop
7. Verify cleanup

Architecture Flow:
    [Test Client]
        |
        v
    [API: POST /runs] --> Create Run in DB
        |
        v
    [API: WS /ws/runs/{id}] --> Subscribe to Redis (run:{id}:telemetry)
        |
        v
    [API: POST /runs/{id}/execute] --> Call HAL /start_run
        |
        v
    [HAL: POST /start_run] --> Start Mock Driver with CV waveform
        |
        v
    [HAL: stream_telemetry] --> Publish frames to Redis
        |
        v
    [API: Redis Subscriber] --> Forward frames to WebSocket
        |
        v
    [Test Client: WebSocket] --> Receive frames, verify duck shape

Success Criteria:
- WebSocket connection established
- "status: running" event received
- At least 10 telemetry frames received
- Voltage follows triangle wave: -0.5 -> +0.5 -> -0.5 (duck shape)
- Emergency stop successful
- All connections cleaned up
"""

import pytest
import asyncio
import httpx
from websockets.client import connect as ws_connect
import json
from typing import List, Dict, Any
from datetime import datetime, timedelta


# ============ Test Configuration ============

API_BASE_URL = "http://localhost:8080"
HAL_BASE_URL = "http://localhost:8081"
WS_BASE_URL = "ws://localhost:8080"

# Test user credentials (assumes user exists or will be created)
TEST_USER = {
    "username": "test_user_integration",
    "email": "integration@test.com",
    "password": "integration_test_password_123!",
    "full_name": "Integration Test User"
}


# ============ Fixtures ============

@pytest.fixture(scope="module")
async def api_client():
    """Create HTTP client for API"""
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="module")
async def hal_client():
    """Create HTTP client for HAL"""
    async with httpx.AsyncClient(base_url=HAL_BASE_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="module")
async def auth_token(api_client):
    """
    Get authentication token for test user

    Creates user if doesn't exist, then authenticates
    """
    # Try to register (might fail if user exists)
    try:
        register_response = await api_client.post(
            "/api/v1/auth/register",
            json=TEST_USER
        )
        if register_response.status_code == 201:
            print(f"✓ Created test user: {TEST_USER['username']}")
    except Exception as e:
        print(f"Note: User registration failed (might already exist): {e}")

    # Authenticate
    token_response = await api_client.post(
        "/api/v1/auth/token",
        data={
            "username": TEST_USER["username"],
            "password": TEST_USER["password"]
        }
    )

    assert token_response.status_code == 200, f"Authentication failed: {token_response.text}"

    token_data = token_response.json()
    access_token = token_data["access_token"]

    print(f"✓ Authenticated as: {TEST_USER['username']}")

    return access_token


# ============ The Golden Loop Test ============

@pytest.mark.asyncio
@pytest.mark.integration
async def test_golden_loop(api_client, hal_client, auth_token):
    """
    The Golden Loop: Full end-to-end test of Frontend -> API -> HAL -> Redis -> WebSocket

    This test verifies the complete integration of all services.
    """

    print("\n" + "=" * 80)
    print("🔬 GOLDEN LOOP TEST: Frontend -> API -> HAL -> Redis -> WebSocket")
    print("=" * 80)

    # ========== Step 1: Check HAL Health ==========

    print("\n📡 Step 1: Check HAL service health...")

    hal_health = await hal_client.get("/health")
    assert hal_health.status_code == 200, "HAL service not healthy"

    hal_health_data = hal_health.json()
    print(f"   HAL Status: {hal_health_data['status']}")
    print(f"   Redis Connected: {hal_health_data['redis_connected']}")

    assert hal_health_data["status"] == "healthy", "HAL service is not healthy"
    assert hal_health_data["redis_connected"] is True, "HAL not connected to Redis"

    print("   ✓ HAL service is healthy")

    # ========== Step 2: Create Run ==========

    print("\n📝 Step 2: Create a Run in API...")

    run_create_response = await api_client.post(
        "/api/v1/runs",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "type": "experiment",
            "engine": "auto",
            "tags": ["integration-test", "golden-loop"],
            "metadata": {"driver": "mock", "test": "golden_loop"}
        }
    )

    assert run_create_response.status_code == 202, f"Run creation failed: {run_create_response.text}"

    run_data = run_create_response.json()
    run_id = run_data["run_id"]

    print(f"   ✓ Created Run: {run_id}")
    print(f"   Status: {run_data['status']}")

    # ========== Step 3: Connect WebSocket ==========

    print(f"\n🔌 Step 3: Connect to WebSocket (ws://localhost:8080/ws/runs/{run_id}?token=...)...")

    ws_url = f"{WS_BASE_URL}/ws/runs/{run_id}?token={auth_token}"

    frames_received: List[Dict[str, Any]] = []
    connection_events: List[Dict[str, Any]] = []

    async def websocket_listener():
        """Background task to listen for WebSocket messages"""
        nonlocal frames_received, connection_events

        async with ws_connect(ws_url) as websocket:
            print("   ✓ WebSocket connected")

            # Wait for messages
            async for message in websocket:
                data = json.loads(message)

                msg_type = data.get("type")

                if msg_type == "event":
                    connection_events.append(data)
                    event = data.get("event")
                    print(f"   📬 Event: {event}")

                    if event == "connected":
                        print(f"      Telemetry Channel: {data.get('telemetry_channel')}")

                elif msg_type == "frame":
                    frames_received.append(data)

                    # Log every 10th frame
                    if len(frames_received) % 10 == 0:
                        frame_data = data.get("data", {})
                        print(
                            f"   📊 Frame {len(frames_received)}: "
                            f"V={frame_data.get('voltage', 0):.3f}V, "
                            f"I={frame_data.get('current', 0):.6f}A"
                        )

                # Stop after receiving 50 frames (sufficient to verify duck shape)
                if len(frames_received) >= 50:
                    print(f"   ✓ Received {len(frames_received)} frames, stopping listener")
                    break

    # Start WebSocket listener in background
    ws_task = asyncio.create_task(websocket_listener())

    # Wait for connection event
    await asyncio.sleep(1.0)

    assert len(connection_events) > 0, "Did not receive connection event"
    assert connection_events[0]["event"] == "connected", "Connection event not received"

    print("   ✓ WebSocket connection confirmed")

    # ========== Step 4: Execute Run (Trigger HAL) ==========

    print(f"\n🚀 Step 4: Execute Run (POST /api/v1/runs/{run_id}/execute)...")

    execute_response = await api_client.post(
        f"/api/v1/runs/{run_id}/execute",
        headers={"Authorization": f"Bearer {auth_token}"}
    )

    assert execute_response.status_code == 200, f"Execute failed: {execute_response.text}"

    execute_data = execute_response.json()

    print(f"   ✓ Run executed on HAL")
    print(f"   Status: {execute_data['status']}")
    print(f"   Telemetry Channel: {execute_data['telemetry_channel']}")
    print(f"   WebSocket URL: {execute_data['websocket_url']}")

    # ========== Step 5: Wait for Telemetry Frames ==========

    print("\n📡 Step 5: Waiting for telemetry frames from HAL via Redis...")

    # Wait for WebSocket listener to collect frames
    try:
        await asyncio.wait_for(ws_task, timeout=15.0)
    except asyncio.TimeoutError:
        print(f"   ⚠️ Timeout after 15s, received {len(frames_received)} frames")

    print(f"   ✓ Received {len(frames_received)} telemetry frames")

    # ========== Step 6: Verify Frame Count ==========

    print(f"\n✅ Step 6: Verify frame count...")

    assert len(frames_received) >= 10, f"Expected at least 10 frames, got {len(frames_received)}"

    print(f"   ✓ Frame count: {len(frames_received)} (>= 10) ✓")

    # ========== Step 7: Verify Duck Shape (CV Curve) ==========

    print("\n🦆 Step 7: Verify 'Duck Shape' (CV curve)...")

    # Extract voltage values
    voltages = []
    currents = []

    for frame in frames_received:
        if frame.get("type") == "frame":
            data = frame.get("data", {})
            voltage = data.get("voltage")
            current = data.get("current")

            if voltage is not None:
                voltages.append(voltage)
            if current is not None:
                currents.append(current)

    print(f"   Collected {len(voltages)} voltage values")

    assert len(voltages) >= 10, "Not enough voltage data points"

    # Verify triangle wave: starts low, goes high, comes back down
    # CV waveform: initial_value=-0.5, final_value=0.5, duration=10s
    # Expected pattern: -0.5 -> 0.5 (forward scan) -> -0.5 (reverse scan)

    first_third = voltages[: len(voltages) // 3]
    middle_third = voltages[len(voltages) // 3 : 2 * len(voltages) // 3]
    last_third = voltages[2 * len(voltages) // 3 :]

    avg_first = sum(first_third) / len(first_third) if first_third else 0
    avg_middle = sum(middle_third) / len(middle_third) if middle_third else 0
    avg_last = sum(last_third) / len(last_third) if last_third else 0

    print(f"   Average Voltage:")
    print(f"      First third:  {avg_first:.3f}V")
    print(f"      Middle third: {avg_middle:.3f}V")
    print(f"      Last third:   {avg_last:.3f}V")

    # Duck shape verification:
    # - First third should be < 0 (starts at -0.5V)
    # - Middle third should be > 0 (reaches +0.5V)
    # - Last third should be < 0 (returns to -0.5V)

    assert avg_first < 0, f"First third should be negative (got {avg_first:.3f}V)"
    assert avg_middle > 0, f"Middle third should be positive (got {avg_middle:.3f}V)"
    assert avg_last < 0, f"Last third should be negative (got {avg_last:.3f}V)"

    print("   ✓ Duck shape verified: Voltage goes UP then DOWN (triangle wave) 🦆")

    # ========== Step 8: Verify Current Values ==========

    print("\n⚡ Step 8: Verify current values (Butler-Volmer simulation)...")

    assert len(currents) >= 10, "Not enough current data points"

    # Currents should be non-zero (Butler-Volmer simulation)
    non_zero_currents = [i for i in currents if abs(i) > 1e-9]

    print(f"   Non-zero currents: {len(non_zero_currents)}/{len(currents)}")
    print(f"   Current range: {min(currents):.6f}A to {max(currents):.6f}A")

    assert len(non_zero_currents) > 0, "All currents are zero (simulation not working)"

    print("   ✓ Current values look realistic")

    # ========== Step 9: Emergency Stop ==========

    print(f"\n🛑 Step 9: Trigger emergency stop...")

    connection_id = execute_data.get("connection_id")

    emergency_stop_response = await hal_client.post(
        "/emergency_stop",
        json={"connection_id": connection_id}
    )

    assert emergency_stop_response.status_code == 200, f"Emergency stop failed: {emergency_stop_response.text}"

    stop_data = emergency_stop_response.json()
    print(f"   ✓ Emergency stop executed")
    print(f"   Connections stopped: {stop_data['connections_stopped']}")

    # ========== Step 10: Cleanup ==========

    print("\n🧹 Step 10: Cleanup...")

    # Disconnect from HAL
    disconnect_response = await hal_client.delete(f"/connections/{connection_id}")
    assert disconnect_response.status_code == 200, f"Disconnect failed: {disconnect_response.text}"

    print(f"   ✓ Disconnected from HAL: {connection_id}")

    # ========== SUCCESS ==========

    print("\n" + "=" * 80)
    print("🎉 GOLDEN LOOP TEST PASSED!")
    print("=" * 80)
    print("\nSummary:")
    print(f"   Run ID: {run_id}")
    print(f"   Frames Received: {len(frames_received)}")
    print(f"   Voltage Range: {min(voltages):.3f}V to {max(voltages):.3f}V")
    print(f"   Current Range: {min(currents):.6f}A to {max(currents):.6f}A")
    print(f"   Duck Shape: ✓ Verified (voltage up, then down)")
    print(f"   Emergency Stop: ✓ Successful")
    print("\n✨ All integration tests passed!")
    print("=" * 80 + "\n")


# ============ Additional Helper Tests ============

@pytest.mark.asyncio
@pytest.mark.integration
async def test_hal_health_check(hal_client):
    """Test HAL service health endpoint"""
    response = await hal_client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "active_connections" in data
    assert "redis_connected" in data

    print(f"✓ HAL Health: {data['status']}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_api_health_check(api_client):
    """Test API service health endpoint"""
    response = await api_client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "timestamp" in data

    print(f"✓ API Health: {data['status']}")
