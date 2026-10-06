"""
TDD Unit tests for Student Device Registration & Dedicated Dashboard service.
Tests key generation, device onboarding, API key validation, telemetry filtering,
and ESP32 firmware snippet generation.
"""

import pytest
from datetime import datetime, timezone

from services.device_service import (
    generate_device_api_key,
    register_student_device,
    get_device_by_api_key,
    get_student_device_telemetry,
    generate_esp32_code_snippet,
)


def test_generate_device_api_key():
    """Verify API key format and uniqueness."""
    key1 = generate_device_api_key()
    key2 = generate_device_api_key()

    assert isinstance(key1, str)
    assert key1.startswith("sk_dev_")
    assert len(key1) >= 20
    assert key1 != key2


def test_register_student_device_success(mock_supabase):
    """Verify successful student device registration with auto-generated API key."""
    result = register_student_device(
        supabase=mock_supabase,
        owner_name="Ahmad Zaki",
        device_name="ESP32 Gerbang Siswa A",
        device_type="gate",
        device_id="DEV-SISWA-01",
    )

    assert result["device_id"] == "DEV-SISWA-01"
    assert result["owner_name"] == "Ahmad Zaki"
    assert result["device_name"] == "ESP32 Gerbang Siswa A"
    assert result["device_type"] == "gate"
    assert result["status"] == "offline"
    assert result["api_key"].startswith("sk_dev_")

    # Verify device exists in database
    dev = mock_supabase.table("iot_devices").select("*").eq("device_id", "DEV-SISWA-01").execute().data
    assert len(dev) == 1
    assert dev[0]["owner_name"] == "Ahmad Zaki"


def test_register_student_device_validation_errors(mock_supabase):
    """Verify validation when registering student devices."""
    # Empty owner name
    with pytest.raises(ValueError, match="Nama pemilik/siswa tidak boleh kosong"):
        register_student_device(
            supabase=mock_supabase,
            owner_name="  ",
            device_name="ESP32 Node",
        )

    # Empty device name
    with pytest.raises(ValueError, match="Nama perangkat tidak boleh kosong"):
        register_student_device(
            supabase=mock_supabase,
            owner_name="Ahmad Zaki",
            device_name="",
        )

    # Duplicate device ID
    register_student_device(
        supabase=mock_supabase,
        owner_name="Ahmad Zaki",
        device_name="Node 1",
        device_id="DEV-DUP-01",
    )
    with pytest.raises(ValueError, match="sudah terdaftar"):
        register_student_device(
            supabase=mock_supabase,
            owner_name="Budi",
            device_name="Node 2",
            device_id="DEV-DUP-01",
        )


def test_get_device_by_api_key(mock_supabase):
    """Verify lookup of device by API key."""
    created = register_student_device(
        supabase=mock_supabase,
        owner_name="Siti Rahma",
        device_name="ESP32 Sensor Siswa B",
        device_id="DEV-SISWA-02",
    )
    api_key = created["api_key"]

    device = get_device_by_api_key(mock_supabase, api_key)
    assert device is not None
    assert device["device_id"] == "DEV-SISWA-02"
    assert device["owner_name"] == "Siti Rahma"

    # Unknown key returns None
    invalid = get_device_by_api_key(mock_supabase, "sk_dev_invalid_key_12345")
    assert invalid is None


def test_get_student_device_telemetry(mock_supabase):
    """Verify telemetry retrieval isolated strictly to the target student device."""
    # Register student device
    register_student_device(
        supabase=mock_supabase,
        owner_name="Dewi Lestari",
        device_name="ESP32 Multi Siswa C",
        device_id="DEV-SISWA-03",
    )

    # Insert sensor readings for DEV-SISWA-03 and GATE-01
    mock_supabase.table("sensor_data").insert({
        "device_id": "DEV-SISWA-03",
        "sensor_type": "ultrasonic",
        "sensor_value": 24.5,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    mock_supabase.table("sensor_data").insert({
        "device_id": "DEV-SISWA-03",
        "sensor_type": "ir",
        "sensor_value": 480,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    mock_supabase.table("sensor_data").insert({
        "device_id": "GATE-01",
        "sensor_type": "ultrasonic",
        "sensor_value": 15.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    # Insert RFID scan for DEV-SISWA-03
    mock_supabase.table("rfid_scans").insert({
        "device_id": "DEV-SISWA-03",
        "uid": "E5F6G7H8",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    telemetry = get_student_device_telemetry(mock_supabase, "DEV-SISWA-03")

    assert "sensors" in telemetry
    assert "scans" in telemetry
    assert "latest_ultrasonic" in telemetry
    assert len(telemetry["sensors"]) == 2
    assert telemetry["latest_ultrasonic"] == 24.5
    assert len(telemetry["scans"]) == 1
    assert telemetry["scans"][0]["uid"] == "E5F6G7H8"


def test_generate_esp32_code_snippet():
    """Verify C++ Arduino code generator produces correct credentials and syntax."""
    code = generate_esp32_code_snippet(
        device_id="DEV-SISWA-01",
        api_key="sk_dev_abcdef1234567890",
        supabase_url="https://wxowndnwwzryzdkdkkqx.supabase.co",
        supabase_anon_key="sb_publishable_anon_123",
    )

    assert "DEV-SISWA-01" in code
    assert "sk_dev_abcdef1234567890" in code
    assert "https://wxowndnwwzryzdkdkkqx.supabase.co" in code
    assert "sendHeartbeat()" in code
    assert "sendUltrasonicReading" in code
    assert "#include <WiFi.h>" in code


def test_get_student_devices_filtering(mock_supabase):
    """Verify separating student nodes from system infrastructure nodes."""
    from services.device_service import get_student_devices

    # Register student devices
    register_student_device(mock_supabase, "Rian", "Node Rian", device_id="DEV-SISWA-10")
    register_student_device(mock_supabase, "Maya", "Node Maya", device_id="DEV-SISWA-11")

    student_devs = get_student_devices(mock_supabase)
    dev_ids = [d["device_id"] for d in student_devs]

    assert "DEV-SISWA-10" in dev_ids
    assert "DEV-SISWA-11" in dev_ids
    assert "GATE-01" not in dev_ids
    assert "PARKING-01" not in dev_ids


def test_get_student_device_full_details(mock_supabase):
    """Verify comprehensive detail bundle for a student device."""
    from services.device_service import get_student_device_full_details

    register_student_device(
        supabase=mock_supabase,
        owner_name="Ilham",
        device_name="ESP32 Ilham",
        device_id="DEV-SISWA-12",
        device_type="gate",
    )

    details = get_student_device_full_details(mock_supabase, "DEV-SISWA-12")

    assert details is not None
    assert details["device"]["device_id"] == "DEV-SISWA-12"
    assert details["device"]["owner_name"] == "Ilham"
    assert details["device"]["device_type"] == "gate"
    assert "online" in details
    assert "telemetry" in details
    assert "total_telemetry_count" in details
    assert "total_scans_count" in details

