"""
Unit tests for device_service module.
Tests cover:
- Fetching IoT device status
- Evaluating online/offline state based on heartbeat threshold (TRD Sec 21)
- Handling ISO strings, datetimes, and timezones
- Updating device heartbeat
- Fetching all registered devices
"""

from datetime import datetime, timezone, timedelta
import pytest
from services.device_service import (
    get_device_status,
    get_all_devices,
    is_device_online,
    update_device_heartbeat,
    set_device_registration_mode,
    get_device_registration_mode,
)


class TestGetDeviceStatus:
    """Test suite for fetching device records."""

    def test_get_device_status_found(self, mock_supabase):
        """Fetches GATE-01 device status correctly."""
        device = get_device_status(mock_supabase, device_id="GATE-01")
        assert device is not None
        assert device["device_id"] == "GATE-01"
        assert device["device_name"] == "ESP32-S3 Gate Controller"
        assert device["status"] in ["online", "offline"]

    def test_get_device_status_not_found(self, mock_supabase):
        """Returns None for unregistered device ID."""
        device = get_device_status(mock_supabase, device_id="UNKNOWN-DEV")
        assert device is None

    def test_get_all_devices(self, mock_supabase):
        """Fetches all registered IoT devices."""
        devices = get_all_devices(mock_supabase)
        assert len(devices) >= 2
        ids = [d["device_id"] for d in devices]
        assert "GATE-01" in ids
        assert "PARKING-01" in ids


class TestDeviceOnlineThreshold:
    """Test suite for online/offline threshold logic (TRD Sec 21: 30 seconds threshold)."""

    def test_is_device_online_recent_heartbeat(self):
        """Heartbeat received 10 seconds ago with 30s threshold -> online."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(seconds=10)
        assert is_device_online(recent, threshold_seconds=30) is True

    def test_is_device_online_exceeded_threshold(self):
        """Heartbeat received 45 seconds ago with 30s threshold -> offline."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(seconds=45)
        assert is_device_online(old, threshold_seconds=30) is False

    def test_is_device_online_handles_iso_string_with_z(self):
        """Handles ISO 8601 string format ending with 'Z'."""
        now = datetime.now(timezone.utc)
        iso_str = (now - timedelta(seconds=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert is_device_online(iso_str, threshold_seconds=30) is True

    def test_is_device_online_handles_iso_string_with_offset(self):
        """Handles ISO 8601 string format with timezone offset."""
        now = datetime.now(timezone.utc)
        iso_str = (now - timedelta(seconds=12)).isoformat()
        assert is_device_online(iso_str, threshold_seconds=30) is True

    def test_is_device_online_none_last_seen(self):
        """When last_seen is None, device is offline."""
        assert is_device_online(None, threshold_seconds=30) is False

    def test_is_device_online_custom_threshold(self):
        """Respects custom threshold values."""
        now = datetime.now(timezone.utc)
        t = now - timedelta(seconds=15)
        # With threshold 10s -> offline
        assert is_device_online(t, threshold_seconds=10) is False
        # With threshold 60s -> online
        assert is_device_online(t, threshold_seconds=60) is True


class TestUpdateDeviceHeartbeat:
    """Test suite for updating device heartbeats."""

    def test_update_device_heartbeat_existing(self, mock_supabase):
        """Updates heartbeat for existing GATE-01."""
        updated = update_device_heartbeat(mock_supabase, device_id="GATE-01", status="online")
        assert updated["device_id"] == "GATE-01"
        assert updated["status"] == "online"
        assert "last_seen" in updated

        # Verify device status in DB
        device = get_device_status(mock_supabase, "GATE-01")
        assert device["status"] == "online"

    def test_update_device_heartbeat_new_device_upsert(self, mock_supabase):
        """Upserts a new device if not registered yet."""
        updated = update_device_heartbeat(
            mock_supabase,
            device_id="GATE-02",
            status="online",
            device_name="ESP32-S3 Exit Gate"
        )
        assert updated["device_id"] == "GATE-02"
        assert updated["status"] == "online"

        device = get_device_status(mock_supabase, "GATE-02")
        assert device is not None
        assert device["device_name"] == "ESP32-S3 Exit Gate"


class TestDeviceRegistrationMode:
    """Test suite for toggling and checking device registration mode."""

    def test_set_and_get_registration_mode(self, mock_supabase):
        """Verifies setting registration mode to True and back to False."""
        # Enable registration mode
        ok = set_device_registration_mode(mock_supabase, "GATE-01", enable=True)
        assert ok is True
        assert get_device_registration_mode(mock_supabase, "GATE-01") is True

        # Disable registration mode
        ok_off = set_device_registration_mode(mock_supabase, "GATE-01", enable=False)
        assert ok_off is True
        assert get_device_registration_mode(mock_supabase, "GATE-01") is False

