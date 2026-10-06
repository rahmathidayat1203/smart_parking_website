"""
Parking service module for Smart Parking Monitoring System.
Handles parking slot queries, metrics calculations (total, available, occupied, offline),
slot status updates, and sensor evaluation logic.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

VALID_SLOT_STATUSES = {"available", "occupied", "offline"}


def get_parking_slots(supabase: Any) -> List[Dict[str, Any]]:
    """
    Fetches all parking slots from parking_slots ordered by slot_code.
    """
    try:
        res = supabase.table("parking_slots").select("*").order("slot_code").execute()
        return res.data if res.data else []
    except Exception:
        return []


def calculate_slot_metrics(slots: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Computes summary metrics for parking slots:
    Returns dict: {'total': int, 'available': int, 'occupied': int, 'offline': int}
    """
    total = len(slots)
    available = sum(1 for s in slots if s.get("status") == "available")
    occupied = sum(1 for s in slots if s.get("status") == "occupied")
    offline = sum(1 for s in slots if s.get("status") == "offline")
    return {
        "total": total,
        "available": available,
        "occupied": occupied,
        "offline": offline,
    }


def update_slot_status(
    supabase: Any,
    slot_code: str,
    status: str,
    sensor_value: Optional[int] = None,
    device_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Updates the status and sensor reading for a specific slot_code.
    Validates status against ('available', 'occupied', 'offline').
    """
    if status not in VALID_SLOT_STATUSES:
        raise ValueError(f"Invalid slot status: '{status}'. Must be one of {VALID_SLOT_STATUSES}")

    check = supabase.table("parking_slots").select("*").eq("slot_code", slot_code).execute()
    if not check.data or len(check.data) == 0:
        raise ValueError(f"Slot code not found: '{slot_code}'")

    payload: Dict[str, Any] = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if sensor_value is not None:
        payload["sensor_value"] = int(sensor_value)
    if device_id is not None:
        payload["device_id"] = device_id

    res = supabase.table("parking_slots").update(payload).eq("slot_code", slot_code).execute()
    return res.data[0] if isinstance(res.data, list) else res.data


def check_slot_offline(slot: Dict[str, Any], threshold_seconds: int = 30) -> bool:
    """
    Checks if a slot is offline based on status or last updated_at timestamp.
    """
    if not slot:
        return True
    if slot.get("status") == "offline":
        return True

    updated_at = slot.get("updated_at")
    if not updated_at:
        return True

    if isinstance(updated_at, str):
        normalized_str = updated_at.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized_str)
        except Exception:
            return True
    elif isinstance(updated_at, datetime):
        dt = updated_at
    else:
        return True

    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    elapsed = (now - dt).total_seconds()
    return elapsed > threshold_seconds


def evaluate_slot_status(sensor_value: Optional[int], ir_threshold: int = 1000) -> str:
    """
    Determines slot status ('occupied' or 'available') based on IR sensor reading.
    Supports:
    - Digital Active-LOW IR sensor (0 = LOW / obstacle detected = 'occupied', 1 = HIGH / clear = 'available')
    - Analog ADC threshold (> ir_threshold = 'occupied')
    """
    if sensor_value is None:
        return "available"
    if sensor_value == 0:
        return "occupied"
    if sensor_value == 1:
        return "available"
    return "occupied" if sensor_value > ir_threshold else "available"


def get_slots_by_device(supabase: Any, device_id: str) -> List[Dict[str, Any]]:
    """
    Fetches parking slots assigned to a specific device_id.
    """
    try:
        res = supabase.table("parking_slots").select("*").eq("device_id", device_id).order("slot_code").execute()
        return res.data if res.data else []
    except Exception:
        return []


def assign_slots_to_device(supabase: Any, slot_codes: List[str], device_id: str) -> bool:
    """
    Assigns a list of slot_codes to a specific device_id.
    """
    try:
        for code in slot_codes:
            supabase.table("parking_slots").update({
                "device_id": device_id,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).eq("slot_code", code).execute()
        return True
    except Exception:
        return False


def create_parking_slot(
    supabase: Any,
    slot_code: str,
    status: str = "available",
    sensor_value: int = 1,
    device_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a new parking slot record in parking_slots table.
    """
    code = (slot_code or "").strip().upper()
    if not code:
        raise ValueError("Kode slot parkir tidak boleh kosong.")

    # Check for duplicate slot_code
    existing = supabase.table("parking_slots").select("*").eq("slot_code", code).execute()
    if existing.data and len(existing.data) > 0:
        raise ValueError(f"Kode slot '{code}' sudah digunakan.")

    if status not in VALID_SLOT_STATUSES:
        raise ValueError(f"Status slot tidak valid: '{status}'. Harus salah satu dari {VALID_SLOT_STATUSES}")

    payload = {
        "slot_code": code,
        "status": status,
        "sensor_value": int(sensor_value),
        "device_id": device_id.strip() if device_id else None,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    res = supabase.table("parking_slots").insert(payload).execute()
    return res.data[0] if isinstance(res.data, list) and res.data else res.data


def update_parking_slot(
    supabase: Any,
    slot_code: str,
    new_slot_code: Optional[str] = None,
    status: Optional[str] = None,
    sensor_value: Optional[int] = None,
    device_id: Any = "KEEP_EXISTING"
) -> Dict[str, Any]:
    """
    Updates an existing parking slot's details (code, status, sensor_value, device_id).
    """
    orig_code = (slot_code or "").strip().upper()
    check = supabase.table("parking_slots").select("*").eq("slot_code", orig_code).execute()
    if not check.data or len(check.data) == 0:
        raise ValueError(f"Slot dengan kode '{orig_code}' tidak ditemukan.")

    payload: Dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    if new_slot_code is not None:
        clean_new = new_slot_code.strip().upper()
        if clean_new and clean_new != orig_code:
            # Check duplicate
            dup = supabase.table("parking_slots").select("*").eq("slot_code", clean_new).execute()
            if dup.data and len(dup.data) > 0:
                raise ValueError(f"Kode slot '{clean_new}' sudah digunakan oleh slot lain.")
            payload["slot_code"] = clean_new

    if status is not None:
        if status not in VALID_SLOT_STATUSES:
            raise ValueError(f"Status tidak valid: '{status}'. Harus salah satu dari {VALID_SLOT_STATUSES}")
        payload["status"] = status

    if sensor_value is not None:
        payload["sensor_value"] = int(sensor_value)

    if device_id != "KEEP_EXISTING":
        payload["device_id"] = device_id.strip() if (isinstance(device_id, str) and device_id != "(Tanpa Device)" and device_id.strip()) else None

    res = supabase.table("parking_slots").update(payload).eq("slot_code", orig_code).execute()
    return res.data[0] if isinstance(res.data, list) and res.data else res.data


def delete_parking_slot(supabase: Any, slot_code: str) -> bool:
    """
    Deletes a parking slot record from parking_slots table.
    """
    code = (slot_code or "").strip().upper()
    check = supabase.table("parking_slots").select("*").eq("slot_code", code).execute()
    if not check.data or len(check.data) == 0:
        raise ValueError(f"Slot dengan kode '{code}' tidak ditemukan.")

    supabase.table("parking_slots").delete().eq("slot_code", code).execute()
    return True


