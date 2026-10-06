"""
Device service module for Smart Parking IoT monitoring.
Handles device status queries, online/offline threshold evaluation (TRD Sec 21),
and heartbeat updates.
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone


def get_device_status(supabase: Any, device_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches the status and metadata for a specific device from iot_devices.
    """
    try:
        res = supabase.table("iot_devices").select("*").eq("device_id", device_id).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception:
        pass
    return None


def get_all_devices(supabase: Any) -> List[Dict[str, Any]]:
    """
    Fetches all registered devices from iot_devices.
    """
    try:
        res = supabase.table("iot_devices").select("*").execute()
        return res.data if res.data else []
    except Exception:
        return []


def is_device_online(
    last_seen: Optional[Union[str, datetime]],
    threshold_seconds: int = 30
) -> bool:
    """
    Evaluates whether an IoT device is currently online.
    Per TRD Sec 21: if now - last_seen > threshold_seconds -> offline.
    """
    if last_seen is None:
        return False

    if isinstance(last_seen, str):
        normalized_str = last_seen.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized_str)
        except Exception:
            return False
    elif isinstance(last_seen, datetime):
        dt = last_seen
    else:
        return False

    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    elapsed = (now - dt).total_seconds()
    return elapsed <= threshold_seconds


def update_device_heartbeat(
    supabase: Any,
    device_id: str,
    status: str = "online",
    device_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Updates or upserts the heartbeat and status of an IoT device in iot_devices.
    """
    payload: Dict[str, Any] = {
        "device_id": device_id,
        "status": status,
        "last_seen": datetime.now(timezone.utc).isoformat(),
    }
    if device_name is not None:
        payload["device_name"] = device_name

    res = supabase.table("iot_devices").upsert(payload, on_conflict="device_id").execute()
    return res.data[0] if isinstance(res.data, list) else res.data


def generate_device_api_key() -> str:
    """
    Generates a secure, unique API key token for student device authorization.
    Format: sk_dev_<32 hex characters>
    """
    import secrets
    return f"sk_dev_{secrets.token_hex(16)}"


def register_student_device(
    supabase: Any,
    owner_name: str,
    device_name: str,
    device_type: str = "multi-sensor",
    device_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Registers a new student device with owner credentials and auto-generated API key.
    """
    cleaned_owner = (owner_name or "").strip()
    if not cleaned_owner:
        raise ValueError("Nama pemilik/siswa tidak boleh kosong.")

    cleaned_name = (device_name or "").strip()
    if not cleaned_name:
        raise ValueError("Nama perangkat tidak boleh kosong.")

    if not device_id:
        import secrets
        device_id = f"DEV-SISWA-{secrets.token_hex(3).upper()}"
    else:
        device_id = device_id.strip().upper()

    # Check for duplicate device_id
    existing = supabase.table("iot_devices").select("id").eq("device_id", device_id).execute()
    if existing.data and len(existing.data) > 0:
        raise ValueError(f"Perangkat dengan ID '{device_id}' sudah terdaftar.")

    api_key = generate_device_api_key()
    now_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "device_id": device_id,
        "device_name": cleaned_name,
        "owner_name": cleaned_owner,
        "device_type": device_type,
        "api_key": api_key,
        "status": "offline",
        "created_at": now_iso,
    }

    res = supabase.table("iot_devices").insert(payload).execute()
    return res.data[0] if isinstance(res.data, list) else res.data


def get_device_by_api_key(supabase: Any, api_key: str) -> Optional[Dict[str, Any]]:
    """
    Finds and authenticates a device by its unique API key.
    """
    if not api_key:
        return None
    res = supabase.table("iot_devices").select("*").eq("api_key", api_key.strip()).execute()
    if res.data and len(res.data) > 0:
        return res.data[0]
    return None


def get_student_device_telemetry(supabase: Any, device_id: str) -> Dict[str, Any]:
    """
    Retrieves sensor data and RFID scans isolated specifically for a target device_id.
    """
    # Fetch sensor readings
    sensors_res = supabase.table("sensor_data").select("*").eq("device_id", device_id).order("created_at", desc=True).limit(50).execute()
    sensors = sensors_res.data if sensors_res.data else []

    # Fetch RFID scans
    scans_res = supabase.table("rfid_scans").select("*").eq("device_id", device_id).order("created_at", desc=True).limit(20).execute()
    scans = scans_res.data if scans_res.data else []

    # Determine latest ultrasonic
    latest_ultrasonic = None
    for s in sensors:
        if s.get("sensor_type") == "ultrasonic":
            latest_ultrasonic = s.get("sensor_value")
            break

    return {
        "sensors": sensors,
        "scans": scans,
        "latest_ultrasonic": latest_ultrasonic,
    }


def generate_esp32_code_snippet(
    device_id: str,
    api_key: str,
    supabase_url: str,
    supabase_anon_key: str
) -> str:
    """
    Generates a complete, ready-to-flash Arduino C++ firmware sketch for ESP32-S3
    with pre-filled credentials.
    """
    clean_url = supabase_url.rstrip("/")
    return f"""// ====================================================================
// ESP32-S3 Smart Parking Firmware - Kode Siswa
// Device ID  : {device_id}
// Device Key : {api_key}
// Target URL : {clean_url}
// ====================================================================

#include <WiFi.h>
#include <HTTPClient.h>

// 1. Konfigurasi WiFi
const char* ssid = "NAMA_WIFI_HOTSPOT";
const char* password = "PASSWORD_WIFI";

// 2. Kredensial & Endpoint Supabase
const char* SUPABASE_URL = "{clean_url}";
const char* SUPABASE_KEY = "{supabase_anon_key}";
const char* DEVICE_ID = "{device_id}";
const char* DEVICE_API_KEY = "{api_key}";

// Pin Definisi HC-SR04
const int TRIG_PIN = 5;
const int ECHO_PIN = 18;

void sendHeartbeat() {{
  if (WiFi.status() == WL_CONNECTED) {{
    HTTPClient http;
    String endpoint = String(SUPABASE_URL) + "/rest/v1/iot_devices";
    http.begin(endpoint);

    http.addHeader("Content-Type", "application/json");
    http.addHeader("apikey", SUPABASE_KEY);
    http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);
    http.addHeader("Prefer", "resolution=merge-duplicates");

    String json = "{{\\"device_id\\":\\"" + String(DEVICE_ID) + 
                  "\\",\\"status\\":\\"online\\",\\"last_seen\\":\\"now()\\"}}";

    int code = http.POST(json);
    Serial.printf("[Heartbeat] HTTP %d\\n", code);
    http.end();
  }}
}}

void sendUltrasonicReading(float distanceCm) {{
  if (WiFi.status() == WL_CONNECTED) {{
    HTTPClient http;
    String endpoint = String(SUPABASE_URL) + "/rest/v1/sensor_data";
    http.begin(endpoint);

    http.addHeader("Content-Type", "application/json");
    http.addHeader("apikey", SUPABASE_KEY);
    http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);

    String json = "{{\\"device_id\\":\\"" + String(DEVICE_ID) + 
                  "\\",\\"sensor_type\\":\\"ultrasonic\\",\\"sensor_value\\":" + 
                  String(distanceCm, 2) + "}}";

    int code = http.POST(json);
    Serial.printf("[Sensor Ultrasonik] Jarak: %.2f cm -> HTTP %d\\n", distanceCm, code);
    http.end();
  }}
}}

float readUltrasonicDistance() {{
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  if (duration == 0) return 999.0; // Timeout
  return duration * 0.034 / 2.0;
}}

void setup() {{
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  WiFi.begin(ssid, password);
  Serial.print("Menghubungkan ke WiFi");
  while (WiFi.status() != WL_CONNECTED) {{
    delay(500);
    Serial.print(".");
  }}
  Serial.println("\\nWiFi Terhubung! IP: " + WiFi.localIP().toString());
}}

unsigned long lastHeartbeat = 0;
unsigned long lastSensor = 0;

void loop() {{
  unsigned long now = millis();

  // Kirim Heartbeat setiap 10 detik (dibawah batas 30s offline)
  if (now - lastHeartbeat > 10000) {{
    sendHeartbeat();
    lastHeartbeat = now;
  }}

  // Baca dan kirim sensor setiap 3 detik
  if (now - lastSensor > 3000) {{
    float distance = readUltrasonicDistance();
    sendUltrasonicReading(distance);
    lastSensor = now;
  }}
}}
"""


def get_student_devices(supabase: Any) -> List[Dict[str, Any]]:
    """
    Fetches all devices registered by students (differentiating from core gateway/system nodes).
    """
    all_devs = get_all_devices(supabase)
    student_devs = []
    for d in all_devs:
        dev_id = d.get("device_id", "")
        owner = d.get("owner_name")
        api_key = d.get("api_key")
        # Identify student devices by presence of owner_name or DEV-SISWA prefix or api_key
        if owner or dev_id.startswith("DEV-SISWA") or api_key:
            student_devs.append(d)
    return student_devs


def get_student_device_full_details(supabase: Any, device_id: str) -> Optional[Dict[str, Any]]:
    """
    Gathers comprehensive device profile, connectivity status,
    and all associated telemetries (ultrasonic, IR, RFID scans).
    """
    device = get_device_status(supabase, device_id)
    if not device:
        return None

    online = is_device_online(device.get("last_seen"), threshold_seconds=30)
    telemetry = get_student_device_telemetry(supabase, device_id)

    return {
        "device": device,
        "online": online,
        "telemetry": telemetry,
        "total_telemetry_count": len(telemetry.get("sensors", [])),
        "total_scans_count": len(telemetry.get("scans", [])),
        "latest_ultrasonic": telemetry.get("latest_ultrasonic"),
    }


def set_device_registration_mode(supabase: Any, device_id: str, enable: bool = True) -> bool:
    """
    Toggles the registration mode command for a specific IoT device.
    Sets status to 'registering' if enable=True, or 'online' if enable=False.
    """
    try:
        new_status = "registering" if enable else "online"
        supabase.table("iot_devices").update({
            "status": new_status,
            "last_seen": datetime.now(timezone.utc).isoformat(),
        }).eq("device_id", device_id).execute()
        return True
    except Exception:
        return False


def get_device_registration_mode(supabase: Any, device_id: str) -> bool:
    """
    Checks if a device is currently in registration mode ('status' == 'registering').
    """
    try:
        res = supabase.table("iot_devices").select("status").eq("device_id", device_id).execute()
        if res.data and len(res.data) > 0:
            return res.data[0].get("status") == "registering"
    except Exception:
        pass
    return False


def update_device(
    supabase: Any,
    device_id: str,
    device_name: Optional[str] = None,
    owner_name: Optional[str] = None,
    device_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Updates IoT device metadata (device_name, owner_name, device_type).
    """
    dev = get_device_status(supabase, device_id)
    if not dev:
        raise ValueError(f"Perangkat dengan ID '{device_id}' tidak ditemukan.")

    payload: Dict[str, Any] = {}
    if device_name is not None and device_name.strip():
        payload["device_name"] = device_name.strip()
    if owner_name is not None:
        payload["owner_name"] = owner_name.strip()
    if device_type is not None and device_type.strip():
        payload["device_type"] = device_type.strip()

    if not payload:
        return dev

    res = supabase.table("iot_devices").update(payload).eq("device_id", device_id).execute()
    return res.data[0] if isinstance(res.data, list) and res.data else dev


def delete_device(supabase: Any, device_id: str) -> bool:
    """
    Deletes an IoT device from iot_devices.
    Also clears device association from parking slots and users if linked.
    """
    dev = get_device_status(supabase, device_id)
    if not dev:
        raise ValueError(f"Perangkat dengan ID '{device_id}' tidak ditemukan.")

    # Unlink any parking slots associated with this device
    try:
        supabase.table("parking_slots").update({"device_id": None}).eq("device_id", device_id).execute()
    except Exception:
        pass

    # Unlink any users associated with this device
    try:
        supabase.table("app_users").update({"device_id": None}).eq("device_id", device_id).execute()
    except Exception:
        pass

    # Delete device from iot_devices
    supabase.table("iot_devices").delete().eq("device_id", device_id).execute()
    return True



