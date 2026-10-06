"""
Sensor service module for Smart Parking Monitoring.
Handles queries for HC-SR04 ultrasonic and IR sensor logs, latest sensor readings,
and ingesting new sensor measurements.
"""

from typing import Optional, List, Dict, Any

VALID_SENSOR_TYPES = {"ultrasonic", "ir"}
# Ambang batas jarak ultrasonic deteksi mobil di gerbang (cm) - sesuai firmware ESP32
CAR_DETECTION_DISTANCE_CM = 20.0


def get_recent_sensor_data(supabase: Any, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fetches the most recent sensor logs from sensor_data, ordered by created_at desc.
    """
    try:
        res = supabase.table("sensor_data").select("*").order("created_at", desc=True).limit(limit).execute()
        return res.data if res.data else []
    except Exception:
        return []


def get_latest_sensor_by_type(
    supabase: Any,
    sensor_type: str,
    device_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Fetches the latest reading for a specific sensor type (e.g. 'ultrasonic' or 'ir').
    """
    try:
        query = supabase.table("sensor_data").select("*").eq("sensor_type", sensor_type)
        if device_id:
            query = query.eq("device_id", device_id)
        res = query.order("created_at", desc=True).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception:
        pass
    return None


def get_latest_sensors_summary(supabase: Any) -> Dict[str, Any]:
    """
    Aggregates the latest sensor values across ultrasonic and IR sensors.
    """
    ultrasonic = get_latest_sensor_by_type(supabase, "ultrasonic")
    ir = get_latest_sensor_by_type(supabase, "ir")

    summary: Dict[str, Any] = {}
    if ultrasonic:
        summary["ultrasonic"] = {
            "distance_cm": ultrasonic.get("sensor_value"),
            "device_id": ultrasonic.get("device_id"),
            "created_at": ultrasonic.get("created_at"),
        }
    else:
        summary["ultrasonic"] = {
            "distance_cm": None,
            "device_id": None,
            "created_at": None,
        }

    if ir:
        summary["ir"] = {
            "sensor_value": ir.get("sensor_value"),
            "device_id": ir.get("device_id"),
            "created_at": ir.get("created_at"),
        }
    else:
        summary["ir"] = {
            "sensor_value": None,
            "device_id": None,
            "created_at": None,
        }

    return summary


def add_sensor_reading(
    supabase: Any,
    device_id: str,
    sensor_type: str,
    sensor_value: float
) -> Dict[str, Any]:
    """
    Inserts a new sensor reading into sensor_data table.
    Validates sensor_type in ('ultrasonic', 'ir') and non-negative sensor_value.
    """
    if sensor_type not in VALID_SENSOR_TYPES:
        raise ValueError(f"Invalid sensor type: '{sensor_type}'. Must be one of {VALID_SENSOR_TYPES}")

    if sensor_value < 0:
        raise ValueError("Sensor value cannot be negative")

    payload: Dict[str, Any] = {
        "device_id": device_id,
        "sensor_type": sensor_type,
        "sensor_value": float(sensor_value),
    }

    res = supabase.table("sensor_data").insert(payload).execute()
    return res.data[0] if isinstance(res.data, list) else res.data


def delete_sensor_reading(supabase: Any, reading_id: int) -> bool:
    """
    Deletes a specific sensor reading by ID.
    """
    try:
        supabase.table("sensor_data").delete().eq("id", reading_id).execute()
        return True
    except Exception:
        return False


def clear_sensor_data_by_device(supabase: Any, device_id: str) -> bool:
    """
    Clears all sensor data readings recorded for a specific device.
    """
    try:
        supabase.table("sensor_data").delete().eq("device_id", device_id).execute()
        return True
    except Exception:
        return False

