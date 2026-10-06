"""
Unit test suite for Anti-Passback Algorithm and Forensic Audit Service.
Verifies inside_parking tracking, anti-passback violation rejection,
photo snapshot generation, forensic audit logging, and tailgating detection.
"""

import pytest
from services.audit_service import (
    generate_vehicle_snapshot_svg,
    log_audit_event,
    get_audit_logs,
    process_gate_entry,
    process_gate_exit,
    report_tailgating,
)
from services.member_service import (
    register_member,
    set_member_inside_parking,
    reset_all_passback,
    validate_rfid_access,
    get_member_by_uid,
)


class TestAntiPassbackAlgorithm:
    """Test suite verifying Anti-Passback rules."""

    def test_first_entry_granted_and_updates_inside_flag(self, mock_supabase):
        """Card outside can enter, and inside_parking is updated to True."""
        # Member 1 (A3F21C12) is active and inside_parking is False initially
        member_before = get_member_by_uid(mock_supabase, "A3F21C12")
        assert member_before["inside_parking"] is False

        entry_res = process_gate_entry(mock_supabase, "A3F21C12", device_id="GATE-01")
        assert entry_res["authorized"] is True
        assert entry_res["gate_action"] == "open"
        assert entry_res["status"] == "active"
        assert entry_res["photo_url"] is not None

        member_after = get_member_by_uid(mock_supabase, "A3F21C12")
        assert member_after["inside_parking"] is True

    def test_second_consecutive_entry_rejected_by_anti_passback(self, mock_supabase):
        """Card already inside is denied entry when tapped again."""
        # Set member 1 inside parking
        set_member_inside_parking(mock_supabase, 1, inside=True)

        entry_res = process_gate_entry(mock_supabase, "A3F21C12", device_id="GATE-01")
        assert entry_res["authorized"] is False
        assert entry_res["gate_action"] == "remain_closed"
        assert entry_res["status"] == "anti_passback_violation"
        assert "Anti-Passback" in entry_res.get("reason", "")
        assert entry_res["audit_log"]["event_type"] == "anti_passback_violation"

    def test_exit_allows_subsequent_entry(self, mock_supabase):
        """Card inside can exit, resetting inside_parking to False, allowing next entry."""
        # Member enters
        process_gate_entry(mock_supabase, "A3F21C12", device_id="GATE-01")
        assert get_member_by_uid(mock_supabase, "A3F21C12")["inside_parking"] is True

        # Member exits
        exit_res = process_gate_exit(mock_supabase, "A3F21C12", device_id="GATE-01")
        assert exit_res["authorized"] is True
        assert exit_res["gate_action"] == "open"
        assert exit_res["status"] == "exit_granted"
        assert get_member_by_uid(mock_supabase, "A3F21C12")["inside_parking"] is False

        # Member enters again - should succeed!
        second_entry = process_gate_entry(mock_supabase, "A3F21C12", device_id="GATE-01")
        assert second_entry["authorized"] is True
        assert second_entry["gate_action"] == "open"

    def test_exit_without_entry_violation(self, mock_supabase):
        """Card outside attempting to exit triggers anti_passback_exit_violation."""
        val = validate_rfid_access(mock_supabase, "A3F21C12", direction="exit")
        assert val["authorized"] is False
        assert val["status"] == "anti_passback_exit_violation"
        assert val["gate_action"] == "remain_closed"

    def test_reset_all_passback(self, mock_supabase):
        """Admin emergency reset sets all members outside."""
        set_member_inside_parking(mock_supabase, 1, inside=True)
        set_member_inside_parking(mock_supabase, 2, inside=True)

        assert get_member_by_uid(mock_supabase, "A3F21C12")["inside_parking"] is True
        assert get_member_by_uid(mock_supabase, "B4E22D33")["inside_parking"] is True

        reset_all_passback(mock_supabase)

        assert get_member_by_uid(mock_supabase, "A3F21C12")["inside_parking"] is False
        assert get_member_by_uid(mock_supabase, "B4E22D33")["inside_parking"] is False


class TestForensicAuditAndTailgating:
    """Test suite verifying vehicle snapshot, forensic logs, and tailgating alerts."""

    def test_vehicle_snapshot_svg_generation(self):
        """Generates valid base64 data URI SVG containing vehicle and plate info."""
        svg_uri = generate_vehicle_snapshot_svg(
            license_plate="BG 9999 XX",
            vehicle_type="car",
            event_type="entry_granted",
            camera_id="CAM-GATE-01"
        )
        assert svg_uri.startswith("data:image/svg+xml;base64,")

    def test_tailgating_incident_reporting(self, mock_supabase):
        """Reports a tailgating detection event and verifies forensic audit log."""
        log = report_tailgating(
            supabase=mock_supabase,
            device_id="GATE-01",
            details="Kendaraan membuntuti tanpa tap kartu!"
        )
        assert log["event_type"] == "tailgating_detected"
        assert log["tailgating_detected"] is True
        assert log["device_id"] == "GATE-01"
        assert "TAILGATING" in log["license_plate"]

        # Verify log retrieval with tailgating_only filter
        tailgate_logs = get_audit_logs(mock_supabase, tailgating_only=True)
        assert len(tailgate_logs) >= 1
        assert tailgate_logs[0]["tailgating_detected"] is True

    def test_unauthorized_scan_logs_security_event(self, mock_supabase):
        """Scanning an unregistered card creates an unauthorized audit log."""
        res = process_gate_entry(mock_supabase, "UNKNOWN99", device_id="GATE-01")
        assert res["authorized"] is False
        assert res["gate_action"] == "remain_closed"
        assert res["audit_log"]["event_type"] == "unauthorized_scan"
