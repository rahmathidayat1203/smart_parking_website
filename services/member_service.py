"""
Member service module for Smart Parking Monitoring & RFID Member System.
Handles member registration, UID normalization, duplicate checks,
and CRUD operations on the parking_members and rfid_scans tables.
"""

from typing import Optional, List, Dict, Any


def normalize_rfid_uid(uid: Optional[str]) -> str:
    """
    Normalizes an RFID UID string by stripping spaces, colons, hyphens,
    and converting characters to uppercase (e.g. 'a3 f2 1c 12' -> 'A3F21C12').
    Raises ValueError if uid is None or empty.
    """
    if uid is None or not isinstance(uid, str) or not uid.strip():
        raise ValueError("RFID UID cannot be empty")
    cleaned = uid.replace(" ", "").replace(":", "").replace("-", "").strip().upper()
    if not cleaned:
        raise ValueError("RFID UID cannot be empty")
    return cleaned


def is_uid_registered(supabase: Any, uid: str) -> bool:
    """
    Checks if a normalized RFID UID is already registered in parking_members.
    """
    try:
        norm_uid = normalize_rfid_uid(uid)
    except ValueError:
        return False
    res = supabase.table("parking_members").select("*").eq("rfid_uid", norm_uid).execute()
    return bool(res.data and len(res.data) > 0)


def register_member(
    supabase: Any,
    rfid_uid: str,
    member_name: str,
    license_plate: str,
    vehicle_type: str = "car",
    status: str = "active",
    inside_parking: bool = False
) -> Dict[str, Any]:
    """
    Registers a new member into parking_members.
    Validates input fields and prevents duplicate UID registration (DRD Sec 12).
    """
    if not member_name or not member_name.strip() or not license_plate or not license_plate.strip():
        raise ValueError("Member name and license plate are required")

    norm_uid = normalize_rfid_uid(rfid_uid)

    if is_uid_registered(supabase, norm_uid):
        raise ValueError("RFID UID already registered")

    payload = {
        "rfid_uid": norm_uid,
        "member_name": member_name.strip(),
        "license_plate": license_plate.strip(),
        "vehicle_type": vehicle_type,
        "status": status,
        "inside_parking": inside_parking,
    }
    res = supabase.table("parking_members").insert(payload).execute()
    return res.data[0] if isinstance(res.data, list) else res.data


def get_all_members(supabase: Any) -> List[Dict[str, Any]]:
    """
    Fetches all members from parking_members, ordered by created_at descending.
    """
    try:
        res = supabase.table("parking_members").select("*").order("created_at", desc=True).execute()
        return res.data if res.data else []
    except Exception:
        return []


def get_member_by_uid(supabase: Any, uid: str) -> Optional[Dict[str, Any]]:
    """
    Fetches a member record by its normalized RFID UID.
    """
    try:
        norm_uid = normalize_rfid_uid(uid)
    except ValueError:
        return None
    try:
        res = supabase.table("parking_members").select("*").eq("rfid_uid", norm_uid).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception:
        pass
    return None


def update_member(
    supabase: Any,
    member_id: Any,
    member_name: str,
    license_plate: str,
    vehicle_type: str,
    status: str
) -> Dict[str, Any]:
    """
    Updates an existing member's name, license plate, vehicle type, or status.
    Supports targeting by integer member_id or string rfid_uid.
    """
    payload = {
        "member_name": member_name.strip() if member_name else member_name,
        "license_plate": license_plate.strip() if license_plate else license_plate,
        "vehicle_type": vehicle_type,
        "status": status,
    }
    query = supabase.table("parking_members").update(payload)
    if isinstance(member_id, int) or (isinstance(member_id, str) and member_id.isdigit()):
        res = query.eq("id", int(member_id)).execute()
    else:
        res = query.eq("rfid_uid", str(member_id)).execute()
    return res.data[0] if isinstance(res.data, list) and res.data else (res.data if res.data else {})


def toggle_member_status(supabase: Any, member_id: int, current_status: str) -> Dict[str, Any]:
    """
    Toggles member status between 'active' and 'inactive'.
    """
    new_status = "inactive" if current_status == "active" else "active"
    res = supabase.table("parking_members").update({"status": new_status}).eq("id", member_id).execute()
    return res.data[0] if isinstance(res.data, list) else res.data


def delete_member(supabase: Any, member_id: Any) -> bool:
    """
    Deletes a member record from parking_members by ID or rfid_uid.
    """
    query = supabase.table("parking_members").delete()
    if isinstance(member_id, int) or (isinstance(member_id, str) and member_id.isdigit()):
        query.eq("id", int(member_id)).execute()
    else:
        query.eq("rfid_uid", str(member_id)).execute()
    return True


def get_latest_rfid_scan(supabase: Any, device_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Fetches the most recent scan from rfid_scans table, optionally filtered by device_id.
    """
    try:
        query = supabase.table("rfid_scans").select("*")
        if device_id:
            query = query.eq("device_id", device_id)
        res = query.order("created_at", desc=True).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception:
        pass
    return None


def delete_rfid_scan(supabase: Any, scan_id: int) -> bool:
    """
    Deletes a specific RFID scan record by ID.
    """
    try:
        supabase.table("rfid_scans").delete().eq("id", scan_id).execute()
        return True
    except Exception:
        return False


def clear_rfid_scans_by_device(supabase: Any, device_id: str) -> bool:
    """
    Clears all RFID scan records for a specific device.
    """
    try:
        supabase.table("rfid_scans").delete().eq("device_id", device_id).execute()
        return True
    except Exception:
        return False



def set_member_inside_parking(supabase: Any, member_id: int, inside: bool) -> Dict[str, Any]:
    """
    Sets the inside_parking flag for a member (Anti-Passback tracking).
    """
    res = supabase.table("parking_members").update({"inside_parking": inside}).eq("id", member_id).execute()
    return res.data[0] if isinstance(res.data, list) and res.data else res.data


def reset_all_passback(supabase: Any) -> bool:
    """
    Resets inside_parking to False for all members (Emergency / Daily reset).
    """
    try:
        supabase.table("parking_members").update({"inside_parking": False}).neq("id", 0).execute()
        return True
    except Exception:
        return False


def validate_rfid_access(
    supabase: Any,
    uid: str,
    direction: str = "entry",
    enforce_anti_passback: bool = True,
    update_state: bool = False
) -> Dict[str, Any]:
    """
    Validates RFID access for gate entry/exit with Anti-Passback support:
    - If member exists and status == 'active':
        - If enforce_anti_passback is True:
            - If direction == 'entry' and member is already inside -> Anti-Passback violation (deny)
            - If direction == 'exit' and member is already outside -> Anti-Passback exit violation (deny)
        - Else: access granted, gate action: 'open'
    - If member exists but status == 'inactive' -> access denied, gate action: 'remain_closed'
    - If member does not exist -> access denied, gate action: 'remain_closed'
    """
    try:
        norm_uid = normalize_rfid_uid(uid)
    except ValueError:
        return {
            "authorized": False,
            "status": "invalid_uid",
            "gate_action": "remain_closed",
            "member": None,
        }

    member = get_member_by_uid(supabase, norm_uid)
    if not member:
        return {
            "authorized": False,
            "status": "unregistered",
            "gate_action": "remain_closed",
            "member": None,
        }

    if member.get("status") != "active":
        return {
            "authorized": False,
            "status": "inactive",
            "gate_action": "remain_closed",
            "member": member,
        }

    # Anti-Passback validation
    if enforce_anti_passback:
        is_inside = bool(member.get("inside_parking"))
        if direction == "entry" and is_inside:
            return {
                "authorized": False,
                "status": "anti_passback_violation",
                "gate_action": "remain_closed",
                "reason": "Pelanggaran Anti-Passback: Kartu sudah tercatat berada di dalam area parkir!",
                "member": member,
            }
        elif direction == "exit" and not is_inside:
            return {
                "authorized": False,
                "status": "anti_passback_exit_violation",
                "gate_action": "remain_closed",
                "reason": "Pelanggaran Anti-Passback: Kartu belum tercatat masuk ke area parkir!",
                "member": member,
            }

    if update_state:
        new_inside = (direction == "entry")
        supabase.table("parking_members").update({"inside_parking": new_inside}).eq("id", member["id"]).execute()
        member["inside_parking"] = new_inside

    return {
        "authorized": True,
        "status": "active",
        "gate_action": "open",
        "member": member,
    }


