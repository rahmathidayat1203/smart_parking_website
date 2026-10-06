"""
Unit tests for sensor_service module.
Tests cover:
- Fetching recent sensor data (ultrasonic, IR)
- Fetching latest sensor reading by type and device
- Aggregating latest sensor summary for dashboard
- Adding sensor readings with input validation
"""

import pytest
from services.sensor_service import (
    get_recent_sensor_data,
    get_latest_sensor_by_type,
    get_latest_sensors_summary,
    add_sensor_reading,
)


class TestGetRecentSensorData:
    """Test suite for fetching sensor history."""

    def test_get_recent_sensor_data_default_limit(self, mock_supabase):
        """Fetches recent sensor records up to limit."""
        data = get_recent_sensor_data(mock_supabase, limit=10)
        assert isinstance(data, list)
        assert len(data) >= 5
        # Verify structure
        first = data[0]
        for field in ["id", "device_id", "sensor_type", "sensor_value", "created_at"]:
            assert field in first

    def test_get_recent_sensor_data_with_custom_limit(self, mock_supabase):
        """Respects custom limit parameter."""
        data = get_recent_sensor_data(mock_supabase, limit=2)
        assert len(data) == 2


class TestGetLatestSensorByType:
    """Test suite for retrieving the latest reading for a sensor type."""

    def test_get_latest_sensor_by_type_ultrasonic(self, mock_supabase):
        """Fetches latest ultrasonic distance measurement."""
        latest = get_latest_sensor_by_type(mock_supabase, sensor_type="ultrasonic")
        assert latest is not None
        assert latest["sensor_type"] == "ultrasonic"
        assert latest["sensor_value"] == 18.5
        assert latest["device_id"] == "GATE-01"

    def test_get_latest_sensor_by_type_ir(self, mock_supabase):
        """Fetches latest IR sensor reading."""
        latest = get_latest_sensor_by_type(mock_supabase, sensor_type="ir")
        assert latest is not None
        assert latest["sensor_type"] == "ir"
        assert isinstance(latest["sensor_value"], (int, float))

    def test_get_latest_sensor_by_type_not_found(self, mock_supabase):
        """Returns None when sensor type does not exist."""
        latest = get_latest_sensor_by_type(mock_supabase, sensor_type="temperature")
        assert latest is None


class TestLatestSensorsSummary:
    """Test suite for aggregated sensor summary (DRD Sec 7 & 15)."""

    def test_get_latest_sensors_summary(self, mock_supabase):
        """Summarizes ultrasonic distance and slot IR values."""
        summary = get_latest_sensors_summary(mock_supabase)
        assert isinstance(summary, dict)
        assert "ultrasonic" in summary
        assert summary["ultrasonic"]["distance_cm"] == 18.5

    def test_car_detection_distance_threshold(self):
        """Ambang batas deteksi kendaraan HC-SR04 adalah 20.0 cm sesuai ESP32 firmware."""
        from services.sensor_service import CAR_DETECTION_DISTANCE_CM
        assert CAR_DETECTION_DISTANCE_CM == 20.0


class TestAddSensorReading:
    """Test suite for inserting new sensor data."""

    def test_add_sensor_reading_valid(self, mock_supabase):
        """Inserts a new ultrasonic reading."""
        result = add_sensor_reading(
            supabase=mock_supabase,
            device_id="GATE-01",
            sensor_type="ultrasonic",
            sensor_value=25.4
        )
        assert result["device_id"] == "GATE-01"
        assert result["sensor_type"] == "ultrasonic"
        assert result["sensor_value"] == 25.4
        assert "id" in result

        # Verify it is returned as latest ultrasonic reading
        latest = get_latest_sensor_by_type(mock_supabase, "ultrasonic")
        assert latest["sensor_value"] == 25.4

    def test_add_sensor_reading_invalid_type_raises_error(self, mock_supabase):
        """Rejects unknown sensor types."""
        with pytest.raises(ValueError, match="Invalid sensor type"):
            add_sensor_reading(
                supabase=mock_supabase,
                device_id="GATE-01",
                sensor_type="invalid_type",
                sensor_value=10.0
            )

    def test_add_sensor_reading_invalid_negative_value(self, mock_supabase):
        """Rejects invalid negative sensor measurements."""
        with pytest.raises(ValueError, match="Sensor value cannot be negative"):
            add_sensor_reading(
                supabase=mock_supabase,
                device_id="GATE-01",
                sensor_type="ultrasonic",
                sensor_value=-5.0
            )
