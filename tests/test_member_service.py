"""
Unit tests for member_service module.
Tests cover:
- UID normalization (e.g. 'a3 f2 1c 12' -> 'A3F21C12')
- Duplicate UID checks (DRD Section 12)
- Member registration with validation
- Member status toggling (active <-> inactive)
- Updating and deleting member records
- Fetching the latest RFID scan from rfid_scans
"""

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
)


class TestRfidNormalization:
    """Test suite for RFID UID normalization rules."""

    def test_normalize_rfid_uid_space_separated(self):
        """TRD Sec 7.1: 'a3 f2 1c 12' must become 'A3F21C12'."""
        assert normalize_rfid_uid("a3 f2 1c 12") == "A3F21C12"

    def test_normalize_rfid_uid_colon_separated(self):
        """Colons in hex representation like 'a3:f2:1c:12' must be stripped and uppercased."""
        assert normalize_rfid_uid("a3:f2:1c:12") == "A3F21C12"

    def test_normalize_rfid_uid_dash_separated(self):
        """Hyphens in hex representation like 'a3-f2-1c-12' must be stripped."""
        assert normalize_rfid_uid("a3-f2-1c-12") == "A3F21C12"

    def test_normalize_rfid_uid_already_normalized(self):
        """Already uppercase hex string remains unchanged."""
        assert normalize_rfid_uid("A3F21C12") == "A3F21C12"

    def test_normalize_rfid_uid_strips_outer_whitespace(self):
        """Leading and trailing spaces should be removed."""
        assert normalize_rfid_uid("   b4e22d33  ") == "B4E22D33"

    @pytest.mark.parametrize("invalid_uid", ["", "   ", None])
    def test_normalize_rfid_uid_invalid_empty_raises_error(self, invalid_uid):
        """Empty, whitespace-only, or None UID should raise ValueError."""
        with pytest.raises(ValueError, match="RFID UID cannot be empty"):
            normalize_rfid_uid(invalid_uid)


class TestMemberRegistrationAndDuplicateCheck:
    """Test suite for member registration and duplicate checking."""

    def test_is_uid_registered_true_for_existing(self, mock_supabase):
        """Existing UID 'A3F21C12' in seed data should return True."""
        assert is_uid_registered(mock_supabase, "A3F21C12") is True

    def test_is_uid_registered_case_insensitive(self, mock_supabase):
        """Existing UID should be matched regardless of casing or spacing."""
        assert is_uid_registered(mock_supabase, "a3 f2 1c 12") is True

    def test_is_uid_registered_false_for_new(self, mock_supabase):
        """Non-existing UID should return False."""
        assert is_uid_registered(mock_supabase, "FF998877") is False

    def test_register_member_success(self, mock_supabase):
        """New member registration should normalize UID, insert to DB, and return member dict."""
        new_uid = "99 aa bb cc"
        result = register_member(
            supabase=mock_supabase,
            rfid_uid=new_uid,
            member_name="Ahmad Yani",
            license_plate="B 1010 ABC",
            vehicle_type="car",
            status="active"
        )
        assert result["rfid_uid"] == "99AABBCC"
        assert result["member_name"] == "Ahmad Yani"
        assert result["license_plate"] == "B 1010 ABC"
        assert result["vehicle_type"] == "car"
        assert result["status"] == "active"
        assert "id" in result

        # Verify member can be fetched now
        fetched = get_member_by_uid(mock_supabase, "99AABBCC")
        assert fetched is not None
        assert fetched["member_name"] == "Ahmad Yani"

    def test_register_member_duplicate_uid_raises_error(self, mock_supabase):
        """DRD Sec 12: Duplicate UID registration must be prevented."""
        with pytest.raises(ValueError, match="RFID UID already registered"):
            register_member(
                supabase=mock_supabase,
                rfid_uid="A3F21C12",  # Already in seed data
                member_name="Duplicate User",
                license_plate="B 9999 DUP"
            )

    def test_register_member_validation_missing_name_or_plate(self, mock_supabase):
        """Registering with empty name or license plate should raise ValueError."""
        with pytest.raises(ValueError, match="Member name and license plate are required"):
            register_member(
                supabase=mock_supabase,
                rfid_uid="EE112233",
                member_name="",
                license_plate="B 1234 XY"
            )

        with pytest.raises(ValueError, match="Member name and license plate are required"):
            register_member(
                supabase=mock_supabase,
                rfid_uid="EE112233",
                member_name="Valid Name",
                license_plate="   "
            )


class TestMemberCrudOperations:
    """Test suite for member retrieval, updates, and deletion."""

    def test_get_all_members(self, mock_supabase):
        """Fetches list of members sorted properly."""
        members = get_all_members(mock_supabase)
        assert isinstance(members, list)
        assert len(members) >= 3
        # Verify fields
        first = members[0]
        for field in ["id", "rfid_uid", "member_name", "license_plate", "status"]:
            assert field in first

    def test_get_member_by_uid_found(self, mock_supabase):
        """Returns member dict when UID exists."""
        member = get_member_by_uid(mock_supabase, "A3F21C12")
        assert member is not None
        assert member["member_name"] == "Rahmat Hidayat"

    def test_get_member_by_uid_not_found(self, mock_supabase):
        """Returns None when UID does not exist."""
        member = get_member_by_uid(mock_supabase, "NOTFOUND00")
        assert member is None

    def test_update_member_success(self, mock_supabase):
        """Updates member information successfully."""
        updated = update_member(
            supabase=mock_supabase,
            member_id=1,
            member_name="Rahmat Hidayat M.Sc",
            license_plate="BG 1234 RH",
            vehicle_type="car",
            status="active"
        )
        assert updated["member_name"] == "Rahmat Hidayat M.Sc"

    def test_toggle_member_status_active_to_inactive(self, mock_supabase):
        """Toggles an active member to inactive."""
        # Member 1 is active
        updated = toggle_member_status(mock_supabase, member_id=1, current_status="active")
        assert updated["status"] == "inactive"

    def test_toggle_member_status_inactive_to_active(self, mock_supabase):
        """Toggles an inactive member to active."""
        # Member 3 is inactive in seed data
        updated = toggle_member_status(mock_supabase, member_id=3, current_status="inactive")
        assert updated["status"] == "active"

    def test_delete_member_success(self, mock_supabase):
        """Deletes a member from database by id."""
        success = delete_member(mock_supabase, member_id=2)
        assert success is True
        # Verify member no longer exists
        remaining_members = get_all_members(mock_supabase)
        assert all(m["id"] != 2 for m in remaining_members)


class TestRfidScans:
    """Test suite for fetching recent RFID scans."""

    def test_get_latest_rfid_scan_returns_latest(self, mock_supabase):
        """Fetches the latest RFID scan from rfid_scans table."""
        latest = get_latest_rfid_scan(mock_supabase)
        assert latest is not None
        assert "uid" in latest
        assert "device_id" in latest
        assert "created_at" in latest
        # In seed data, D6A44B55 is the most recent (1 min ago)
        assert latest["uid"] == "D6A44B55"

    def test_get_latest_rfid_scan_empty_table(self, mock_supabase):
        """Returns None if table has no scans."""
        mock_supabase.set_table("rfid_scans", [])
        latest = get_latest_rfid_scan(mock_supabase)
        assert latest is None

    def test_get_latest_rfid_scan_filtered_by_device(self, mock_supabase):
        """Fetches the latest RFID scan filtered by device_id."""
        # Insert a scan for a specific student device
        mock_supabase.table("rfid_scans").insert({
            "uid": "E5F6A7B8",
            "device_id": "DEV-SISWA-01",
        }).execute()
        # Querying specifically for GATE-01 should not return the DEV-SISWA-01 scan
        gate_scan = get_latest_rfid_scan(mock_supabase, device_id="GATE-01")
        assert gate_scan is not None
        assert gate_scan["device_id"] == "GATE-01"
        assert gate_scan["uid"] == "D6A44B55"

        # Querying specifically for DEV-SISWA-01 should return the new scan
        student_scan = get_latest_rfid_scan(mock_supabase, device_id="DEV-SISWA-01")
        assert student_scan is not None
        assert student_scan["device_id"] == "DEV-SISWA-01"
        assert student_scan["uid"] == "E5F6A7B8"

    def test_get_latest_rfid_scan_filtered_no_match(self, mock_supabase):
        """Returns None if no scans match the specified device_id."""
        scan = get_latest_rfid_scan(mock_supabase, device_id="NON_EXISTENT_DEV")
        assert scan is None

