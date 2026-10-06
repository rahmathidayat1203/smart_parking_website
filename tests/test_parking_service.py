"""
Unit tests for parking_service module.
Tests cover:
- Fetching parking slots
- Calculating summary metrics (total, available, occupied)
- Updating slot status and sensor values
- Offline slot logic and threshold evaluation
"""

from datetime import datetime, timezone, timedelta
import pytest
from services.parking_service import (
    get_parking_slots,
    calculate_slot_metrics,
    update_slot_status,
    check_slot_offline,
    evaluate_slot_status,
    get_slots_by_device,
    assign_slots_to_device,
)


class TestGetParkingSlots:
    """Test suite for fetching parking slot records."""

    def test_get_parking_slots_returns_all_four(self, mock_supabase):
        """TRD Sec 13.3 & DRD Sec 5.2: Should return 4 parking slots (P01-P04)."""
        slots = get_parking_slots(mock_supabase)
        assert len(slots) == 4
        codes = [s["slot_code"] for s in slots]
        assert codes == ["P01", "P02", "P03", "P04"]

    def test_get_parking_slots_empty(self, mock_supabase):
        """Returns empty list when no slots exist."""
        mock_supabase.set_table("parking_slots", [])
        slots = get_parking_slots(mock_supabase)
        assert slots == []


class TestCalculateSlotMetrics:
    """Test suite for parking summary metrics calculations."""

    def test_calculate_slot_metrics_sample_data(self, sample_slots):
        """With 3 available and 1 occupied slot: total=4, available=3, occupied=1, offline=0."""
        metrics = calculate_slot_metrics(sample_slots)
        assert metrics["total"] == 4
        assert metrics["available"] == 3
        assert metrics["occupied"] == 1
        assert metrics["offline"] == 0

    def test_calculate_slot_metrics_with_offline_status(self):
        """Handles slots explicitly marked as offline."""
        slots = [
            {"slot_code": "P01", "status": "available"},
            {"slot_code": "P02", "status": "occupied"},
            {"slot_code": "P03", "status": "offline"},
        ]
        metrics = calculate_slot_metrics(slots)
        assert metrics["total"] == 3
        assert metrics["available"] == 1
        assert metrics["occupied"] == 1
        assert metrics["offline"] == 1

    def test_calculate_slot_metrics_empty(self):
        """Handles empty slots list gracefully."""
        metrics = calculate_slot_metrics([])
        assert metrics["total"] == 0
        assert metrics["available"] == 0
        assert metrics["occupied"] == 0
        assert metrics["offline"] == 0


class TestUpdateSlotStatus:
    """Test suite for slot status and sensor updates."""

    def test_update_slot_status_valid(self, mock_supabase):
        """Updates slot P01 from available to occupied."""
        updated = update_slot_status(
            supabase=mock_supabase,
            slot_code="P01",
            status="occupied",
            sensor_value=2200,
            device_id="PARKING-01"
        )
        assert updated["slot_code"] == "P01"
        assert updated["status"] == "occupied"
        assert updated["sensor_value"] == 2200

        # Verify change persists in DB
        slots = get_parking_slots(mock_supabase)
        p01 = next(s for s in slots if s["slot_code"] == "P01")
        assert p01["status"] == "occupied"
        assert p01["sensor_value"] == 2200

    def test_update_slot_status_invalid_status_raises_error(self, mock_supabase):
        """Status must be 'available', 'occupied', or 'offline'."""
        with pytest.raises(ValueError, match="Invalid slot status"):
            update_slot_status(
                supabase=mock_supabase,
                slot_code="P01",
                status="unknown_status"
            )

    def test_update_slot_status_nonexistent_slot_raises_error(self, mock_supabase):
        """Updating non-existent slot code should raise ValueError."""
        with pytest.raises(ValueError, match="Slot code not found"):
            update_slot_status(
                supabase=mock_supabase,
                slot_code="P99",
                status="available"
            )


class TestOfflineSlotLogic:
    """Test suite for offline slot logic."""

    def test_check_slot_offline_recent_update(self):
        """Slot updated 5 seconds ago is NOT offline (threshold=30s)."""
        now = datetime.now(timezone.utc)
        slot = {
            "slot_code": "P01",
            "status": "available",
            "updated_at": (now - timedelta(seconds=5)).isoformat()
        }
        assert check_slot_offline(slot, threshold_seconds=30) is False

    def test_check_slot_offline_exceeded_threshold(self):
        """Slot updated 45 seconds ago IS offline (threshold=30s)."""
        now = datetime.now(timezone.utc)
        slot = {
            "slot_code": "P01",
            "status": "available",
            "updated_at": (now - timedelta(seconds=45)).isoformat()
        }
        assert check_slot_offline(slot, threshold_seconds=30) is True

    def test_check_slot_offline_no_timestamp(self):
        """Slot without updated_at is considered offline."""
        slot = {"slot_code": "P01", "status": "available", "updated_at": None}
        assert check_slot_offline(slot, threshold_seconds=30) is True

    def test_check_slot_offline_status_already_offline(self):
        """Slot with status='offline' is considered offline regardless of timestamp."""
        slot = {"slot_code": "P01", "status": "offline", "updated_at": datetime.now(timezone.utc).isoformat()}
        assert check_slot_offline(slot, threshold_seconds=30) is True


class TestEvaluateSlotStatus:
    """Test suite for evaluating slot status based on IR sensor reading."""

    def test_evaluate_slot_status_occupied(self):
        """IR value above threshold (e.g. 1000) indicates occupied vehicle."""
        assert evaluate_slot_status(sensor_value=2150, ir_threshold=1000) == "occupied"

    def test_evaluate_slot_status_available(self):
        """IR value below threshold indicates empty slot."""
        assert evaluate_slot_status(sensor_value=450, ir_threshold=1000) == "available"

    def test_evaluate_slot_status_none_sensor_value(self):
        """Missing sensor reading defaults to 'available' or 'offline'."""
        assert evaluate_slot_status(sensor_value=None) == "available"

    def test_evaluate_slot_status_digital_ir_low_occupied(self):
        """Digital IR obstacle sensor with Active-LOW logic (0 = vehicle detected)."""
        assert evaluate_slot_status(sensor_value=0) == "occupied"

    def test_evaluate_slot_status_digital_ir_high_available(self):
        """Digital IR obstacle sensor with Active-LOW logic (1 = slot is clear/available)."""
        assert evaluate_slot_status(sensor_value=1) == "available"


class TestDeviceSlots:
    """Test suite for device-specific parking slots."""

    def test_get_slots_by_device(self, mock_supabase):
        """Verifies filtering slots by device_id."""
        slots = get_slots_by_device(mock_supabase, "PARKING-01")
        assert len(slots) >= 1
        for s in slots:
            assert s["device_id"] == "PARKING-01"

    def test_assign_slots_to_device(self, mock_supabase):
        """Verifies reassigning slots to a new device_id."""
        success = assign_slots_to_device(mock_supabase, ["P01", "P02"], "DEV-SISWA-01")
        assert success is True

        assigned = get_slots_by_device(mock_supabase, "DEV-SISWA-01")
        assigned_codes = [s["slot_code"] for s in assigned]
        assert "P01" in assigned_codes
        assert "P02" in assigned_codes

