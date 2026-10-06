# TRD — Smart Parking Monitoring & RFID Member System (Enhanced Version)

## 1. Document Purpose

Dokumen **Technical Requirements Document (TRD)** ini merinci arsitektur teknis, spesifikasi hardware & firmware, alur FreeRTOS multi-core, skema database Supabase, protokol sinkronisasi cloud dua arah (2-Way Sync), struktur backend Python Streamlit berbasis **Selective Realtime Fragments (`@st.fragment`)**, algoritma **Anti-Passback**, sistem **Audit Forensik Kendaraan & Deteksi Tailgating**, serta mitigasi kestabilan jaringan untuk implementasi sistem **Smart Parking Monitoring & RFID Member System**.

Dokumen ini menjadi acuan tunggal teknis bagi implementasi firmware C++ (ESP32-S3), konfigurasi cloud (Supabase PostgreSQL / PostgREST), dan aplikasi web dashboard (Streamlit).

---

# 2. System Architecture Overview

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                        USER ACCESS LAYER                               │
 │             Admin Browser                      Student Browser         │
 └──────────────────────┬────────────────────────────────┬────────────────┘
                        │                                │
                        ▼                                ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                     STREAMLIT PYTHON BACKEND                           │
 │                                                                        │
 │  • app.py (Router & Authentication Handler)                           │
 │  • pages/1_Monitoring_Parkir.py (Targeted Fragment: Slots & Devices)   │
 │  • pages/2_Member_RFID.py (Targeted Fragment: Anti-Passback & Audit)  │
 │  • pages/3_IoT_Device.py (Targeted Fragment: Online Status & Keys)     │
 │  • pages/4_Monitoring_Sensor.py (Targeted Fragment: Telemetry Graphs)  │
 │  • pages/5_Dashboard_Siswa.py (Targeted Fragment: Workspace & Sim)     │
 │  • pages/6_Manajemen_User.py (User CRUD & Device Association)          │
 │  • services/                                                          │
 │    - audit_service.py (Anti-Passback, Forensics, Tailgating, SVG HUD) │
 │    - member_service.py (Passback Validation, UID normalization, CRUD) │
 │    - parking_service.py (Slot metrics, digital IR evaluation)         │
 │    - device_service.py (Heartbeat, telemetry, C++ snippets)           │
 │    - supabase_client.py (Resilient client with WinError 10035 retry)  │
 │                                                                        │
 │  [Network Layer: httpx with HTTPTransport retries=3]                   │
 └──────────────────────────────────┬─────────────────────────────────────┘
                                    │ HTTPS REST API
                                    ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                        SUPABASE CLOUD                                  │
 │                                                                        │
 │  • PostgreSQL 15+ Database Engine                                      │
 │  • PostgREST API with Duplicate Resolution (`resolution=merge-dups`)   │
 │  • Tables: app_users, iot_devices, parking_slots,                      │
 │            parking_members (inside_parking), rfid_scans,               │
 │            sensor_data, audit_forensic_logs                            │
 └──────────────────────────────────▲─────────────────────────────────────┘
                                    │ HTTPS (WiFi 2.4 GHz)
                                    │ Upsert Payloads & Polling
 ┌──────────────────────────────────┴─────────────────────────────────────┐
 │                ESP32-S3 UNIFIED CONTROLLER (FreeRTOS)                  │
 │                                                                        │
 │  ┌─────────────────────────────────┐ ┌───────────────────────────────┐ │
 │  │ CORE 0: Network & Audio         │ │ CORE 1: Physical Edge Control │ │
 │  ├─────────────────────────────────┤ ├───────────────────────────────┤ │
 │  │ • TaskNetwork                   │ │ • TaskUltrasonic (Gate Jarak) │ │
 │  │   - WiFi State Machine          │ │ • TaskSlotIR (3x IR Slots)    │ │
 │  │   - Command Poll (2.5s)         │ │ • TaskGate (Servo, Tailgate)  │ │
 │  │   - Batch Slot Upsert (5s)      │ │ • TaskRFID (Passback/Reg Mode)│ │
 │  │   - Heartbeat Sync (10s)        │ │ • TaskLCD (16x2 Anti-Flicker) │ │
 │  │ • TaskBuzzer (Async Melody)     │ └───────────────────────────────┘ │
 │  └─────────────────────────────────┘                                   │
 │    [Inter-Task Semaphores & Queues for Thread Safety]                 │
 └────────────────────────────────────────────────────────────────────────┘
```

---

# 3. Hardware Requirements & Specifications

## 3.1 Microcontroller Unit
- **SoC**: ESP32-S3-WROOM-1 / ESP32-S3 DevKit
- **CPU**: Dual-Core 32-bit Xtensa® LX7, hingga 240 MHz
- **Memory**: 512 KB SRAM, 8 MB Flash, 2 MB PSRAM (opsional)
- **Konektivitas**: 2.4 GHz Wi-Fi (802.11 b/g/n), Bluetooth 5 (LE)
- **Tegangan Operasional**: 3.3V DC (Input VIN: 5V DC via Micro-USB / Type-C)

## 3.2 Pin Mapping (Firmware Reference)

Seluruh pin berikut telah diverifikasi bebas konflik dengan SPI internal flash/PSRAM ESP32-S3:

| No | Perangkat Hardware | Fungsi Pin | GPIO ESP32-S3 | Karakteristik Sinyal | Keterangan Sirkuit |
|:---:|:---|:---|:---:|:---|:---|
| 1 | **Servo SG90 / MG995** | Signal (PWM) | **GPIO 4** | PWM 50 Hz (LEDC) | 0° = Tutup, 90° = Buka |
| 2 | **LCD 16x2 (PCF8574)** | SDA | **GPIO 16** | I2C Data (400 kHz) | Pull-up internal / board I2C |
| 3 | **LCD 16x2 (PCF8574)** | SCL | **GPIO 17** | I2C Clock (400 kHz) | Address: 0x27 |
| 4 | **Buzzer Aktif/Pasif** | Positive (+) | **GPIO 27** | PWM / Tone Frequency | Driver transistor 2N2222 / direct |
| 5 | **HC-SR04 Ultrasonic** | TRIG | **GPIO 25** | Digital Output (10µs) | Trigger pulsa ultrasonic |
| 6 | **HC-SR04 Ultrasonic** | ECHO | **GPIO 26** | Digital Input | Voltage divider 5V ke 3.3V (1kΩ/2kΩ) |
| 7 | **IR Sensor Slot 1** | DOUT | **GPIO 32** | Digital Input (Active-LOW)| Slot `P01`: 0 = Terisi, 1 = Kosong |
| 8 | **IR Sensor Slot 2** | DOUT | **GPIO 33** | Digital Input (Active-LOW)| Slot `P02`: 0 = Terisi, 1 = Kosong |
| 9 | **IR Sensor Slot 3** | DOUT | **GPIO 35** | Digital Input (Active-LOW)| Slot `P03`: 0 = Terisi, 1 = Kosong |
| 10| **RC522 RFID Reader** | SDA / SS | **GPIO 5** | SPI Chip Select | Logic Level 3.3V |
| 11| **RC522 RFID Reader** | SCK | **GPIO 18** | SPI Clock | Logic Level 3.3V |
| 12| **RC522 RFID Reader** | MOSI | **GPIO 23** | SPI Master Out | Logic Level 3.3V |
| 13| **RC522 RFID Reader** | MISO | **GPIO 19** | SPI Master In | Logic Level 3.3V |
| 14| **RC522 RFID Reader** | RST | **GPIO 22** | Digital Reset | Reset modul MFRC522 |

---

# 4. Sensor Logic & Calibration Standards

## 4.1 Ultrasonic HC-SR04 (Gate Presence & Tailgate Detection)
- **Ambang Batas Kehadiran Mobil Normal**: $\le 20.0\text{ cm}$.
- **Histeresis**: Kehadiran dinyatakan hilang jika jarak $> 25.0\text{ cm}$ atau pembacaan *timeout* (0.0 cm).
- **Deteksi Mobil Membuntuti (Tailgating)**:
  - Jika setelah satu kendaraan melewati palang (transisi jarak dari $\le 20\text{cm} \rightarrow > 25\text{cm}$), sensor kembali mendeteksi jarak $\le 20\text{cm}$ dalam jendela waktu $< 1.5\text{ detik}$ sebelum siklus servo selesai dan tanpa transaksi RFID baru, insiden diklasifikasikan sebagai **TAILGATING**.
  - ESP32 membunyikan alarm terus-menerus, LCD menampilkan `TAILGATING DETECTED!`, dan event dicatat ke `audit_forensic_logs`.

## 4.2 Sensor Slot IR (Digital Active-LOW)
- **Nilai Logika 0 (LOW)**: Pancaran inframerah terhalang oleh bodi kendaraan $\rightarrow$ Status: `occupied` (TERISI).
- **Nilai Logika 1 (HIGH)**: Pancaran inframerah tidak memantul / bebas $\rightarrow$ Status: `available` (KOSONG).
- **Sampling & Debouncing**: Sensor dibaca dengan interval 50ms dengan akumulasi debouncing 5 sampel berturut-turut untuk menyaring derau optik/cahaya sekitar.

## 4.3 Kunci Kesiapan Sistem & Dormansi Sensor (System Readiness Gate Lock & Sensor Dormancy)
- **Aturan Operasional Mutlak**: Sebelum sistem dinyatakan siap (`sharedSystemReady == true`), seluruh sensor dan aktuator **DIKUNCI SECARA PENUH (Dormant Mode)**:
  1. **Sensor Ultrasonic (HC-SR04)**: Dilarang menembakkan pulsa trigger (`PIN_TRIG`) dan dilarang membaca durasi echo. `readDistance()` tidak dieksekusi.
  2. **Sensor IR 3 Slot Parkir**: Dilarang membaca level logika digital pin IR (`PIN_IR_SLOT1..3`). Status slot tidak diperbarui.
  3. **RFID Reader (MFRC522)**: Dilarang melakukan polling kartu (`PICC_IsNewCardPresent`) atau membangunkan kartu (`PICC_WakeupA`). Seluruh tap fisik diabaikan.
  4. **Aktuator Palang Gerbang (Servo)**: Tetap dikunci pada sudut 0° (tertutup rapat). Sinyal pemicu buka gerbang diabaikan jika sistem belum siap.
  5. **Telemetri Serial & Cloud**: Serial monitor tidak mengeluarkan log sensor berkala, dan `TaskNetwork` tidak mengirimkan batch upsert slot maupun jarak ultrasonik ke Supabase.
- **Fail-Safe Disconnection**: Jika koneksi WiFi terputus saat sistem sedang berjalan, flag `sharedSystemReady` otomatis diubah ke `false`, LCD menampilkan `MEMUAT SISTEM ... WiFi Putus`, dan seluruh sensor seketika kembali ke mode dorman hingga rekoneksi berhasil.

---

# 5. Algoritma Anti-Passback & Audit Forensik

## 5.1 Skema State Machine Anti-Passback

```text
                  ┌──────────────────────────────┐
                  │    KENDARAAN DI LUAR AREA    │
                  │    (inside_parking = False)  │
                  └──────────────┬───────────────┘
                                 │
                 Tap Kartu Valid │ Tap Kartu Valid
                 di Gerbang MASUK│ di Gerbang KELUAR
                                 │ (Passback Unmatched)
                                 ▼
                     [ EVALUASI AKSES MASUK ]
                     ├── Kartu Belum Terdaftar   ──> Ditolak (unregistered)
                     ├── Status Kartu INACTIVE   ──> Ditolak (inactive)
                     ├── inside_parking == True  ──> DITOLAK: ANTI-PASSBACK VIOLATION!
                     │                               (Alarm, Snapshot HUD, LCD Alert)
                     └── inside_parking == False ──> DITERIMA: Akses Diberikan
                                                     (inside_parking := True,
                                                      Catat Snapshot Masuk,
                                                      Servo Buka 90°)
                                 │
                                 ▼
                  ┌──────────────────────────────┐
                  │    KENDARAAN DI DALAM AREA   │
                  │    (inside_parking = True)   │
                  └──────────────┬───────────────┘
                                 │
                 Tap Kartu Valid │ Tap Kartu Lagi
                 di Gerbang KELUAR│ di Gerbang MASUK
                                 │ (Pelanggaran Anti-Passback)
                                 ▼
                     [ EVALUASI AKSES KELUAR ]
                     └── inside_parking == True  ──> DITERIMA: Akses Keluar Diberikan
                                                     (inside_parking := False,
                                                      Catat Snapshot Keluar,
                                                      Servo Buka 90°)
```

## 5.2 Snapshot HUD Forensik Vektor SVG

Setiap transaksi gerbang menghasilkan snapshot visual HUD vektor SVG beresolusi tinggi (640x360 piksel) yang disintesis secara deterministik oleh `services/audit_service.py`:
- Menampilkan siluet model kendaraan (sedan/SUV/motor).
- Reticle HUD forensik dengan garis scan optik, indikator bounding box plat nomor, timestamp presisi milidetik, Device ID, dan status otorisasi (`ENTRY GRANTED`, `ANTI-PASSBACK VIOLATION`, `TAILGATING DETECTED`).
- Format SVG bebas dependensi library eksternal (OpenCV/Pillow) dan dapat langsung dirender di browser Streamlit via `st.image()` dengan performa loading instan.

---

# 6. Arsitektur Realtime Component Fragment (`@st.fragment`)

## 6.1 Masalah Polling Tradisional
Pada versi lama yang menggunakan `st_autorefresh` atau meta refresh, seluruh skrip Python dijalankan ulang dari baris pertama:
- Seluruh DOM browser berkedip (white flash).
- Pengguna yang sedang mengisi form (nama member, nomor plat, formulir registrasi) kehilangan fokus dan input teksnya terhapus.
- Posisi scroll halaman kembali ke paling atas.

## 6.2 Solusi Targeted Realtime Fragment
Framework membungkus fungsi tampilan dinamis dengan decorator `@realtime_fragment(run_every="3s")` (`utils/ui_helpers.py`):
```python
@realtime_fragment(run_every="3s")
def render_live_slot_grid(supabase, device_id):
    slots = get_parking_slots(supabase)
    # Render metrik dan kartu slot parkir saja...
```

**Mekanisme Kerja**:
1. Streamlit membuka koneksi WebSocket persisten dua arah ke browser.
2. Ketika interval timer fragment (misal: 3 detik) tercapai, Streamlit mengeksekusi **hanya fungsi yang didekorasi**.
3. Komparator virtual-DOM Streamlit menghitung perbedaan (delta) dan mengirimkan paket JSON patch mini ke browser.
4. Browser hanya memperbarui elemen HTML target di dalam container fragment tanpa me-reload sisa halaman.
5. Form isian di luar fragment (seperti form registrasi member) tetap 100% interaktif tanpa pernah kehilangan teks atau fokus.

---

# 7. Supabase Database Schema & DDL

Database PostgreSQL pada Supabase menggunakan DDL berikut:

## 7.1 Table: `app_users`
```sql
create table if not exists app_users (
    id bigint generated by default as identity primary key,
    username text unique not null,
    password_hash text not null,
    full_name text not null,
    role text not null check (role in ('admin', 'student')),
    created_at timestamptz default now()
);
```

## 7.2 Table: `iot_devices`
```sql
create table if not exists iot_devices (
    id bigint generated by default as identity primary key,
    device_id text unique not null,
    device_name text,
    device_type text default 'esp32_master',
    owner_name text default 'Lab IoT',
    api_key text unique,
    status text default 'offline' check (status in ('online', 'offline', 'registering')),
    last_seen timestamptz default now()
);
```

## 7.3 Table: `parking_slots`
```sql
create table if not exists parking_slots (
    id bigint generated by default as identity primary key,
    slot_code text unique not null,
    status text default 'available' check (status in ('available', 'occupied', 'offline')),
    sensor_value integer default 1,
    device_id text references iot_devices(device_id) on delete set null,
    updated_at timestamptz default now()
);
```

## 7.4 Table: `parking_members` (Dengan Flag Anti-Passback)
```sql
create table if not exists parking_members (
    id bigint generated by default as identity primary key,
    rfid_uid text unique not null,
    member_name text not null,
    license_plate text not null,
    vehicle_type text default 'car',
    status text default 'active' check (status in ('active', 'inactive')),
    inside_parking boolean default false,
    created_at timestamptz default now()
);
```

## 7.5 Table: `rfid_scans`
```sql
create table if not exists rfid_scans (
    id bigint generated by default as identity primary key,
    uid text not null,
    device_id text,
    created_at timestamptz default now()
);
```

## 7.6 Table: `sensor_data`
```sql
create table if not exists sensor_data (
    id bigint generated by default as identity primary key,
    device_id text,
    sensor_type text check (sensor_type in ('ultrasonic', 'ir')),
    sensor_value double precision not null,
    created_at timestamptz default now()
);
```

## 7.7 Table: `audit_forensic_logs` (Forensik & Tailgating)
```sql
create table if not exists audit_forensic_logs (
    id bigint generated by default as identity primary key,
    event_type text not null check (event_type in ('entry', 'exit', 'anti_passback_violation', 'tailgating')),
    rfid_uid text,
    license_plate text,
    member_name text,
    device_id text default 'GATE-01',
    photo_url text,
    notes text,
    created_at timestamptz default now()
);
```

---

# 8. Cloud API Endpoints & Upsert Specifications

Seluruh transmisi HTTP ke Supabase PostgREST mematuhi protokol upsert bebas HTTP 409:

## 8.1 Slot Status Batch Upsert
- **URL**: `https://<SUPABASE_PROJECT_ID>.supabase.co/rest/v1/parking_slots?on_conflict=slot_code`
- **Headers**:
  ```http
  apikey: <SUPABASE_KEY>
  Authorization: Bearer <SUPABASE_KEY>
  Content-Type: application/json
  Prefer: resolution=merge-duplicates
  ```
- **Payload**:
  ```json
  [
    {"slot_code": "P01", "status": "available", "sensor_value": 1, "device_id": "GATE-01"},
    {"slot_code": "P02", "status": "available", "sensor_value": 1, "device_id": "GATE-01"},
    {"slot_code": "P03", "status": "occupied", "sensor_value": 0, "device_id": "GATE-01"}
  ]
  ```

## 8.2 Device Heartbeat Upsert
- **URL**: `https://<SUPABASE_PROJECT_ID>.supabase.co/rest/v1/iot_devices?on_conflict=device_id`
- **Headers**: `Prefer: resolution=merge-duplicates`
- **Payload**:
  ```json
  {
    "device_id": "GATE-01",
    "status": "online",
    "last_seen": "2026-10-06T03:00:00Z"
  }
  ```

---

# 9. Resilience & Windows Socket Mitigation

Pada sistem operasi Windows, klien HTTP asinkron/sinkron kerap mengalami exception socket:
`ReadError: [WinError 10035] A non-blocking socket operation could not be completed immediately`

### Solusi Arsitektural Python (`services/supabase_client.py`):
1. Mengonfigurasi `httpx.HTTPTransport` dengan parameter `retries=3`.
2. Menerapkan timeout kustom: `connect=10.0s`, `read=20.0s`, `write=15.0s`.
3. Membungkus eksekusi query PostgREST dalam blok `try-except` dengan *exponential backoff* 200ms jika socket sistem Windows belum siap membaca buffer.

---

# 10. Security & Operational Safety

1. **Pencegahan Kontrol Gerbang Manual di Web**:
   - Web application secara absolut **TIDAK MEMILIKI** tombol buka/tutup palang gerbang manual demi menjaga keselamatan fisik pengemudi dan kendaraan di lapangan.
2. **Validasi Anti-Passback**:
   - Mencegah penggunaan berulang satu kartu member pada sesi masuk yang sama.
3. **Kredensial IoT Berbasis Token Mandiri**:
   - Setiap perangkat siswa terdaftar memiliki `api_key` unik (`sk_dev_...`).

---

# 11. Arsitektur Layanan Manajemen Data Menyeluruh (CRUD Backend Services)

Untuk mendukung perawatan data dan kontrol menyeluruh oleh Administrator dan Siswa, sistem mengimplementasikan lapisan CRUD terpadu pada `services/`:

### 11.1 Layanan Slot Parkir (`services/parking_service.py`)
- `create_parking_slot(supabase, slot_code: str, device_id: Optional[str] = None) -> Dict[str, Any]`
  - Validasi keunikan kode slot (mencegah duplikasi). Status default diatur ke `'available'`.
- `update_parking_slot(supabase, slot_code: str, new_slot_code: Optional[str] = None, status: Optional[str] = None, sensor_value: Optional[int] = None, device_id: Any = "KEEP_EXISTING") -> Dict[str, Any]`
  - Memperbarui parameter slot, mendukung pengubahan nama slot, pemaksaan status, dan pelepasan/pengaitan perangkat IoT (`device_id=None`).
- `delete_parking_slot(supabase, slot_code: str) -> bool`
  - Menghapus baris slot parkir dari tabel `parking_slots`.

### 11.2 Layanan Perangkat IoT (`services/device_service.py`)
- `update_device(supabase, device_id: str, device_name: Optional[str] = None, owner_name: Optional[str] = None, device_type: Optional[str] = None) -> Dict[str, Any]`
  - Memperbarui metadata perangkat IoT yang terdaftar di `iot_devices`.
- `delete_device(supabase, device_id: str) -> bool`
  - Menghapus perangkat IoT secara permanen dari sistem.

### 11.3 Layanan Pengguna & RBAC (`services/auth_service.py`)
- `update_user_profile(supabase, username: str, full_name: Optional[str] = None, role: Optional[str] = None, device_id: Any = "KEEP_EXISTING") -> Dict[str, Any]`
  - Memperbarui profil akun pengguna secara atomik (nama lengkap, peran administrator/siswa, dan penautan perangkat).
- `delete_user(supabase, username_to_delete: str, current_admin_username: Optional[str] = None) -> bool`
  - Menghapus akun pengguna dari `app_users` dengan pencegahan penghapusan diri sendiri (*anti-self-deletion safeguard*).

### 11.4 Layanan Audit Forensik (`services/audit_service.py`)
- `delete_audit_log(supabase, log_id: int) -> bool`
  - Menghapus rekaman log insiden gerbang individual.
- `clear_all_audit_logs(supabase) -> bool`
  - Mengosongkan seluruh tabel `audit_forensic_logs` saat pembersihan berkala.

### 11.5 Layanan Sensor & Telemetri (`services/sensor_service.py`)
- `delete_sensor_reading(supabase, reading_id: int) -> bool`
  - Menghapus rekaman pembacaan telemetri individual.
- `clear_sensor_data_by_device(supabase, device_id: str) -> bool`
  - Menghapus seluruh data telemetri historis dari perangkat tertentu.

### 11.6 Layanan Member & Riwayat Scan RFID (`services/member_service.py`)
- `update_member(supabase, member_id: Any, member_name: str, license_plate: str, vehicle_type: str, status: str) -> Dict[str, Any]`
  - Mendukung penargetan berdasarkan integer ID atau string `rfid_uid`.
- `delete_member(supabase, member_id: Any) -> bool`
  - Menghapus keanggotaan kartu RFID secara permanen.
- `delete_rfid_scan(supabase, scan_id: int) -> bool`
  - Menghapus satu log pembacaan RFID.
- `clear_rfid_scans_by_device(supabase, device_id: str) -> bool`
  - Mengosongkan seluruh log scan kartu RFID yang dikirim oleh perangkat tertentu.

---

# 12. Technical Acceptance Verification

Sistem dinyatakan memenuhi seluruh standar teknis TRD apabila:
1. Pembacaan dinamis web berjalan menggunakan **Selective Realtime Fragments** tanpa reload halaman utuh.
2. Algoritma Anti-Passback menolak akses saat `inside_parking == True` pada gerbang masuk.
3. Insiden Tailgating dan pelanggaran tercatat rapi pada tabel `audit_forensic_logs` lengkap dengan snapshot HUD.
4. Firmware FreeRTOS mengunci sistem saat booting hingga WiFi stabil dan menampilkan status pada LCD 16x2. Seluruh sensor dorman total sebelum sistem siap.
5. Manajemen CRUD pada seluruh entitas sistem (Member, Slot, Device, User, Sensor Data, RFID Scans, Audit Logs) berfungsi dengan aman dan terverifikasi.
6. Seluruh test suite unit & integrasi lulus 100% (130 passed tests).
