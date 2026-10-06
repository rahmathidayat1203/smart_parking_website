"""
Unit and integration tests for CRUD (Create, Read, Update, Delete) operations
across all system entities:
- Parking Slots: create, update, delete
- IoT Devices: update, delete
- App Users: update profile (full name, role, device)
- Audit Forensic Logs: delete single, clear all
- Sensor Telemetry: delete single reading, clear by device
- RFID Scans: delete single scan, clear by device
- Parking Members: update, delete
"""

import pytest
from services.parking_service import (
    create_parking_slot,
    update_parking_slot,
    delete_parking_slot,
    get_parking_slots,
)
from services.device_service import (
    update_device,
    delete_device,
    get_device_status,
)
from services.auth_service import (
    update_user_profile,
    get_all_users,
)
from services.audit_service import (
    delete_audit_log,
    clear_all_audit_logs,
    get_audit_logs,
    log_audit_event,
)
from services.sensor_service import (
    delete_sensor_reading,
    clear_sensor_data_by_device,
    add_sensor_reading,
    get_recent_sensor_data,
)
from services.member_service import (
    update_member,
    delete_member,
    get_member_by_uid,
    delete_rfid_scan,
    clear_rfid_scans_by_device,
)


class TestParkingSlotCRUD:
    def test_create_update_delete_parking_slot(self, mock_supabase):
        # 1. Create
        created = create_parking_slot(mock_supabase, slot_code="P99", device_id="GATE-01")
        assert created["slot_code"] == "P99"
        assert created["device_id"] == "GATE-01"
        assert created["status"] == "available"

        # 2. Update status and device
        updated = update_parking_slot(
            mock_supabase,
            slot_code="P99",
            new_slot_code="P99-NEW",
            status="occupied",
            device_id=None,
        )
        assert updated["slot_code"] == "P99-NEW"
        assert updated["status"] == "occupied"
        assert updated["device_id"] is None

        # 3. Delete
        deleted = delete_parking_slot(mock_supabase, "P99-NEW")
        assert deleted is True

        # Verify not in slots
        slots = get_parking_slots(mock_supabase)
        assert not any(s["slot_code"] == "P99-NEW" for s in slots)

    def test_create_duplicate_slot_raises(self, mock_supabase):
        with pytest.raises(ValueError, match="sudah digunakan"):
            create_parking_slot(mock_supabase, slot_code="P01")

    def test_update_nonexistent_slot_raises(self, mock_supabase):
        with pytest.raises(ValueError, match="tidak ditemukan"):
            update_parking_slot(mock_supabase, slot_code="NONEXISTENT")


class TestIoTDeviceCRUD:
    def test_update_and_delete_device(self, mock_supabase):
        # Update device
        updated = update_device(
            mock_supabase,
            device_id="GATE-01",
            device_name="Gerbang Utama Baru",
            owner_name="Admin Utama",
            device_type="gate",
        )
        assert updated["device_name"] == "Gerbang Utama Baru"
        assert updated["owner_name"] == "Admin Utama"
        assert updated["device_type"] == "gate"

        # Delete device
        deleted = delete_device(mock_supabase, "PARKING-01")
        assert deleted is True
        assert get_device_status(mock_supabase, "PARKING-01") is None

    def test_update_nonexistent_device_raises(self, mock_supabase):
        with pytest.raises(ValueError, match="tidak ditemukan"):
            update_device(mock_supabase, "DEV_GHOST")


class TestUserProfileUpdate:
    def test_update_user_profile(self, mock_supabase):
        updated = update_user_profile(
            mock_supabase,
            username="admin",
            full_name="Administrator Super",
            role="admin",
            device_id="GATE-01",
        )
        assert updated["full_name"] == "Administrator Super"
        assert updated["role"] == "admin"
        assert updated["device_id"] == "GATE-01"

    def test_update_nonexistent_user_raises(self, mock_supabase):
        with pytest.raises(ValueError, match="tidak ditemukan"):
            update_user_profile(mock_supabase, username="ghost_user")


class TestAuditLogCRUD:
    def test_delete_and_clear_audit_logs(self, mock_supabase):
        # Log an event first
        log_audit_event(
            mock_supabase,
            event_type="test_event",
            device_id="GATE-01",
            details="Test Audit",
        )
        logs = get_audit_logs(mock_supabase)
        assert len(logs) > 0
        first_id = logs[0].get("id")

        if first_id:
            del_res = delete_audit_log(mock_supabase, first_id)
            assert del_res is True

        # Clear all
        clear_res = clear_all_audit_logs(mock_supabase)
        assert clear_res is True
        assert len(get_audit_logs(mock_supabase)) == 0


class TestSensorTelemetryCRUD:
    def test_delete_and_clear_sensor_readings(self, mock_supabase):
        # Add reading
        add_sensor_reading(mock_supabase, device_id="TEST-DEV", sensor_type="ultrasonic", sensor_value=15.5)
        history = [s for s in get_recent_sensor_data(mock_supabase) if s.get("device_id") == "TEST-DEV"]
        assert len(history) >= 1

        first_id = history[0].get("id")
        if first_id:
            del_res = delete_sensor_reading(mock_supabase, first_id)
            assert del_res is True

        # Clear all for device
        add_sensor_reading(mock_supabase, device_id="TEST-DEV", sensor_type="ir", sensor_value=1.0)
        clear_res = clear_sensor_data_by_device(mock_supabase, "TEST-DEV")
        assert clear_res is True
        remaining = [s for s in get_recent_sensor_data(mock_supabase) if s.get("device_id") == "TEST-DEV"]
        assert len(remaining) == 0


class TestRfidScansAndMemberCRUD:
    def test_rfid_scan_delete_and_clear(self, mock_supabase):
        # Insert test scan
        mock_supabase.table("rfid_scans").insert({
            "id": 888,
            "uid": "AA:BB:CC:DD",
            "device_id": "TEST-DEV",
            "created_at": "2026-03-30T10:00:00Z",
        }).execute()

        # Delete single scan
        del_scan = delete_rfid_scan(mock_supabase, 888)
        assert del_scan is True

        # Clear scans by device
        mock_supabase.table("rfid_scans").insert({
            "uid": "11:22:33:44",
            "device_id": "TEST-DEV",
        }).execute()
        clear_res = clear_rfid_scans_by_device(mock_supabase, "TEST-DEV")
        assert clear_res is True

    def test_member_update_and_delete(self, mock_supabase):
        # Update member
        updated = update_member(
            mock_supabase,
            member_id="B4E22D33",
            member_name="Budi Updated",
            license_plate="B 9999 XYZ",
            vehicle_type="motorcycle",
            status="inactive",
        )
        assert updated["member_name"] == "Budi Updated"
        assert updated["license_plate"] == "B 9999 XYZ"
        assert updated["vehicle_type"] == "motorcycle"
        assert updated["status"] == "inactive"

        # Delete member
        deleted = delete_member(mock_supabase, "B4E22D33")
        assert deleted is True
        assert get_member_by_uid(mock_supabase, "B4E22D33") is None
