"""
Audit forensic and Anti-Passback service module for Smart Parking Monitoring.
Handles security auditing, vehicle snapshot generation, entry/exit forensic logging,
and tailgating detection.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import base64
import html


def generate_vehicle_snapshot_svg(
    license_plate: str = "BG 1234 RH",
    vehicle_type: str = "car",
    event_type: str = "entry_granted",
    camera_id: str = "CAM-GATE-01"
) -> str:
    """
    Generates a realistic SVG vehicle snapshot representation
    with timestamp, camera ID, bounding box, and security badge.
    Returns a data URI string (data:image/svg+xml;base64,...).
    """
    is_violation = "violation" in event_type or "tailgating" in event_type or "unauthorized" in event_type
    border_color = "#EF4444" if is_violation else "#10B981"
    badge_text = "SECURITY ALERT" if is_violation else "VEHICLE LOGGED"
    badge_bg = "#EF4444" if is_violation else "#10B981"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    safe_plate = html.escape(str(license_plate or "UNKNOWN").upper())
    safe_cam = html.escape(str(camera_id))
    safe_type = html.escape(str(vehicle_type or "car").capitalize())

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 240" width="100%" height="100%">
  <defs>
    <linearGradient id="bg_{safe_cam}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a" />
      <stop offset="100%" stop-color="#1e293b" />
    </linearGradient>
    <linearGradient id="carBody_{safe_cam}" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#334155" />
      <stop offset="50%" stop-color="#475569" />
      <stop offset="100%" stop-color="#1e293b" />
    </linearGradient>
  </defs>

  <!-- Background Screen -->
  <rect width="400" height="240" fill="url(#bg_{safe_cam})" rx="8"/>
  <rect x="5" y="5" width="390" height="230" fill="none" stroke="#334155" stroke-dasharray="4,4" rx="6"/>

  <!-- Camera HUD info -->
  <text x="16" y="24" fill="#94a3b8" font-family="monospace" font-size="11" font-weight="bold">● REC [{safe_cam}]</text>
  <text x="384" y="24" text-anchor="end" fill="#94a3b8" font-family="monospace" font-size="11">{now_str}</text>

  <!-- Vehicle Silhouette -->
  <g transform="translate(60, 50)">
    <!-- Car body -->
    <path d="M 40,90 L 70,45 L 180,45 L 220,90 L 250,95 L 250,115 L 20,115 L 20,95 Z" fill="url(#carBody_{safe_cam})" stroke="#64748b" stroke-width="2"/>
    <!-- Windows -->
    <path d="M 75,50 L 125,50 L 125,85 L 50,85 Z" fill="#0284c7" opacity="0.4"/>
    <path d="M 135,50 L 175,50 L 210,85 L 135,85 Z" fill="#0284c7" opacity="0.4"/>
    <!-- Headlights -->
    <circle cx="245" cy="100" r="5" fill="#fef08a" opacity="0.9"/>
    <!-- Wheels -->
    <circle cx="65" cy="115" r="16" fill="#0f172a" stroke="#64748b" stroke-width="3"/>
    <circle cx="205" cy="115" r="16" fill="#0f172a" stroke="#64748b" stroke-width="3"/>
    <circle cx="65" cy="115" r="6" fill="#cbd5e1"/>
    <circle cx="205" cy="115" r="6" fill="#cbd5e1"/>
  </g>

  <!-- Detection Bounding Box on Plate -->
  <rect x="120" y="150" width="160" height="42" fill="#090d16" stroke="{border_color}" stroke-width="2" rx="4"/>
  <rect x="125" y="154" width="150" height="34" fill="#0f172a" rx="2"/>
  <text x="200" y="176" text-anchor="middle" fill="#ffffff" font-family="monospace" font-weight="bold" font-size="14" letter-spacing="2">{safe_plate}</text>

  <!-- Security Tag / Badge -->
  <rect x="16" y="204" width="130" height="22" fill="{badge_bg}" rx="4"/>
  <text x="81" y="219" text-anchor="middle" fill="#ffffff" font-family="sans-serif" font-size="10" font-weight="bold">{badge_text}</text>

  <!-- Type tag -->
  <text x="384" y="219" text-anchor="end" fill="#cbd5e1" font-family="sans-serif" font-size="11">Type: {safe_type}</text>
</svg>"""

    b64_svg = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{b64_svg}"


def log_audit_event(
    supabase: Any,
    event_type: str,
    rfid_uid: Optional[str] = None,
    member_name: Optional[str] = None,
    license_plate: Optional[str] = None,
    device_id: Optional[str] = "GATE-01",
    photo_url: Optional[str] = None,
    tailgating_detected: bool = False,
    details: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Inserts a new forensic log record into audit_forensic_logs table.
    """
    if not photo_url:
        plate = license_plate or "UNKNOWN"
        photo_url = generate_vehicle_snapshot_svg(
            license_plate=plate,
            vehicle_type="car",
            event_type=event_type,
            camera_id=f"CAM-{device_id or 'GATE-01'}"
        )

    payload = {
        "event_type": event_type,
        "rfid_uid": rfid_uid,
        "member_name": member_name,
        "license_plate": license_plate,
        "device_id": device_id,
        "photo_url": photo_url,
        "tailgating_detected": tailgating_detected,
        "details": details or "",
    }
    try:
        res = supabase.table("audit_forensic_logs").insert(payload).execute()
        return res.data[0] if isinstance(res.data, list) and res.data else payload
    except Exception:
        return payload


def get_audit_logs(
    supabase: Any,
    limit: int = 50,
    event_type: Optional[str] = None,
    tailgating_only: bool = False,
) -> List[Dict[str, Any]]:
    """
    Fetches forensic logs sorted by created_at descending.
    """
    try:
        query = supabase.table("audit_forensic_logs").select("*").order("created_at", desc=True).limit(limit)
        if event_type:
            query = query.eq("event_type", event_type)
        if tailgating_only:
            query = query.eq("tailgating_detected", True)
        res = query.execute()
        return res.data if res.data else []
    except Exception:
        return []


def process_gate_entry(
    supabase: Any,
    uid: str,
    device_id: str = "GATE-01",
    photo_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Processes gate entry request with Anti-Passback check, photo capture,
    and forensic logging.
    """
    from services.member_service import validate_rfid_access

    val = validate_rfid_access(supabase, uid, direction="entry", enforce_anti_passback=True, update_state=False)

    if val["status"] == "anti_passback_violation":
        member = val.get("member") or {}
        plate = member.get("license_plate") or "UNKNOWN"
        name = member.get("member_name") or "Unknown Member"
        photo = photo_url or generate_vehicle_snapshot_svg(plate, "car", "anti_passback_violation", f"CAM-{device_id}")

        log = log_audit_event(
            supabase=supabase,
            event_type="anti_passback_violation",
            rfid_uid=uid,
            member_name=name,
            license_plate=plate,
            device_id=device_id,
            photo_url=photo,
            tailgating_detected=False,
            details=f"Pelanggaran Anti-Passback: Kartu {name} ({uid}) sudah berada di dalam area parkir!",
        )
        val["audit_log"] = log
        val["photo_url"] = photo
        return val

    if not val["authorized"]:
        photo = photo_url or generate_vehicle_snapshot_svg("UNAUTHORIZED", "car", "unauthorized_scan", f"CAM-{device_id}")
        log = log_audit_event(
            supabase=supabase,
            event_type="unauthorized_scan",
            rfid_uid=uid,
            member_name=val.get("member", {}).get("member_name") if val.get("member") else "Tidak Dikenal",
            license_plate=val.get("member", {}).get("license_plate") if val.get("member") else "-",
            device_id=device_id,
            photo_url=photo,
            tailgating_detected=False,
            details=f"Akses masuk ditolak: Status {val['status']}",
        )
        val["audit_log"] = log
        val["photo_url"] = photo
        return val

    # Authorized entry: set inside_parking = True and log entry
    member = val["member"]
    supabase.table("parking_members").update({"inside_parking": True}).eq("id", member["id"]).execute()
    member["inside_parking"] = True

    plate = member.get("license_plate", "-")
    name = member.get("member_name", "Member")
    photo = photo_url or generate_vehicle_snapshot_svg(plate, member.get("vehicle_type", "car"), "entry_granted", f"CAM-{device_id}")

    log = log_audit_event(
        supabase=supabase,
        event_type="entry_granted",
        rfid_uid=uid,
        member_name=name,
        license_plate=plate,
        device_id=device_id,
        photo_url=photo,
        tailgating_detected=False,
        details=f"Akses masuk diberikan kepada {name} ({plate})",
    )
    val["audit_log"] = log
    val["photo_url"] = photo
    return val


def process_gate_exit(
    supabase: Any,
    uid: str,
    device_id: str = "GATE-01",
    photo_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Processes gate exit request: sets inside_parking = False and logs forensic audit.
    """
    from services.member_service import get_member_by_uid, normalize_rfid_uid

    try:
        norm_uid = normalize_rfid_uid(uid)
    except ValueError:
        return {"authorized": False, "status": "invalid_uid", "gate_action": "remain_closed"}

    member = get_member_by_uid(supabase, norm_uid)
    if not member:
        return {"authorized": False, "status": "unregistered", "gate_action": "remain_closed"}

    # Update inside_parking to False
    supabase.table("parking_members").update({"inside_parking": False}).eq("id", member["id"]).execute()
    member["inside_parking"] = False

    plate = member.get("license_plate", "-")
    name = member.get("member_name", "Member")
    photo = photo_url or generate_vehicle_snapshot_svg(plate, member.get("vehicle_type", "car"), "exit_granted", f"CAM-{device_id}")

    log = log_audit_event(
        supabase=supabase,
        event_type="exit_granted",
        rfid_uid=norm_uid,
        member_name=name,
        license_plate=plate,
        device_id=device_id,
        photo_url=photo,
        tailgating_detected=False,
        details=f"Akses keluar diberikan kepada {name} ({plate}). Posisi diperbarui ke Luar.",
    )

    return {
        "authorized": True,
        "status": "exit_granted",
        "gate_action": "open",
        "member": member,
        "photo_url": photo,
        "audit_log": log,
    }


def report_tailgating(
    supabase: Any,
    device_id: str = "GATE-01",
    details: Optional[str] = None,
    photo_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reports a tailgating incident (unauthorized vehicle closely following behind).
    Triggers forensic snapshot and alarm log.
    """
    photo = photo_url or generate_vehicle_snapshot_svg("SUSPICIOUS", "car", "tailgating_detected", f"CAM-{device_id}")
    msg = details or "PERINGATAN TAILGATING: Kendaraan membuntuti tanpa otorisasi kartu saat palang gerbang terbuka!"

    return log_audit_event(
        supabase=supabase,
        event_type="tailgating_detected",
        rfid_uid=None,
        member_name="TIDAK TERIDENTIFIKASI",
        license_plate="TAILGATING/NO_TAP",
        device_id=device_id,
        photo_url=photo,
        tailgating_detected=True,
        details=msg,
    )


def delete_audit_log(supabase: Any, log_id: int) -> bool:
    """
    Deletes a specific forensic audit log entry by ID.
    """
    try:
        supabase.table("audit_forensic_logs").delete().eq("id", log_id).execute()
        return True
    except Exception:
        return False


def clear_all_audit_logs(supabase: Any) -> bool:
    """
    Clears all forensic audit logs from audit_forensic_logs.
    """
    try:
        supabase.table("audit_forensic_logs").delete().neq("id", 0).execute()
        return True
    except Exception:
        return False

