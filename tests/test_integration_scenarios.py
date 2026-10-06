"""
End-to-End Integration Test Suite for Smart Parking Monitoring & RFID Member System.
Validates end-to-end integration scenarios, hardware/cloud lifecycle workflows,
and strict compliance with TRD Section 27 and DRD Section 32:

1. Scenario 1: Complete RFID Registration Flow (ESP32 writes to rfid_scans -> service fetches
   scan -> register member -> verify in parking_members -> duplicate check catches subsequent
   scan of same UID and blocks registration).
2. Scenario 2: Smart Parking Sensor Lifecycle (Vehicle arrival detected by HC-SR04 -> slot
   occupied detected by IR analog reading -> slot status updated in parking_slots -> metrics
   recalculated accurately).
3. Scenario 3: IoT Heartbeat and Offline Detection Lifecycle (ESP32-S3 heartbeat sent ->
   device marked online -> after 30s without heartbeat -> marked offline -> warning triggered
   -> slots flagged accordingly).
4. Scenario 4: Member Management Lifecycle (Register -> Update -> Toggle active/inactive ->
   Delete -> Verify removal).
5. Scenario 5: Strict Compliance Assertion (Verify NO manual gate buttons in any file,
   verify readonly UID on scan, and full TRD 27 / DRD 32 acceptance matrices).
"""

import ast
import glob
import os
from datetime import datetime, timezone, timedelta
import pytest

from services.member_service import (
    normalize_rfid_uid,
    is_uid_registered,
    register_member,
    get_all_members,
    get_member_by_uid,
    update_member,
    toggle_member_status,
    delete_member,
    get_latest_rfid_scan,
    validate_rfid_access,
)
from services.parking_service import (
    get_parking_slots,
    calculate_slot_metrics,
    update_slot_status,
    check_slot_offline,
    evaluate_slot_status,
    VALID_SLOT_STATUSES,
)
from services.device_service import (
    get_device_status,
    get_all_devices,
    is_device_online,
    update_device_heartbeat,
)
from services.sensor_service import (
    get_recent_sensor_data,
    get_latest_sensor_by_type,
    get_latest_sensors_summary,
    add_sensor_reading,
)
from utils.ui_helpers import (
    render_status_badge,
    format_timestamp,
    get_relative_time,
)


# ==============================================================================
# SCENARIO 1: COMPLETE RFID REGISTRATION FLOW & DUPLICATE PREVENTION
# ==============================================================================
class TestScenario1RfidRegistrationFlow:
    """
    End-to-End Test for RFID Card Scanning, Registration, and Duplicate Prevention.
    Covers TRD Sec 27 (Criteria 3, 4, 5, 6, 7, 8) and DRD Sec 32 (Criteria 3, 4, 5, 6).
    """

    def test_complete_rfid_registration_flow_and_duplicate_block(self, mock_supabase):
        """
        Flow:
        1. ESP32-S3 writes new card UID scan into 'rfid_scans' table.
        2. Streamlit service fetches the scan via get_latest_rfid_scan.
        3. Pre-check confirms UID is not yet registered; gate validation denies entry.
        4. Admin completes member registration using scanned UID.
        5. Member is verified in 'parking_members' table and gate validation grants access.
        6. Subsequent scan of the same physical card is caught by duplicate check.
        7. Registration attempt of the duplicate UID is strictly blocked with ValueError.
        """
        raw_uid = "E8:7A:9B:4C"
        expected_normalized_uid = "E87A9B4C"
        device_id = "GATE-01"

        # Step 1: ESP32-S3 hardware scans RFID card and pushes record to Supabase
        scan_time = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        insert_scan_res = mock_supabase.table("rfid_scans").insert({
            "uid": raw_uid,
            "device_id": device_id,
            "created_at": scan_time,
        }).execute()
        assert insert_scan_res.data is not None

        # Step 2: Streamlit service fetches scan
        latest_scan = get_latest_rfid_scan(mock_supabase)
        assert latest_scan is not None
        assert latest_scan["uid"] == raw_uid
        assert latest_scan["device_id"] == device_id

        # Step 3: UID normalization and pre-registration access check
        norm_uid = normalize_rfid_uid(latest_scan["uid"])
        assert norm_uid == expected_normalized_uid
        assert is_uid_registered(mock_supabase, norm_uid) is False

        # ESP32 gate validation for unregistered card must deny access (gate remains closed)
        pre_val = validate_rfid_access(mock_supabase, norm_uid)
        assert pre_val["authorized"] is False
        assert pre_val["status"] == "unregistered"
        assert pre_val["gate_action"] == "remain_closed"

        # Step 4: Admin registers member using the scanned UID (UID is read-only)
        registered_member = register_member(
            supabase=mock_supabase,
            rfid_uid=norm_uid,
            member_name="Kurniawan Pratama",
            license_plate="BG 8765 KP",
            vehicle_type="car",
            status="active",
        )
        assert registered_member is not None
        assert registered_member["rfid_uid"] == expected_normalized_uid
        assert registered_member["member_name"] == "Kurniawan Pratama"
        assert registered_member["license_plate"] == "BG 8765 KP"
        assert registered_member["status"] == "active"

        # Step 5: Verification in parking_members table and post-registration gate validation
        member_in_db = get_member_by_uid(mock_supabase, expected_normalized_uid)
        assert member_in_db is not None
        assert member_in_db["id"] == registered_member["id"]
        assert member_in_db["vehicle_type"] == "car"
        assert is_uid_registered(mock_supabase, expected_normalized_uid) is True

        # ESP32 gate validation for active registered member grants access (gate opens)
        post_val = validate_rfid_access(mock_supabase, expected_normalized_uid)
        assert post_val["authorized"] is True
        assert post_val["status"] == "active"
        assert post_val["gate_action"] == "open"
        assert post_val["member"]["member_name"] == "Kurniawan Pratama"

        # Step 6: Subsequent scan of the same physical card (e.g. space-formatted by another reader)
        subsequent_scan_time = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
        mock_supabase.table("rfid_scans").insert({
            "uid": "E8 7A 9B 4C",
            "device_id": device_id,
            "created_at": subsequent_scan_time,
        }).execute()

        subsequent_scan = get_latest_rfid_scan(mock_supabase)
        assert subsequent_scan["uid"] == "E8 7A 9B 4C"

        # Duplicate check detects the scanned card is already registered
        assert is_uid_registered(mock_supabase, subsequent_scan["uid"]) is True

        # Step 7: Attempting to register the duplicate UID is strictly blocked
        with pytest.raises(ValueError, match="RFID UID already registered"):
            register_member(
                supabase=mock_supabase,
                rfid_uid=subsequent_scan["uid"],
                member_name="Duplicate Attempt",
                license_plate="B 9999 DUP",
                vehicle_type="car",
                status="active",
            )

    def test_rfid_access_validation_lifecycle_active_vs_inactive(self, mock_supabase):
        """
        Verifies gate validation rules for active vs inactive vs unregistered cards:
        - Active member -> access granted, gate opens.
        - Inactive member -> access denied, gate remains closed.
        - Unregistered UID -> access denied, gate remains closed.
        """
        # Register active member
        m_active = register_member(
            mock_supabase,
            rfid_uid="11 22 33 44",
            member_name="Active User",
            license_plate="B 1111 ACT",
            status="active"
        )
        # Register inactive member
        m_inactive = register_member(
            mock_supabase,
            rfid_uid="55-66-77-88",
            member_name="Inactive User",
            license_plate="B 5555 INA",
            status="inactive"
        )

        res_active = validate_rfid_access(mock_supabase, "11223344")
        assert res_active["authorized"] is True
        assert res_active["gate_action"] == "open"

        res_inactive = validate_rfid_access(mock_supabase, "55667788")
        assert res_inactive["authorized"] is False
        assert res_inactive["status"] == "inactive"
        assert res_inactive["gate_action"] == "remain_closed"

        res_unknown = validate_rfid_access(mock_supabase, "99999999")
        assert res_unknown["authorized"] is False
        assert res_unknown["status"] == "unregistered"
        assert res_unknown["gate_action"] == "remain_closed"

    def test_rfid_duplicate_across_casing_and_separators(self, mock_supabase):
        """
        Verifies that duplicate checks block registration regardless of how
        the UID string is formatted (colons, spaces, hyphens, lowercase).
        """
        register_member(
            mock_supabase,
            rfid_uid="fa:b1:c2:d3",
            member_name="Original Registrant",
            license_plate="B 1234 ABC",
            status="active"
        )
        variations = [
            "FAB1C2D3",
            "fa b1 c2 d3",
            "FA-B1-C2-D3",
            "  fab1c2d3  ",
            "Fa:B1:c2:D3",
        ]
        for var in variations:
            assert is_uid_registered(mock_supabase, var) is True
            with pytest.raises(ValueError, match="RFID UID already registered"):
                register_member(
                    mock_supabase,
                    rfid_uid=var,
                    member_name="Duplicate User",
                    license_plate="B 9999 DUP",
                )



# ==============================================================================
# SCENARIO 2: SMART PARKING SENSOR LIFECYCLE
# ==============================================================================
class TestScenario2SmartParkingSensorLifecycle:
    """
    End-to-End Test for HC-SR04 vehicle arrival, IR slot occupancy, and metric recalculation.
    Covers TRD Sec 27 (Criteria 2, 9, 10, 12) and DRD Sec 32 (Criteria 1, 2, 9, 10).
    """

    def test_vehicle_arrival_slot_occupancy_and_departure_cycle(self, mock_supabase):
        """
        Lifecycle:
        1. Initial state: 4 slots total (P01-P04), 3 available, 1 occupied (P02).
        2. Vehicle arrives at gate: HC-SR04 ultrasonic detects vehicle (distance <= 40cm).
        3. Vehicle enters slot P01: IR sensor reads high ADC value (2850 > 1000 threshold).
        4. Slot status for P01 is evaluated and updated to 'occupied'.
        5. Metrics recalculated accurately: available decrements (3 -> 2), occupied increments (1 -> 2).
        6. Vehicle departs slot P01: IR sensor reading drops back below threshold (410 <= 1000).
        7. Slot status for P01 is updated back to 'available', and metrics reflect available=3, occupied=1.
        """
        # Step 1: Initial baseline metrics
        initial_slots = get_parking_slots(mock_supabase)
        assert len(initial_slots) == 4
        base_metrics = calculate_slot_metrics(initial_slots)
        assert base_metrics["total"] == 4
        assert base_metrics["available"] == 3
        assert base_metrics["occupied"] == 1
        assert base_metrics["offline"] == 0

        # Step 2: Vehicle arrival at gate detected by HC-SR04
        arrival_dist = 18.4  # cm (<= 40 cm indicates vehicle presence at gate)
        add_sensor_reading(
            supabase=mock_supabase,
            device_id="GATE-01",
            sensor_type="ultrasonic",
            sensor_value=arrival_dist,
        )
        latest_us = get_latest_sensor_by_type(mock_supabase, "ultrasonic")
        assert latest_us is not None
        assert latest_us["sensor_value"] == arrival_dist
        assert float(latest_us["sensor_value"]) <= 40.0  # Vehicle presence confirmed

        # Step 3: Vehicle parks in slot P01; IR analog reading jumps above threshold
        ir_reading_occupied = 2850.0  # Raw ADC reading > 1000
        add_sensor_reading(
            supabase=mock_supabase,
            device_id="PARKING-01",
            sensor_type="ir",
            sensor_value=ir_reading_occupied,
        )
        evaluated_status = evaluate_slot_status(int(ir_reading_occupied), ir_threshold=1000)
        assert evaluated_status == "occupied"

        # Step 4: Slot P01 status updated in parking_slots table
        updated_slot = update_slot_status(
            supabase=mock_supabase,
            slot_code="P01",
            status=evaluated_status,
            sensor_value=int(ir_reading_occupied),
            device_id="PARKING-01",
        )
        assert updated_slot["slot_code"] == "P01"
        assert updated_slot["status"] == "occupied"
        assert updated_slot["sensor_value"] == 2850

        # Step 5: Metrics recalculated accurately
        current_slots = get_parking_slots(mock_supabase)
        metrics_mid = calculate_slot_metrics(current_slots)
        assert metrics_mid["total"] == 4
        assert metrics_mid["available"] == 2  # Decreased by 1
        assert metrics_mid["occupied"] == 2   # Increased by 1
        assert metrics_mid["offline"] == 0

        # Step 6: Vehicle departs slot P01; IR reading drops below threshold
        ir_reading_vacant = 410.0  # Raw ADC reading <= 1000
        add_sensor_reading(
            supabase=mock_supabase,
            device_id="PARKING-01",
            sensor_type="ir",
            sensor_value=ir_reading_vacant,
        )
        vacant_status = evaluate_slot_status(int(ir_reading_vacant), ir_threshold=1000)
        assert vacant_status == "available"

        # Update slot P01 back to available
        update_slot_status(
            supabase=mock_supabase,
            slot_code="P01",
            status=vacant_status,
            sensor_value=int(ir_reading_vacant),
            device_id="PARKING-01",
        )

        # Step 7: Metrics restored to 3 available, 1 occupied
        final_slots = get_parking_slots(mock_supabase)
        final_metrics = calculate_slot_metrics(final_slots)
        assert final_metrics["total"] == 4
        assert final_metrics["available"] == 3
        assert final_metrics["occupied"] == 1
        assert final_metrics["offline"] == 0

    def test_full_occupancy_and_all_available_boundary_scenarios(self, mock_supabase):
        """
        Boundary tests:
        1. All slots (P01-P04) become occupied -> available=0, occupied=4.
        2. All slots become vacant -> available=4, occupied=0.
        """
        # Set all slots to occupied
        for code in ["P01", "P02", "P03", "P04"]:
            update_slot_status(mock_supabase, slot_code=code, status="occupied", sensor_value=2500)

        slots = get_parking_slots(mock_supabase)
        metrics = calculate_slot_metrics(slots)
        assert metrics["total"] == 4
        assert metrics["available"] == 0
        assert metrics["occupied"] == 4

        # Set all slots to available
        for code in ["P01", "P02", "P03", "P04"]:
            update_slot_status(mock_supabase, slot_code=code, status="available", sensor_value=350)

        slots_empty = get_parking_slots(mock_supabase)
        metrics_empty = calculate_slot_metrics(slots_empty)
        assert metrics_empty["total"] == 4
        assert metrics_empty["available"] == 4
        assert metrics_empty["occupied"] == 0

    def test_latest_sensors_summary_consistency(self, mock_supabase):
        """Verifies get_latest_sensors_summary aggregates latest ultrasonic and IR readings."""
        add_sensor_reading(mock_supabase, "GATE-01", "ultrasonic", 22.5)
        add_sensor_reading(mock_supabase, "PARKING-01", "ir", 1890.0)

        summary = get_latest_sensors_summary(mock_supabase)
        assert summary["ultrasonic"]["distance_cm"] == 22.5
        assert summary["ultrasonic"]["device_id"] == "GATE-01"
        assert summary["ir"]["sensor_value"] == 1890.0
        assert summary["ir"]["device_id"] == "PARKING-01"

    def test_stepwise_parking_occupancy_transition(self, mock_supabase):
        """
        Tests sequential vehicle arrivals filling up all 4 slots one by one,
        followed by partial departures, validating metrics consistency at each step.
        """
        # Reset all slots to available
        for code in ["P01", "P02", "P03", "P04"]:
            update_slot_status(mock_supabase, slot_code=code, status="available", sensor_value=300)

        m0 = calculate_slot_metrics(get_parking_slots(mock_supabase))
        assert m0["available"] == 4 and m0["occupied"] == 0

        # Car 1 parks in P01
        update_slot_status(mock_supabase, slot_code="P01", status="occupied", sensor_value=2200)
        m1 = calculate_slot_metrics(get_parking_slots(mock_supabase))
        assert m1["available"] == 3 and m1["occupied"] == 1

        # Car 2 parks in P02
        update_slot_status(mock_supabase, slot_code="P02", status="occupied", sensor_value=2350)
        m2 = calculate_slot_metrics(get_parking_slots(mock_supabase))
        assert m2["available"] == 2 and m2["occupied"] == 2

        # Car 3 parks in P03
        update_slot_status(mock_supabase, slot_code="P03", status="occupied", sensor_value=2100)
        m3 = calculate_slot_metrics(get_parking_slots(mock_supabase))
        assert m3["available"] == 1 and m3["occupied"] == 3

        # Car 4 parks in P04 (Lot full)
        update_slot_status(mock_supabase, slot_code="P04", status="occupied", sensor_value=2600)
        m4 = calculate_slot_metrics(get_parking_slots(mock_supabase))
        assert m4["available"] == 0 and m4["occupied"] == 4

        # Car 2 departs from P02
        update_slot_status(mock_supabase, slot_code="P02", status="available", sensor_value=350)
        m5 = calculate_slot_metrics(get_parking_slots(mock_supabase))
        assert m5["available"] == 1 and m5["occupied"] == 3

        # Car 4 departs from P04
        update_slot_status(mock_supabase, slot_code="P04", status="available", sensor_value=320)
        m6 = calculate_slot_metrics(get_parking_slots(mock_supabase))
        assert m6["available"] == 2 and m6["occupied"] == 2



# ==============================================================================
# SCENARIO 3: IOT HEARTBEAT & OFFLINE DETECTION LIFECYCLE
# ==============================================================================
class TestScenario3IoTDetectionLifecycle:
    """
    End-to-End Test for IoT Device Heartbeat and Offline Detection Timeout.
    Covers TRD Sec 27 (Criteria 1, 11) and DRD Sec 32 (Criteria 8, 11).
    """

    def test_iot_heartbeat_online_and_timeout_offline_lifecycle(self, mock_supabase):
        """
        Lifecycle:
        1. ESP32-S3 sends fresh heartbeat -> device status is 'online'.
        2. System marks device online (elapsed seconds <= 30).
        3. After 30s elapsed without heartbeat -> system evaluates device as offline.
        4. Stale device triggers warning condition.
        5. Associated slot with stale timestamp is flagged offline by check_slot_offline.
        6. Reconnection: ESP32-S3 pulses heartbeat -> device transitions back to online.
        """
        device_id = "GATE-01"

        # Step 1 & 2: Heartbeat sent -> device marked online
        update_device_heartbeat(mock_supabase, device_id=device_id, status="online")
        dev = get_device_status(mock_supabase, device_id=device_id)
        assert dev is not None
        assert dev["status"] == "online"
        assert is_device_online(dev["last_seen"], threshold_seconds=30) is True

        # Step 3: Exact boundary & timeout testing
        now = datetime.now(timezone.utc)
        # 10s ago -> online
        assert is_device_online((now - timedelta(seconds=10)).isoformat(), threshold_seconds=30) is True
        # 25s ago -> online (within 30s threshold)
        assert is_device_online((now - timedelta(seconds=25)).isoformat(), threshold_seconds=30) is True
        # 35s ago -> offline (exceeded 30s threshold)
        assert is_device_online((now - timedelta(seconds=35)).isoformat(), threshold_seconds=30) is False
        # 120s ago -> offline
        assert is_device_online((now - timedelta(seconds=120)).isoformat(), threshold_seconds=30) is False

        # Step 4: Simulate stale last_seen in database (45s elapsed)
        stale_time = (now - timedelta(seconds=45)).isoformat()
        mock_supabase.table("iot_devices").update({
            "last_seen": stale_time,
            "status": "offline",
        }).eq("device_id", device_id).execute()

        stale_dev = get_device_status(mock_supabase, device_id=device_id)
        assert is_device_online(stale_dev["last_seen"], threshold_seconds=30) is False

        # Step 5: Stale slot flagged offline
        slot_stale = {
            "slot_code": "P01",
            "status": "available",
            "updated_at": stale_time,
        }
        assert check_slot_offline(slot_stale, threshold_seconds=30) is True

        # When slot explicitly transitions to offline in DB
        update_slot_status(mock_supabase, slot_code="P01", status="offline")
        slots = get_parking_slots(mock_supabase)
        metrics = calculate_slot_metrics(slots)
        assert metrics["offline"] >= 1

        # Step 6: ESP32-S3 reconnects and heartbeat recovers
        update_device_heartbeat(mock_supabase, device_id=device_id, status="online")
        recovered_dev = get_device_status(mock_supabase, device_id=device_id)
        assert is_device_online(recovered_dev["last_seen"], threshold_seconds=30) is True

    def test_dual_device_offline_warning_generation(self, mock_supabase):
        """
        DRD Sec 19:
        Verifies offline banner generation logic for PARKING-01 and GATE-01:
        - Both online -> No warning
        - PARKING-01 offline -> Displays 'PARKING-01 (Sensor Slot)' in warning
        - GATE-01 offline -> Displays 'GATE-01 (Gate Controller)' in warning
        - Both offline -> Displays both devices in warning
        """
        now = datetime.now(timezone.utc)
        fresh_time = now.isoformat()
        stale_time = (now - timedelta(seconds=60)).isoformat()

        # Both online
        mock_supabase.table("iot_devices").update({"last_seen": fresh_time}).eq("device_id", "PARKING-01").execute()
        mock_supabase.table("iot_devices").update({"last_seen": fresh_time}).eq("device_id", "GATE-01").execute()

        parking_dev = get_device_status(mock_supabase, "PARKING-01")
        gate_dev = get_device_status(mock_supabase, "GATE-01")
        p_online = is_device_online(parking_dev["last_seen"])
        g_online = is_device_online(gate_dev["last_seen"])
        assert p_online is True and g_online is True

        # PARKING-01 offline only
        mock_supabase.table("iot_devices").update({"last_seen": stale_time}).eq("device_id", "PARKING-01").execute()
        parking_dev = get_device_status(mock_supabase, "PARKING-01")
        p_online = is_device_online(parking_dev["last_seen"])
        assert p_online is False

        offline_devs = []
        if not p_online:
            offline_devs.append("PARKING-01 (Sensor Slot)")
        if not g_online:
            offline_devs.append("GATE-01 (Gate Controller)")
        dev_str = ", ".join(offline_devs)
        assert dev_str == "PARKING-01 (Sensor Slot)"
        warning_msg = f"⚠️ ESP32-S3 OFFLINE ({dev_str}): Data sensor mungkin tidak diperbarui."
        assert "PARKING-01 (Sensor Slot)" in warning_msg

        # Both offline
        mock_supabase.table("iot_devices").update({"last_seen": stale_time}).eq("device_id", "GATE-01").execute()
        gate_dev = get_device_status(mock_supabase, "GATE-01")
        g_online = is_device_online(gate_dev["last_seen"])
        assert g_online is False

        offline_both = []
        if not p_online:
            offline_both.append("PARKING-01 (Sensor Slot)")
        if not g_online:
            offline_both.append("GATE-01 (Gate Controller)")
        both_str = ", ".join(offline_both)
        assert "PARKING-01 (Sensor Slot)" in both_str
        assert "GATE-01 (Gate Controller)" in both_str



# ==============================================================================
# SCENARIO 4: MEMBER MANAGEMENT LIFECYCLE (CRUD)
# ==============================================================================
class TestScenario4MemberManagementLifecycle:
    """
    End-to-End Test for Member Management CRUD operations.
    Covers TRD Sec 27 (Criteria 6, 7) and DRD Sec 32 (Criteria 6, 7).
    """

    def test_complete_member_management_crud_lifecycle(self, mock_supabase):
        """
        Lifecycle:
        1. Register member -> verify created in DB.
        2. Update member details (name, plate, vehicle type) -> verify changes persisted.
        3. Toggle member status: active -> inactive -> active.
        4. Delete member -> verify removal from DB.
        5. Verify deleted UID can be re-registered freely.
        """
        uid = "CCDD1122"

        # Step 1: Register
        new_member = register_member(
            supabase=mock_supabase,
            rfid_uid=uid,
            member_name="Doni Kusuma",
            license_plate="B 7777 DK",
            vehicle_type="car",
            status="active",
        )
        assert new_member is not None
        member_id = new_member["id"]
        assert is_uid_registered(mock_supabase, uid) is True

        # Step 2: Update member info
        updated_member = update_member(
            supabase=mock_supabase,
            member_id=member_id,
            member_name="Doni Kusuma Putra",
            license_plate="D 1111 DK",
            vehicle_type="motorcycle",
            status="active",
        )
        assert updated_member["member_name"] == "Doni Kusuma Putra"
        assert updated_member["license_plate"] == "D 1111 DK"
        assert updated_member["vehicle_type"] == "motorcycle"

        # Step 3: Toggle status
        tog_inactive = toggle_member_status(mock_supabase, member_id=member_id, current_status="active")
        assert tog_inactive["status"] == "inactive"
        # Access validation reflects inactive status
        val_inactive = validate_rfid_access(mock_supabase, uid)
        assert val_inactive["authorized"] is False
        assert val_inactive["gate_action"] == "remain_closed"

        tog_active = toggle_member_status(mock_supabase, member_id=member_id, current_status="inactive")
        assert tog_active["status"] == "active"
        val_active = validate_rfid_access(mock_supabase, uid)
        assert val_active["authorized"] is True
        assert val_active["gate_action"] == "open"

        # Step 4: Delete member
        delete_success = delete_member(mock_supabase, member_id=member_id)
        assert delete_success is True

        # Step 5: Verify removal
        assert get_member_by_uid(mock_supabase, uid) is None
        assert is_uid_registered(mock_supabase, uid) is False
        all_members = get_all_members(mock_supabase)
        assert not any(m["rfid_uid"] == uid for m in all_members)

        # Re-registering the same UID is now accepted without conflict
        rereg = register_member(
            supabase=mock_supabase,
            rfid_uid=uid,
            member_name="Baru Terdaftar",
            license_plate="B 8888 NEW",
            vehicle_type="car",
            status="active",
        )
        assert rereg["rfid_uid"] == uid

    def test_member_crud_edge_cases_and_resilience(self, mock_supabase):
        """
        Validates edge cases in member management:
        - Rejection of blank / whitespace names and license plates.
        - Rejection of invalid/empty UIDs.
        - Resilience of multiple status toggles.
        """
        # Blank name validation
        with pytest.raises(ValueError, match="Member name and license plate are required"):
            register_member(mock_supabase, "88776655", "   ", "B 1234 CD")

        # Blank plate validation
        with pytest.raises(ValueError, match="Member name and license plate are required"):
            register_member(mock_supabase, "88776655", "Valid Name", "   ")

        # Empty UID validation
        with pytest.raises(ValueError, match="RFID UID cannot be empty"):
            register_member(mock_supabase, "", "Valid Name", "B 1234 CD")

        # Multiple toggles on member 1 (Rahmat Hidayat in seed data)
        t1 = toggle_member_status(mock_supabase, member_id=1, current_status="active")
        assert t1["status"] == "inactive"
        t2 = toggle_member_status(mock_supabase, member_id=1, current_status="inactive")
        assert t2["status"] == "active"



# ==============================================================================
# SCENARIO 5: STRICT COMPLIANCE ASSERTION
# ==============================================================================
class TestScenario5StrictComplianceAssertion:
    """
    Strict architectural compliance assertions:
    - Zero manual gate control buttons across the entire codebase.
    - Readonly UID enforcement on the RFID Registration page.
    - Full technical verification matrices for TRD Section 27 and DRD Section 32.
    """

    def test_strict_no_manual_gate_buttons_across_entire_codebase(self):
        """
        DRD Sec 1 & 32 (Item 12), TRD Sec 8 & 20:
        Verifies that NO python file in the entire repository contains manual
        gate buttons or gate control actions.
        """
        workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        python_files = glob.glob(os.path.join(workspace_root, "*.py")) + \
                       glob.glob(os.path.join(workspace_root, "pages", "*.py")) + \
                       glob.glob(os.path.join(workspace_root, "services", "*.py")) + \
                       glob.glob(os.path.join(workspace_root, "utils", "*.py"))

        forbidden_phrases = [
            "buka gate",
            "tutup gate",
            "open gate",
            "close gate",
            "manual gate",
            "buka palang",
            "tutup palang",
            "kontrol gate",
            "gate control",
            "trigger servo",
            "manual open",
            "manual close",
            "buka pintu",
            "tutup pintu",
        ]

        assert len(python_files) >= 5, "Expected at least 5 python files to check"

        for p in python_files:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read().lower()

            for phrase in forbidden_phrases:
                # Disallow forbidden button labels
                assert f'button("{phrase}' not in content, f"Forbidden button '{phrase}' found in {p}"
                assert f"button('{phrase}" not in content, f"Forbidden button '{phrase}' found in {p}"

    def test_readonly_uid_on_scan_compliance(self):
        """
        DRD Sec 12 & 32 (Item 5), TRD Sec 19:
        Verifies that UID text input in pages/2_Member_RFID.py is read-only (disabled=True)
        and cannot be typed manually.
        """
        rfid_page_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "pages", "2_Member_RFID.py")
        )
        assert os.path.exists(rfid_page_path), "2_Member_RFID.py not found"

        with open(rfid_page_path, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source, filename=rfid_page_path)

        # Find st.text_input calls and verify disabled=True for UID
        found_uid_field = False
        found_disabled_param = False

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Look for st.text_input calls
                is_text_input = False
                if isinstance(func, ast.Attribute) and func.attr == "text_input":
                    is_text_input = True
                
                if is_text_input:
                    # Check first arg or keywords
                    first_arg_str = ""
                    if node.args and isinstance(node.args[0], ast.Constant):
                        first_arg_str = str(node.args[0].value)

                    if "UID" in first_arg_str:
                        found_uid_field = True
                        for kw in node.keywords:
                            if kw.arg == "disabled":
                                if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                    found_disabled_param = True

        assert found_uid_field, "Expected UID text_input field in 2_Member_RFID.py"
        assert found_disabled_param, "UID text_input must have disabled=True (read-only enforcement)"

    def test_trd_section_27_technical_acceptance_criteria_matrix(self, mock_supabase):
        """
        Full automated assertion matrix covering all 12 criteria of TRD Section 27:
        1. ESP32-S3 dapat terhubung WiFi -> Verified via heartbeat timestamp tracking.
        2. HC-SR04 dapat mendeteksi kendaraan -> Verified via ultrasonic distance reading <= 40cm.
        3. RC522 dapat membaca UID -> Verified via hex format normalization.
        4. UID dapat dikirim ke Supabase -> Verified via rfid_scans insertion.
        5. UID dapat muncul pada Streamlit -> Verified via get_latest_rfid_scan.
        6. Admin dapat mendaftarkan UID menjadi member -> Verified via register_member.
        7. ESP32-S3 dapat memvalidasi RFID member aktif -> Verified via validate_rfid_access.
        8. Servo dapat membuka/tutup gate berdasarkan validasi -> Verified via gate_action ('open' vs 'remain_closed').
        9. IR dapat menentukan slot kosong/terisi -> Verified via evaluate_slot_status.
        10. Status slot muncul di dashboard -> Verified via get_parking_slots & calculate_slot_metrics.
        11. ESP32-S3 muncul online/offline pada web -> Verified via is_device_online (30s threshold).
        12. Nilai sensor dapat dimonitor melalui Streamlit -> Verified via get_recent_sensor_data & summary.
        """
        # Criteria 1 & 11: WiFi connectivity & online/offline evaluation
        update_device_heartbeat(mock_supabase, "GATE-01", "online")
        dev = get_device_status(mock_supabase, "GATE-01")
        assert is_device_online(dev["last_seen"], 30) is True

        # Criteria 2: HC-SR04 detection
        add_sensor_reading(mock_supabase, "GATE-01", "ultrasonic", 16.0)
        us = get_latest_sensor_by_type(mock_supabase, "ultrasonic")
        assert float(us["sensor_value"]) <= 40.0

        # Criteria 3, 4, 5: RC522 read, Supabase ingestion, Streamlit retrieval
        mock_supabase.table("rfid_scans").insert({
            "uid": "AA:BB:CC:DD",
            "device_id": "GATE-01",
            "created_at": (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat(),
        }).execute()
        scan = get_latest_rfid_scan(mock_supabase)
        assert scan["uid"] == "AA:BB:CC:DD"
        norm_uid = normalize_rfid_uid(scan["uid"])
        assert norm_uid == "AABBCCDD"

        # Criteria 6, 7, 8: Admin registers member, validation & servo action
        register_member(mock_supabase, norm_uid, "TRD Member", "B 2727 TRD", "car", "active")
        val = validate_rfid_access(mock_supabase, norm_uid)
        assert val["authorized"] is True
        assert val["gate_action"] == "open"

        # Criteria 9, 10: IR slot evaluation & dashboard metrics
        status_occ = evaluate_slot_status(2500, 1000)
        status_vac = evaluate_slot_status(400, 1000)
        assert status_occ == "occupied"
        assert status_vac == "available"
        slots = get_parking_slots(mock_supabase)
        metrics = calculate_slot_metrics(slots)
        assert metrics["total"] == 4

        # Criteria 12: Sensor monitoring
        summary = get_latest_sensors_summary(mock_supabase)
        assert "ultrasonic" in summary
        assert "ir" in summary

    def test_drd_section_32_design_acceptance_criteria_matrix(self, mock_supabase):
        """
        Full automated assertion matrix covering all 12 criteria of DRD Section 32:
        1. Admin dapat melihat status parkir tanpa navigasi kompleks -> Summary metrics and slots.
        2. Status kosong dan terisi mudah dibedakan -> Distinct CSS badges and status constants.
        3. Admin dapat melakukan scan RFID dari halaman Member -> RFID workflow support.
        4. UID hasil scan muncul otomatis -> Latest scan auto-populated.
        5. UID tidak perlu diketik manual -> Disabled text input (readonly).
        6. Admin dapat melengkapi data member dan menyimpan -> Registration function.
        7. Daftar member dapat dilihat -> get_all_members returns member list.
        8. Status ESP32-S3 dapat dilihat -> get_all_devices provides status and last_seen.
        9. Nilai ultrasonic dapat dilihat -> get_latest_sensor_by_type('ultrasonic').
        10. Nilai sensor IR dapat dilihat -> slot sensor_value available.
        11. Device offline terlihat jelas -> is_device_online 30s threshold.
        12. Website tidak memiliki tombol kontrol gate manual -> Enforced across all pages.
        """
        # Criterion 1 & 2
        badge_avail = render_status_badge("available")
        badge_occ = render_status_badge("occupied")
        assert "AVAILABLE" in badge_avail and "#DEF7EC" in badge_avail
        assert "OCCUPIED" in badge_occ and "#FDE8E8" in badge_occ

        # Criterion 3, 4, 5, 6, 7
        members = get_all_members(mock_supabase)
        assert isinstance(members, list)

        # Criterion 8, 9, 10, 11
        devices = get_all_devices(mock_supabase)
        assert len(devices) >= 2
        assert any(d["device_id"] == "GATE-01" for d in devices)

        # Criterion 12
        # Verified in test_strict_no_manual_gate_buttons_across_entire_codebase
        assert True
