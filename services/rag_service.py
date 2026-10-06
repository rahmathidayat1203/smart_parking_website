"""
RAG Indexing Utility for Smart Parking Documentation.

TUJUAN:
    Modul ini BUKAN bagian dari logika runtime website.
    Fungsinya adalah meng-index dokumentasi Smart Parking (PRD, DRD, TRD, Business Rules)
    ke dalam sistem RAG (http://127.0.0.1:8001) sebagai knowledge base.

CARA PAKAI:
    Jalankan script ini sekali untuk meng-index semua dokumen ke RAG:
        python services/rag_service.py

    Atau panggil fungsi index_all_documents() dari script lain.
"""

import sys
import os
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [RAG] %(message)s")
logger = logging.getLogger(__name__)

# RAG API base URL
RAG_API_BASE = "http://127.0.0.1:8001"

# Project ID untuk Smart Parking di RAG
RAG_PROJECT_ID = "smart-parking"


# ==============================================================================
# Koneksi & Health Check
# ==============================================================================

def is_rag_available() -> bool:
    """
    Mengecek apakah RAG API service aktif dan bisa diakses.
    Mengembalikan True jika endpoint /health merespons dengan status 'healthy'.
    """
    try:
        import requests
        resp = requests.get(f"{RAG_API_BASE}/health", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("status") == "healthy"
    except Exception:
        pass
    return False


def rag_index_text(
    content: str,
    category: str = "business_rule",
    source: str = "smart-parking:manual"
) -> bool:
    """
    Meng-index satu chunk teks ke dalam RAG memory system.
    Mengembalikan True jika berhasil, False jika gagal.
    """
    try:
        import requests
        payload = {
            "project_id": RAG_PROJECT_ID,
            "content": content,
            "category": category,
            "source": source,
        }
        resp = requests.post(
            f"{RAG_API_BASE}/api/v1/index",
            json=payload,
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        logger.warning(f"Gagal index chunk [{source}]: {e}")
        return False


def rag_index_file(file_path: str, category: str = "documentation") -> bool:
    """
    Meng-index file teks (misalnya .md, .txt, .py) ke dalam RAG.
    Mengembalikan True jika berhasil.
    """
    try:
        import requests
        payload = {
            "project_id": RAG_PROJECT_ID,
            "file_path": file_path,
            "category": category,
            "source": f"smart-parking:file:{Path(file_path).name}",
        }
        resp = requests.post(
            f"{RAG_API_BASE}/api/v1/index",
            json=payload,
            timeout=15,
        )
        if resp.status_code == 200:
            result = resp.json()
            logger.info(f"File di-index: {file_path} → {result.get('chunks', 0)} chunk")
            return True
        else:
            logger.warning(f"Gagal index file {file_path}: HTTP {resp.status_code} — {resp.text}")
            return False
    except Exception as e:
        logger.warning(f"Gagal index file {file_path}: {e}")
        return False


def rag_search(query: str, category: Optional[str] = None, limit: int = 5) -> list:
    """
    Mencari konteks relevan dari RAG memory berdasarkan query.
    Hanya untuk keperluan pengembang / debugging — bukan dipanggil oleh website.
    """
    try:
        import requests
        payload = {
            "project_id": RAG_PROJECT_ID,
            "query": query,
            "limit": limit,
            "hybrid": True,
        }
        if category:
            payload["category"] = category
        resp = requests.post(f"{RAG_API_BASE}/api/v1/search", json=payload, timeout=8)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning(f"RAG search gagal: {e}")
    return []


# ==============================================================================
# Dokumentasi Smart Parking (PRD / DRD / TRD / Business Rules)
# ==============================================================================

# Dokumen ini adalah teks PRD/DRD/TRD Smart Parking yang akan di-index ke RAG.
# Tambahkan atau edit isi dokumen sesuai kebutuhan.

SMART_PARKING_DOCUMENTS = [

    # ──────────────────────────────────────────────────────────────────────────
    # PRD — Product Requirements Document
    # ──────────────────────────────────────────────────────────────────────────
    {
        "category": "documentation",
        "source": "smart-parking:PRD:overview",
        "content": """
PRD Smart Parking Monitoring & RFID Member System — Overview

Produk: Smart Parking Monitoring & RFID Member System
Platform: Streamlit (Python) + Supabase (PostgreSQL) + ESP32-S3 IoT Hardware
Tujuan Produk:
  Sistem manajemen parkir berbasis IoT yang memungkinkan deteksi otomatis ketersediaan slot parkir
  menggunakan sensor IR Active-LOW dan ultrasonik HC-SR04, serta kontrol akses gerbang parkir
  melalui kartu RFID RC522 yang dikelola oleh mikrokontroler ESP32-S3.

Target Pengguna:
  - Administrator: Mengelola member RFID, slot parkir, perangkat IoT, dan akses pengguna sistem.
  - Siswa/Student: Memantau slot parkir dan melihat status perangkat IoT milik mereka.
  - Perangkat IoT (ESP32-S3): Mengirim data sensor dan menerima perintah gerbang.

Fitur Utama:
  1. Dashboard real-time monitoring slot parkir (3-4 slot, auto-refresh 3-4 detik)
  2. Kontrol akses gerbang otomatis berbasis RFID + Anti-Passback
  3. Manajemen member RFID (registrasi, edit, nonaktifkan, hapus)
  4. Monitoring sensor (IR Active-LOW, ultrasonik HC-SR04)
  5. Log audit forensik rekaman kamera gerbang
  6. Manajemen perangkat IoT siswa
  7. Manajemen user & role (admin/student)
""",
    },

    # ──────────────────────────────────────────────────────────────────────────
    # DRD — Detail Requirements Document: Akses & Member
    # ──────────────────────────────────────────────────────────────────────────
    {
        "category": "business_rule",
        "source": "smart-parking:DRD:member_access",
        "content": """
DRD Sec 12 — Aturan Akses Member RFID Smart Parking

Aturan Utama Akses:
  1. Hanya member RFID yang terdaftar di tabel parking_members dengan status='active'
     yang diizinkan membuka palang gerbang parkir.
  2. Kartu RFID yang UID-nya tidak ditemukan dalam database (status: unregistered)
     akan ditolak aksesnya. Gate action: 'remain_closed'. Palang TIDAK membuka.
  3. Member yang berstatus 'inactive' juga ditolak aksesnya. Gate action: 'remain_closed'.
  4. Sistem mengembalikan respons terstruktur:
     - authorized: True/False
     - status: 'active' | 'inactive' | 'unregistered' | 'invalid_uid' | 'anti_passback_violation'
     - gate_action: 'open' | 'remain_closed'
     - member: data member atau None

Registrasi Member (DRD Sec 9-11):
  - UID kartu RFID WAJIB dibaca otomatis oleh sensor RC522 pada ESP32. TIDAK boleh diketik manual.
  - Duplikasi UID dilarang: satu kartu hanya bisa didaftarkan satu kali.
  - Field wajib: rfid_uid (normalized), member_name, license_plate, vehicle_type, status.
  - UID dinormalisasi: strip spasi/titik dua/tanda hubung, uppercase (e.g. 'a3 f2:1c' → 'A3F21C').
""",
    },

    # ──────────────────────────────────────────────────────────────────────────
    # DRD — Anti-Passback
    # ──────────────────────────────────────────────────────────────────────────
    {
        "category": "business_rule",
        "source": "smart-parking:DRD:anti_passback",
        "content": """
DRD Sec 14 — Aturan Anti-Passback Smart Parking

Anti-Passback mencegah penyalahgunaan kartu RFID dengan memantau posisi member (dalam/luar area).

Aturan:
  - Setiap member memiliki flag inside_parking (Boolean) di tabel parking_members.
  - Entry (masuk): Jika inside_parking=True (sudah di dalam), tap masuk ditolak.
    Status: 'anti_passback_violation'. Gate action: 'remain_closed'.
  - Exit (keluar): Jika inside_parking=False (sudah di luar), tap keluar ditolak.
    Status: 'anti_passback_exit_violation'. Gate action: 'remain_closed'.
  - Saat akses berhasil: inside_parking diperbarui (entry → True, exit → False).
  - Emergency Reset: Administrator dapat mereset semua member ke inside_parking=False
    melalui halaman Member RFID jika sistem sempat offline.
""",
    },

    # ──────────────────────────────────────────────────────────────────────────
    # DRD — Slot Parkir & Sensor IR
    # ──────────────────────────────────────────────────────────────────────────
    {
        "category": "business_rule",
        "source": "smart-parking:DRD:slot_and_sensor",
        "content": """
DRD Sec 8 — Slot Parkir & Sensor IR Active-LOW

Status Slot:
  - available (KOSONG): Sensor IR membaca HIGH (nilai=1). Tidak ada kendaraan.
  - occupied (TERISI): Sensor IR membaca LOW (nilai=0). Kendaraan terdeteksi (modul Active-LOW).
  - offline: Tidak ada pembaruan data > 30 detik, atau ESP32 terputus dari WiFi.

Logika Sensor IR Active-LOW:
  - Nilai 0 (LOW) → obstacle detected → status: 'occupied'
  - Nilai 1 (HIGH) → no obstacle → status: 'available'
  - Nilai > 1000 (ADC analog) → > threshold → status: 'occupied'
  - Palang gerbang HANYA membuka jika minimal 1 slot tersedia.

Ambang Batas Offline:
  - Slot dianggap offline jika updated_at > 30 detik dari sekarang.
  - Jika ESP32 device offline, semua slot device tersebut otomatis ditampilkan sebagai OFFLINE.

Tabel: parking_slots (slot_code, status, sensor_value, device_id, updated_at)
""",
    },

    # ──────────────────────────────────────────────────────────────────────────
    # TRD — Technical Requirements: Gate Logic (FreeRTOS)
    # ──────────────────────────────────────────────────────────────────────────
    {
        "category": "business_rule",
        "source": "smart-parking:TRD:gate_logic",
        "content": """
TRD Sec 20 — Logika Akses Palang Gerbang (FreeRTOS ESP32)

Tiga Kondisi Akses Gerbang (diproses oleh TaskGate di ESP32):

  Kondisi 1 — DITOLAK (No Car at Gate):
    Kartu RFID di-tap tetapi sensor ultrasonik HC-SR04 membaca jarak > 20 cm
    (tidak ada kendaraan di depan gerbang).
    Respons: Pesan peringatan "Dekatkan Kendaraan". Palang TIDAK membuka.

  Kondisi 2 — DITOLAK (Parking Full):
    Ada kendaraan di gerbang (jarak ≤ 20 cm) tetapi semua slot parkir penuh (sisa=0).
    Respons: LCD menampilkan "PARKIR PENUH!". Palang TIDAK membuka.

  Kondisi 3 — DITERIMA (Access Granted):
    Ada kendaraan di gerbang (jarak ≤ 20 cm) DAN minimal 1 slot kosong DAN kartu valid (member aktif).
    Respons: Palang terbuka otomatis 90° selama 5 detik. LCD menampilkan "SELAMAT DATANG".

Sensor Ultrasonik HC-SR04:
  - Ambang batas deteksi kendaraan: ≤ 20 cm
  - Endpoint: POST /api/sensor_reading (type='ultrasonic', device_id, sensor_value)

LCD 16x2 I2C (SDA:16, SCL:17):
  - Baris 1: "[1][2][3] SISA:N" atau "[-][-][-] PENUH!"
  - Baris 2: "SILAKAN TAP..." / "GERBANG: MAJU..." / "PARKIR PENUH!"
""",
    },

    # ──────────────────────────────────────────────────────────────────────────
    # TRD — Arsitektur Sistem & Database
    # ──────────────────────────────────────────────────────────────────────────
    {
        "category": "architecture",
        "source": "smart-parking:TRD:architecture",
        "content": """
TRD Sec 1-5 — Arsitektur Sistem Smart Parking

Stack Teknologi:
  - Frontend/Backend: Streamlit (Python 3.13)
  - Database: Supabase (PostgreSQL) via supabase-py
  - Hardware: ESP32-S3 + RC522 RFID + HC-SR04 Ultrasonik + IR Active-LOW + Servo SG90 + LCD 16x2 I2C
  - Firmware: Arduino / C++ (FreeRTOS tasks)

Tabel Database Utama:
  1. parking_members: rfid_uid (PK normalized), member_name, license_plate, vehicle_type,
                      status (active/inactive), inside_parking (Anti-Passback), created_at
  2. parking_slots: slot_code (PK), status (available/occupied/offline), sensor_value,
                    device_id (FK), updated_at
  3. rfid_scans: id, uid, device_id, created_at — log tap kartu masuk dari ESP32
  4. iot_devices: device_id (PK), device_name, device_type, owner_name, api_key,
                  last_seen, registration_mode, created_at
  5. sensor_readings: id, device_id, sensor_type (ir/ultrasonic), sensor_value, created_at
  6. audit_logs: id, event_type, rfid_uid, member_name, license_plate, device_id,
                 photo_url, details, created_at — forensic gate log
  7. app_users: id, username, password_hash, full_name, role (admin/student), device_id, created_at

Auto-Refresh: Fragment-based (st.fragment) 3-4 detik — bukan full page reload.
Autentikasi: Session-based (st.session_state + query_params persistence).
""",
    },

    # ──────────────────────────────────────────────────────────────────────────
    # DRD — Role & Hak Akses Halaman
    # ──────────────────────────────────────────────────────────────────────────
    {
        "category": "business_rule",
        "source": "smart-parking:DRD:roles_access",
        "content": """
DRD Sec 15-17 — Role Pengguna & Hak Akses Halaman

Role yang Tersedia:
  - admin: Akses penuh ke semua halaman.
  - student/siswa: Akses terbatas ke Monitoring Parkir dan Dashboard Siswa saja.

Pemetaan Halaman & Role:
  - app.py (Dashboard Utama): Semua role (admin, student)
  - 1_Monitoring_Parkir.py: Semua role (admin, student)
  - 2_Member_RFID.py: Admin only
  - 3_IoT_Device.py: Admin only
  - 4_Monitoring_Sensor.py: Admin only
  - 5_Dashboard_Siswa.py: Semua role (admin, student)
  - 6_Manajemen_User.py: Admin only

Jika pengguna tidak login → halaman menampilkan form login dan menghentikan eksekusi (st.stop()).
Jika pengguna login tapi role tidak diizinkan → pesan error dan st.stop().

Registrasi Siswa:
  - Siswa bisa mendaftar mandiri melalui form registrasi di halaman login.
  - Saat registrasi, sistem otomatis membuat perangkat IoT baru (device_id unik).
""",
    },

    # ──────────────────────────────────────────────────────────────────────────
    # DRD — Tailgating Detection & Audit Log
    # ──────────────────────────────────────────────────────────────────────────
    {
        "category": "business_rule",
        "source": "smart-parking:DRD:tailgating_audit",
        "content": """
DRD Sec 19 — Deteksi Tailgating & Log Audit Forensik

Tailgating (Mobil Membuntuti):
  - Sistem mendeteksi kendaraan yang masuk ke area parkir tanpa melakukan tap kartu RFID.
  - Terdeteksi via sensor ultrasonik: kendaraan terdeteksi di gerbang tapi tidak ada tap kartu.
  - Saat terdeteksi: event_type='tailgating_detected' dicatat ke tabel audit_logs.
  - Alert banner merah ditampilkan di halaman Monitoring Parkir.

Log Audit Forensik (audit_logs):
  - Mencatat semua event akses gerbang: entry, exit, violation, tailgating.
  - Field: event_type, rfid_uid, member_name, license_plate, device_id, photo_url, details, created_at.
  - photo_url: URL gambar dari kamera gerbang (jika tersedia).
  - Admin dapat menghapus log individual atau membersihkan semua log.
  - Ditampilkan di halaman Monitoring Parkir sebagai kartu visual.
""",
    },
]


# ==============================================================================
# Fungsi Indexing Utama
# ==============================================================================

def index_all_documents(workspace_path: Optional[str] = None) -> dict:
    """
    Meng-index semua dokumen Smart Parking ke dalam RAG.

    Parameter:
        workspace_path: Path ke folder webSmartParking (opsional).
                        Jika diberikan, akan mencoba index file source code juga.

    Mengembalikan:
        dict dengan 'success', 'failed', 'total' count.
    """
    if not is_rag_available():
        logger.error(f"RAG API tidak aktif di {RAG_API_BASE}. Pastikan RAG service sudah berjalan.")
        return {"success": 0, "failed": 0, "total": 0, "error": "RAG not available"}

    logger.info(f"Terhubung ke RAG API: {RAG_API_BASE}")
    logger.info(f"Project ID: {RAG_PROJECT_ID}")
    logger.info("=" * 60)

    success_count = 0
    failed_count = 0

    # 1. Index dokumen teks (PRD/DRD/TRD)
    logger.info(f"Meng-index {len(SMART_PARKING_DOCUMENTS)} dokumen teks...")
    for doc in SMART_PARKING_DOCUMENTS:
        ok = rag_index_text(
            content=doc["content"].strip(),
            category=doc["category"],
            source=doc["source"],
        )
        status = "OK" if ok else "FAIL"
        logger.info(f"  [{status}] {doc['source']}")
        if ok:
            success_count += 1
        else:
            failed_count += 1

    # 2. Index file source code (opsional, jika workspace_path diberikan)
    if workspace_path:
        ws = Path(workspace_path)
        if ws.exists():
            # File yang akan di-index dari codebase
            source_files = [
                ("services/member_service.py", "module_summary"),
                ("services/parking_service.py", "module_summary"),
                ("services/auth_service.py", "module_summary"),
                ("services/device_service.py", "module_summary"),
                ("services/audit_service.py", "module_summary"),
                ("utils/ui_helpers.py", "module_summary"),
            ]
            logger.info(f"\nMeng-index {len(source_files)} file source code dari {workspace_path}...")
            for rel_path, category in source_files:
                abs_path = str(ws / rel_path)
                if Path(abs_path).exists():
                    ok = rag_index_file(abs_path, category=category)
                    status = "OK" if ok else "FAIL"
                    logger.info(f"  [{status}] {rel_path}")
                    if ok:
                        success_count += 1
                    else:
                        failed_count += 1
                else:
                    logger.warning(f"  [!] File tidak ditemukan: {rel_path}")

    total = success_count + failed_count
    logger.info("=" * 60)
    logger.info(f"Selesai! Berhasil: {success_count}/{total} chunk/file di-index ke RAG.")

    return {
        "success": success_count,
        "failed": failed_count,
        "total": total,
    }


def reset_project_memory() -> bool:
    """
    Mereset semua memori RAG untuk project smart-parking.
    Gunakan dengan hati-hati — menghapus semua chunk yang sudah di-index.
    """
    try:
        import requests
        resp = requests.post(
            f"{RAG_API_BASE}/api/v1/project/{RAG_PROJECT_ID}/reset",
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"Project memory '{RAG_PROJECT_ID}' berhasil direset.")
            return True
        logger.warning(f"Reset gagal: HTTP {resp.status_code}")
        return False
    except Exception as e:
        logger.error(f"Reset error: {e}")
        return False


# ==============================================================================
# Entry Point — jalankan langsung sebagai script
# ==============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="RAG Indexing Tool untuk Smart Parking Documentation"
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Path ke folder webSmartParking untuk index file source code (opsional)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset semua memori RAG sebelum meng-index ulang",
    )
    parser.add_argument(
        "--search",
        type=str,
        default=None,
        help="Cari query di RAG untuk testing (tidak index, hanya search)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Smart Parking - RAG Documentation Indexer")
    print("=" * 60)

    if not is_rag_available():
        print(f"\n[!] RAG API tidak bisa diakses di {RAG_API_BASE}")
        print("   Pastikan RAG service sudah berjalan:")
        print("   cd rag_service_project")
        print("   .venv\\Scripts\\python -m uvicorn api.main:app --host 127.0.0.1 --port 8001 --reload")
        sys.exit(1)

    print(f"\n[+] RAG API aktif di {RAG_API_BASE}")

    if args.search:
        print(f"\n[?] Mencari: '{args.search}'\n")
        results = rag_search(args.search, limit=5)
        if not results:
            print("Tidak ada hasil.")
        for i, r in enumerate(results, 1):
            print(f"--- Hasil {i} (score: {r.get('score', 0):.3f}) ---")
            print(f"Source : {r.get('source')}")
            print(f"Category: {r.get('category')}")
            print(f"Content : {r.get('content', '')[:300]}...")
            print()
        sys.exit(0)

    if args.reset:
        print("\n[!] Mereset project memory RAG...")
        reset_project_memory()

    print(f"\n[*] Meng-index dokumentasi Smart Parking ke RAG...")
    if args.workspace:
        print(f"   Workspace: {args.workspace}")

    result = index_all_documents(workspace_path=args.workspace)

    print(f"\n{'=' * 60}")
    print(f"  Hasil: {result['success']} berhasil, {result['failed']} gagal dari {result['total']} total")
    print(f"{'=' * 60}")

    if result["failed"] > 0:
        sys.exit(1)
