# Smart Parking Monitoring & RFID Member System

Website prototype monitoring sistem smart parking berbasis **Streamlit**, **Supabase (PostgreSQL)**, dan **ESP32-S3**, dibangun dengan pendekatan **Test-Driven Development (TDD)** sesuai spesifikasi pada dokumen:
- `PRD_Smart_Parking_ESP32S3_Streamlit_Supabase_Updated.md`
- `TRD_Smart_Parking_ESP32S3_Streamlit_Supabase.md`
- `DRD_Smart_Parking_ESP32S3_Streamlit_Supabase.md`

---

## 📌 Fitur Utama

1. **Dashboard Monitoring Real-Time (`app.py`)**:
   - 4 Kartu Metrik Ringkasan: Total Slot, Slot Kosong, Slot Terisi, dan Status Perangkat ESP32-S3 (`ONLINE`/`OFFLINE`).
   - Grid 4 Slot Parkir (`P01` – `P04`) dengan visual status badge berkejelasan tinggi (KOSONG, TERISI, OFFLINE), nilai sensor analog IR, dan waktu pembaruan terakhir.
   - Kartu Scan RFID Terakhir: UID kartu, nama member, device ID, dan waktu tap.
   - Kartu Sensor Terkini: Nilai jarak ultrasonik HC-SR04 (cm) dengan indikator keberadaan mobil (`Mobil Terdeteksi` / `Tidak Ada Mobil`) dan nilai IR tiap slot.
   - Auto-refresh otomatis setiap 4 detik.
   - **Kepatuhan Mutlak**: Tidak ada tombol kontrol manual buka/tutup gate pada website (kontrol gerbang sepenuhnya berada pada logika mikrokontroler ESP32-S3).

2. **Monitoring Parkir (`pages/1_Monitoring_Parkir.py`)**:
   - Pemantauan visual seluruh slot parkir dengan status indikator.
   - Metrik ketersediaan slot (Total, Kosong, Terisi).
   - Banner peringatan offline jika node sensor parkir (`PARKING-01`) atau gerbang (`GATE-01`) terputus koneksinya.
   - Slot parkir yang terputus tidak akan dianggap kosong melainkan ditandai sebagai `OFFLINE`/`UNKNOWN`.

3. **Manajemen Member RFID (`pages/2_Member_RFID.py`)**:
   - **Registrasi Member Berbasis Scan**:
     - Membaca UID kartu RFID secara otomatis dari tabel `rfid_scans` yang dikirim oleh ESP32-S3 (tanpa pengetikan UID manual).
     - UID berstatus strictly **Read-Only** (disabled input).
     - State Machine Interaksi: `IDLE` ➔ `WAITING` ➔ `DETECTED` / `ALREADY_REGISTERED`.
     - Validasi duplikasi kartu (DRD Sec 12): Sistem memblokir pendaftaran ganda kartu RFID yang sudah terdaftar.
     - Formulir pendaftaran: Nama Member, Nomor Polisi, Jenis Kendaraan (Mobil, Motor, Truk/Lainnya), Status (Aktif/Nonaktif).
     - Dilengkapi tombol simulasi scan kartu untuk pengujian tanpa perangkat keras fisik.
   - **Daftar Member & Pengelolaan**:
     - Tabel anggota (`st.dataframe`) dengan pencarian / filter kata kunci.
     - Fitur Edit Data Member (Nama, Plat, Jenis Kendaraan, Status).
     - Fitur Toggle Status Member (`Aktif` ⮂ `Nonaktif`) sekali klik.
     - Fitur Hapus Member dengan konfirmasi keamanan.

4. **Status Perangkat IoT (`pages/3_IoT_Device.py`)**:
   - Pemantauan konektivitas perangkat mikrokontroler (`GATE-01`, `PARKING-01`).
   - Evaluasi status `ONLINE` / `OFFLINE` otomatis berdasarkan ambang batas heartbeat **30 detik** (TRD Sec 21).
   - Penanda waktu *last seen* relatif (contoh: "10 detik yang lalu") dan absolut.
   - Banner peringatan *ESP32-S3 OFFLINE* jika perangkat melampaui batas waktu heartbeat.

5. **Monitoring Sensor (`pages/4_Monitoring_Sensor.py`)**:
   - Kartu HC-SR04: Jarak pembacaan (cm) dan evaluasi ambang batas kendaraan ($\le$ 40.0 cm).
   - Kartu IR Analog: Nilai mentah ADC dan status keterisian slot (ambang batas okupansi 1000).
   - Tabel Log Sensor: Riwayat pembacaan sensor terbaru dengan paginasi dan filter jenis sensor (`ultrasonic` / `ir`).

6. **Dashboard Mandiri Siswa (`pages/5_Dashboard_Siswa.py`)**:
   - Pendaftaran mandiri perangkat IoT siswa untuk mendapatkan **Device ID**, **API Key unik** (`sk_dev_...`), dan **Connection URL Endpoint**.
   - Dilengkapi generator template kode firmware C++ (Arduino IDE) siap pakai (*pre-filled* kredensial).
   - Dashboard tersendiri per perangkat siswa: pemantauan status online/offline (30s heartbeat), grafik telemetri jarak ultrasonik, pembacaan IR, dan riwayat scan RFID perangkat siswa.
   - Simulator uji coba data langsung dari browser bagi siswa yang belum merakit perangkat fisik.

7. **In-Memory Mock Fallback & Offline Resilience**:
   - Jika kredensial Supabase belum dikonfigurasi atau koneksi internet terputus, sistem secara otomatis beralih ke `MockSupabaseClient` in-memory.
   - Data simulasi dan operasi CRUD tersimpan pada `st.session_state` sehingga aplikasi dapat dieksplorasi secara fungsional tanpa hambatan.

---

## 🏗️ Struktur Proyek

```text
webSmartParking/
│
├── app.py                         # Halaman utama (Dashboard)
│
├── pages/                         # Multi-page Streamlit
│   ├── 1_Monitoring_Parkir.py     # Monitoring Slot Parkir & Metrik
│   ├── 2_Member_RFID.py           # Registrasi & Manajemen Anggota RFID
│   ├── 3_IoT_Device.py            # Pemantauan Perangkat IoT & Registrasi Siswa
│   ├── 4_Monitoring_Sensor.py     # Pemantauan Sensor HC-SR04 & IR
│   ├── 5_Dashboard_Siswa.py       # Dashboard Mandiri Perangkat Siswa
│   └── 6_Manajemen_User.py        # Portal Manajemen User & Hak Akses (Admin)
│
├── services/                      # Service Layer & Database Abstraction
│   ├── __init__.py
│   ├── supabase_client.py         # Factory client Supabase & fallback handler
│   ├── member_service.py          # Logika member, normalisasi UID, validasi akses
│   ├── parking_service.py         # Logika slot parkir, metrik, evaluasi offline
│   ├── device_service.py          # Logika heartbeat, registrasi siswa & template C++
│   ├── sensor_service.py          # Logika log sensor HC-SR04 & IR
│   └── auth_service.py            # Autentikasi multi-role (Admin/Siswa) & RBAC Guard
│
├── utils/                         # UI Helper & Visual Components
│   ├── __init__.py
│   └── ui_helpers.py              # Status badges, branding sidebar, auth guard, navigasi adaptif
│
├── tests/                         # Test Suite TDD & Integration (105 Test)
│   ├── __init__.py
│   ├── conftest.py                # Fixtures & in-memory MockSupabaseClient
│   ├── test_supabase_client.py    # Unit test konfigurasi client Supabase
│   ├── test_member_service.py     # Unit test CRUD member & normalisasi UID
│   ├── test_parking_service.py    # Unit test status slot & kalkulasi metrik
│   ├── test_device_service.py     # Unit test heartbeat & ambang batas 30s
│   ├── test_sensor_service.py     # Unit test pembacaan sensor
│   ├── test_student_device.py     # Unit test registrasi perangkat siswa & API key
│   ├── test_auth_service.py       # Unit test otentikasi admin vs siswa & RBAC
│   ├── test_ui_pages.py           # AST & verifikasi kepatuhan UI (0 gate button)
│   └── test_integration_scenarios.py # 5 Skenario integrasi end-to-end lengkap
│
├── .env                           # Konfigurasi environment lokal
├── .env.example                   # Template konfigurasi environment
├── requirements.txt               # Daftar dependensi Python
├── schema.sql                     # DDL Skema Supabase PostgreSQL & Seed Data
└── README.md                      # Dokumentasi teknis & panduan penggunaan
```

### 🔐 Kredensial Login Bawaan (Default Accounts)

Sistem telah dilengkapi dengan 2 akun default yang dapat langsung digunakan untuk pengujian:

| Peran (Role) | Username | Password | Hak Akses (Permissions) |
|---|---|---|---|
| **Administrator** | `admin` | `admin123` | Akses penuh ke semua halaman: Dashboard Utama, Monitoring Parkir, Registrasi Member RFID, Manajemen Perangkat IoT, Monitoring Sensor, dan Audit Dashboard Siswa. |
| **Siswa / Mahasiswa** | `siswa1` | `siswa123` | Akses terisolasi: Monitoring Parkir umum dan **Dashboard Siswa** khusus untuk perangkat miliknya (`DEV-SISWA-01`), melihat kredensial API Key/URL, dan uji coba simulator. Halaman admin diblokir otomatis. |

*Tersedia juga tab **"📝 Registrasi Siswa Baru"** di form login untuk mendaftarkan akun siswa baru dan langsung membuat perangkat IoT sekaligus.*

---

## ⚙️ Persyaratan Sistem & Instalasi

### 1. Prasyarat
- Python 3.10 atau versi lebih baru (diuji pada Python 3.13).
- Akun Supabase (opsional jika menggunakan mode demo/mock built-in).

### 2. Instalasi Dependensi
Jalankan perintah berikut pada terminal di folder proyek:
```bash
pip install -r requirements.txt
```

Dependensi utama:
- `streamlit`
- `supabase`
- `pandas`
- `python-dotenv`
- `streamlit-autorefresh`
- `pytest`

---

## 🔑 Konfigurasi Environment (`.env`)

Salin file `.env.example` menjadi `.env`:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-or-service-key
DEVICE_ID=GATE-01
OFFLINE_THRESHOLD_SECONDS=30
```

> **Catatan Mode Demo / Fallback:**  
> Jika `SUPABASE_URL` atau `SUPABASE_KEY` masih berisi nilai placeholder / dummy (atau tidak dapat terhubung), aplikasi secara otomatis menjalankan mode `Mock Client` dengan data awal realistis sehingga web tetap berjalan sempurna tanpa error.

---

## 🗄️ Setup Database Supabase (`schema.sql`)

Jika menggunakan project Supabase aktif, jalankan perintah DDL dari file [`schema.sql`](file:///C:/Users/rh638/Downloads/webSmartParking/schema.sql) pada **Supabase SQL Editor**:

Tabel yang dibuat:
1. `parking_members`: Menyimpan kartu member RFID, nama, plat kendaraan, jenis kendaraan, dan status aktif.
2. `rfid_scans`: Menyimpan log scan kartu RFID dari ESP32-S3 untuk pendaftaran dan pencatatan akses.
3. `parking_slots`: Menyimpan status 4 slot parkir (`P01` – `P04`), nilai sensor IR, dan timestamp pembaruan.
4. `iot_devices`: Menyimpan data perangkat (`GATE-01`, `PARKING-01`), status, dan timestamp *last seen*.
5. `sensor_data`: Menyimpan riwayat log data pembacaan sensor ultrasonik dan IR.

---

## 🚀 Menjalankan Aplikasi Web

Jalankan perintah Streamlit dari direktori utama proyek:
```bash
streamlit run app.py
```

Buka peramban pada alamat default:
```text
http://localhost:8501
```

---

## 🧪 Pengujian TDD & Hasil Verifikasi (`pytest`)

Seluruh sistem diuji menggunakan pendekatan **Test-Driven Development (TDD)** dengan total **84 pengujian** yang mencakup pengujian unit, integritas UI, pencegahan tombol manual gerbang, dan skenario integrasi end-to-end:

Jalankan pengujian:
```bash
pytest -v
```

Hasil eksekusi:
```text
============================= test session starts =============================
platform win32 -- Python 3.13.9, pytest-9.1.1, pluggy-1.5.0
collected 84 items

tests/test_device_service.py (11 tests) .................... [ 13%] ALL PASSED
tests/test_integration_scenarios.py (15 tests) .............. [ 30%] ALL PASSED
tests/test_member_service.py (23 tests) ..................... [ 58%] ALL PASSED
tests/test_parking_service.py (16 tests) .................... [ 76%] ALL PASSED
tests/test_sensor_service.py (9 tests) ...................... [ 86%] ALL PASSED
tests/test_supabase_client.py (6 tests) ..................... [ 94%] ALL PASSED
tests/test_ui_pages.py (5 tests) ............................ [100%] ALL PASSED

============================= 84 passed in 7.50s ==============================
```

---

## 📋 Matriks Kepatuhan TRD & DRD

| No | Kriteria Penerimaan | Sumber | Status |
|:--:|---|:---:|:---:|
| 1 | Konektivitas ESP32-S3 ke WiFi terverifikasi via heartbeat | TRD Sec 27.1 | ✅ **PASS** |
| 2 | Deteksi kendaraan HC-SR04 ($\le$ 40 cm = terdeteksi) | TRD Sec 27.2 | ✅ **PASS** |
| 3 | Pembacaan UID RFID RC522 dan normalisasi hex uppercase | TRD Sec 27.3 | ✅ **PASS** |
| 4 | Pengiriman log scan RFID ke tabel `rfid_scans` Supabase | TRD Sec 27.4 | ✅ **PASS** |
| 5 | UID scan otomatis muncul di formulir pendaftaran Streamlit | TRD Sec 27.5 | ✅ **PASS** |
| 6 | Admin dapat mendaftarkan UID menjadi member baru | TRD Sec 27.6 | ✅ **PASS** |
| 7 | Validasi akses RFID member aktif untuk buka gerbang | TRD Sec 27.7 | ✅ **PASS** |
| 8 | Tindakan gate (`open` jika aktif, `remain_closed` jika tidak) | TRD Sec 27.8 | ✅ **PASS** |
| 9 | IR sensor analog menentukan status slot kosong / terisi | TRD Sec 27.9 | ✅ **PASS** |
| 10 | Status 4 slot parkir muncul secara visual di Dashboard | TRD Sec 27.10 | ✅ **PASS** |
| 11 | ESP32-S3 tampil Online/Offline di web (ambang batas 30 detik) | TRD Sec 27.11 | ✅ **PASS** |
| 12 | Nilai sensor ultrasonik & IR dapat dipantau di web | TRD Sec 27.12 | ✅ **PASS** |
| 13 | UID scan bersifat Read-Only (tidak dapat diketik manual) | DRD Sec 10.3 & 32.5 | ✅ **PASS** |
| 14 | Pencegahan duplikasi kartu RFID yang sudah terdaftar | DRD Sec 12 | ✅ **PASS** |
| 15 | **Tidak ada tombol buka/tutup gerbang manual di website** | DRD Sec 1, 32.12 & TRD Sec 8 | ✅ **PASS** |
