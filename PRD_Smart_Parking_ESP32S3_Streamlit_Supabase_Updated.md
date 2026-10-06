# PRD — Smart Parking Monitoring & RFID Member System (Enhanced Version)

## 1. Product Name

**Smart Parking Monitoring & RFID Member System**

Sistem ini merupakan sistem smart parking berbasis IoT dan cloud tingkat lanjut yang mengintegrasikan **ESP32-S3 (Unified Node), RFID RC522, sensor ultrasonic HC-SR04, sensor IR Active-LOW, Servo Gate, LCD 16x2 I2C, Buzzer, Streamlit Web Application dengan Realtime Fragments, Anti-Passback Enforcement, Log Audit Forensik, dan Supabase Cloud Database**.

Sistem dirancang modular, tangguh, dan mendukung kolaborasi multi-peran:
- **ESP32-S3 (Unified Master Controller)**: Menangani deteksi kendaraan di gerbang (ultrasonic), kontrol palang gerbang (servo), pemindaian RFID (RC522), monitoring 3 slot parkir fisik (IR Slot 1, 2, 3), notifikasi audio visual (buzzer & LCD 16x2), proteksi anti-passback fisik, deteksi mobil membuntuti (tailgating), serta sinkronisasi dua arah ke Cloud via FreeRTOS.
- **Supabase Cloud (PostgreSQL & REST API)**: Pusat penyimpanan data terpusat (Member RFID dengan flag `inside_parking`, Log Scan, Status Slot Parkir, Perangkat IoT, Telemetri Sensor, Log Audit Forensik Kendaraan `audit_forensic_logs`, dan Autentikasi Pengguna).
- **Streamlit Web Application**: Dashboard monitoring real-time berbasis **Partial Component Fragments (`@st.fragment`)** tanpa kedip/reload satu halaman penuh, manajemen member RFID tersinkronisasi 2 arah, kartu perangkat siswa interaktif, workspace mandiri siswa, log forensik berserta snapshot visual kendaraan (SVG HUD), dan manajemen pengguna multi-role.

---

# 2. Latar Belakang & Permasalahan

Pada sistem parkir konvensional dan implementasi laboratorium IoT:
1. **Pengalaman Pengguna Web Terganggu Rerun Penuh (Full Page Flicker)**:
   - Polling tradisional berbasis refresh halaman menyeluruh (`st_autorefresh` atau meta-refresh) mereset posisi scroll, menghilangkan input form yang sedang diketik, dan menyebabkan kedipan layar konstan.
2. **Kelemahan Keamanan Kartu Berbagi (Passback Vulnerability)**:
   - Satu kartu RFID member yang valid dapat dioper keluar pagar dan di-tap berulang kali untuk memasukkan beberapa kendaraan yang tidak berhak.
3. **Ketiadaan Bukti Audit dan Deteksi Pelanggaran (Tailgating)**:
   - Tidak adanya rekaman forensik snapshot kendaraan saat gerbang terbuka dan tidak terdeteksinya mobil yang menyelinap membuntuti di belakang kendaraan yang sah sebelum palang tertutup.
4. **Pemisahan Perangkat Lapangan dan Web**:
   - Pendaftaran member baru sering kali terpisah dari perangkat fisik di lapangan sehingga memicu kesalahan ketik UID kartu.
5. **Kebutuhan Workspace Multi-Siswa**:
   - Di lingkungan pendidikan, siswa memerlukan akses mandiri ke node IoT mereka tanpa mencampuri kendali gerbang utama.

Smart Parking Monitoring & RFID Member System memecahkan permasalahan ini dengan arsitektur **Unified Edge + Selective Realtime Fragments + Anti-Passback + Forensic Audit**.

---

# 3. Tujuan Produk

1. **Monitoring Real-Time Slot Parkir Tanpa Kedipan Halaman (Targeted Realtime Fragments)**:
   - Memperbarui metrik KPI, peta 3 slot parkir (`P01`, `P02`, `P03`), telemetri sensor, dan log pemindaian secara parsial melalui WebSocket Streamlit (`@st.fragment(run_every="3s")`), mempertahankan posisi formulir dan input teks tanpa kehilangan fokus.
2. **Penegakan Aturan Anti-Passback (Anti-Passback Enforcement)**:
   - Mencegah kartu RFID yang sama di-tap dua kali berturut-turut pada gerbang masuk dengan melacak flag `inside_parking (boolean)`.
   - Menolak akses (`anti_passback_violation`) dan memicu peringatan audio-visual lokal pada LCD (`ANTI-PASSBACK!`) dan buzzer jika terdeteksi pelanggaran.
3. **Audit Forensik Kendaraan & Deteksi Mobil Membuntuti (Tailgating)**:
   - Mencatat setiap transaksi masuk, keluar, dan pelanggaran ke tabel `audit_forensic_logs` lengkap dengan snapshot HUD kendaraan (vektor SVG resolusi tinggi).
   - Mendeteksi anomali sensor jarak saat kendaraan kedua melintas rapat tanpa otorisasi kartu (Tailgating Alarm).
4. **Pendaftaran Member RFID Sinkron Dua Arah (2-Way Command Sync)**:
   - Mode registrasi (`status = 'registering'`) dari web mengunci palang gerbang agar tetap tertutup dan langsung menampilkan perintah tempel kartu di LCD 16x2.
   - UID kartu langsung ditransmisikan ke web dan mengisi form pendaftaran otomatis.
5. **Navigasi Kartu Perangkat Siswa di Monitoring Parkir**:
   - Admin disediakan kartu interaktif untuk setiap perangkat siswa aktif/terdaftar dengan 1-klik menuju Dashboard Siswa.
6. **Workspace Mandiri Siswa (Student Workspace)**:
   - Siswa mengelola slot mandiri, memantau telemetri, menyalin kredensial unik (`sk_dev_...`), dan menguji via simulator anti-passback.
7. **Pencegahan Kontrol Gerbang Manual di Web**:
   - Integritas operasional fisik dijaga dengan tidak menyediakan tombol buka/tutup palang manual di seluruh halaman website.
8. **Kunci Kesiapan Sistem & Dormansi Total Sensor (Full Sensor Dormancy Before Ready)**:
   - Mikrokomputer ESP32 secara mutlak **TIDAK MEMULAI APAPUN** selama proses boot atau ketika WiFi belum terhubung secara stabil. Seluruh sensor (Ultrasonic HC-SR04, 3 sensor IR slot parkir, dan RFID reader RC522) serta servo gerbang berada dalam status dorman tanpa pembacaan atau transmisi telemetri sama sekali.

---

# 4. Scope Produk

## 4.1 Dalam Scope (Aktif & Terimplementasi)
- **Arsitektur Realtime Partial Component Fragment (`utils.ui_helpers.realtime_fragment`)**:
  - Pembaruan latar belakang per komponen (3s/5s) tanpa full page rerun.
  - Form input, tab, expander, dan state UI tetap stabil saat data cloud disinkronkan.
- **Anti-Passback Algorithm & State Management**:
  - Kolom `inside_parking` pada tabel `parking_members`.
  - Validasi ketat saat masuk (`inside_parking == False` diizinkan $\rightarrow$ diubah ke `True`).
  - Validasi saat keluar (`inside_parking == True` diizinkan $\rightarrow$ diubah ke `False`).
  - Fitur reset darurat status passback oleh Administrator.
- **Audit Forensik & Snapshot HUD Vektor SVG**:
  - Penyimpanan log kejadian ke `audit_forensic_logs`.
  - Generator visualisasi snapshot kendaraan (SVG HUD) menampilkan plat nomor, timestamp, sensor jarak, dan status izin gerbang.
  - Deteksi dan peringatan insiden mobil membuntuti (tailgating).
- **Monitoring Parkir Global & Filter Perangkat**:
  - Ringkasan metrik (Total Slot, Kosong, Terisi).
  - Peta slot parkir adaptif dengan logika Active-LOW IR (`0 = Terisi`, `1 = Kosong`).
  - Kartu interaktif perangkat siswa aktif dengan tombol akses langsung ke Dashboard Siswa.
- **Sinkronisasi Registrasi Member RFID**:
  - Tombol perintah registrasi (`cmd registration`) ke alat.
  - Pembacaan otomatis UID RFID tanpa ketik manual.
  - CRUD Member RFID lengkap.
- **Workspace Dashboard Siswa**:
  - Tab 1: 🅿️ Slot Parkir Siswa (status slot, nilai IR, tautan slot 1-klik).
  - Tab 2: 💳 Pendaftaran Member RFID (live 2-way sync dengan ESP32).
  - Tab 3: 📊 Telemetri Sensor (Ultrasonic HC-SR04 & IR).
  - Tab 4: 🔑 Kredensial IoT (Device ID, API Key unik `sk_dev_...`, endpoint REST, template firmware C++).
  - Tab 5: 🧪 Simulator Uji Coba Web (termasuk simulator Anti-Passback & Tailgating).
- **Firmware ESP32-S3 Terpadu (FreeRTOS)**:
  - Multi-tasking (Gate, Slot IR, Ultrasonic, RFID, LCD 16x2, Network Cloud Sync, Buzzer).
  - Penanganan alert anti-passback dan deteksi tailgating pada TaskGate.

## 4.2 Di Luar Scope (Future Roadmap)
- Kontrol buka/tutup palang gerbang secara manual dari tombol website (dilarang demi keselamatan fisik).
- Pembayaran tarif parkir terintegrasi (QRIS, Payment Gateway).
- Pengenalan plat nomor berbasis AI kamera (ALPR hardware eksternal).
- Aplikasi mobile native (iOS / Android).

---

# 5. User Persona & Hak Akses

## 5.1 Admin
- Mengawasi kondisi seluruh slot parkir, status gerbang utama (`GATE-01`), dan log audit forensik.
- Menganalisis log insiden anti-passback dan alarm tailgating.
- Mereset status `inside_parking` jika terjadi disinkronisasi fisik di lapangan.
- Melihat daftar kartu perangkat siswa aktif di menu Monitoring Parkir dan menginspeksi Dashboard Siswa.
- Mengirim perintah registrasi RFID ke ESP32 dan mendaftarkan member baru.
- Mengelola akun pengguna (Admin/Siswa) dan menautkan perangkat pada halaman Manajemen User.

## 5.2 Siswa (Student)
- Login dengan akun siswa mandiri.
- Mendaftarkan perangkat ESP32 mandiri untuk mendapatkan `Device ID` dan `API Key` (`sk_dev_...`).
- Memonitor telemetri sensor, status 3 slot parkir, dan log scan kartu pada Dashboard Siswa secara real-time tanpa gangguan reload.
- Mengaktifkan mode registrasi pada board ESP32 untuk mendaftarkan kartu member RFID.
- Menguji skenario masuk, keluar, anti-passback, dan insiden tailgating via simulator web.

---

# 6. Tech Stack & Komponen

| Komponen | Teknologi / Spesifikasi |
|---|---|
| **Web Frontend** | Streamlit (Python 3.12/3.13) dengan `@st.fragment` Targeted Delta Update |
| **Styling & Komponen** | Custom Modern CSS, Status Badges, System Loading Animation |
| **Backend & Database** | Supabase (PostgreSQL 15+, PostgREST, RLS Configured) |
| **Audit & Visualisasi** | Embedded High-Resolution SVG HUD Generator (`services/audit_service.py`) |
| **Koneksi Jaringan** | `httpx` dengan `HTTPTransport(retries=3)` & mitigasi `[WinError 10035]` |
| **Microcontroller** | ESP32-S3 (Dual Core Tensilica Xtensa 32-bit LX7, 240MHz) |
| **RTOS Firmware** | FreeRTOS (Core 0: Network & Buzzer; Core 1: Sensor, Gate, RFID, LCD) |
| **RFID Reader** | MFRC522 (13.56 MHz RFID / SPI) |
| **Sensor Jarak** | HC-SR04 Ultrasonic (Trigger: GPIO 25, Echo: GPIO 26) |
| **Sensor Slot Parkir** | 3x Digital IR Obstacle Sensor (Active-LOW: 0=Terisi, 1=Kosong) |
| **Aktuator Gerbang** | Servo Motor SG90/MG995 (PWM GPIO 4) |
| **Display Lokal** | LCD 16x2 I2C (PCF8574, SDA GPIO 16, SCL GPIO 17, Addr 0x27) |
| **Indikator Audio** | Active/Passive Buzzer (GPIO 27) |
| **Protokol Cloud** | WiFi 2.4GHz STA Mode + HTTPS REST API (JSON Payload) |

---

# 7. Arsitektur Produk & Alur Data

```text
 ┌─────────────────────────────────────────────────────────────┐
 │                     PENGGUNA / USER                         │
 │           Admin                            Siswa            │
 └─────────────┬────────────────────────────────┬──────────────┘
               │                                │
               ▼                                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                STREAMLIT WEB APPLICATION                    │
 │                                                             │
 │  • Dashboard Utama (Realtime Fragment: Ringkasan, Mirror)   │
 │  • Monitoring Parkir (Fragment: Peta 3 Slot & Kartu Siswa)  │
 │  • Member RFID (Anti-Passback Flag & Audit Forensik Log)    │
 │  • IoT Devices (Fragment: Status Online & Key Gen)          │
 │  • Monitoring Sensor (Fragment: Ultrasonic & IR Telemetri)  │
 │  • Dashboard Siswa (Fragment: Slot, Tap Terkini, Telemetri) │
 │  • Manajemen User (Multi-Role, Device Binding, User CRUD)   │
 └─────────────────────────────┬───────────────────────────────┘
                               │ HTTPS (REST API)
                               ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                   SUPABASE CLOUD BACKEND                    │
 │                                                             │
 │  • app_users             • iot_devices                      │
 │  • parking_slots         • parking_members (inside_parking) │
 │  • rfid_scans            • sensor_data                      │
 │  • audit_forensic_logs   (Snapshots, Tailgating, Violations)│
 └─────────────────────────────▲───────────────────────────────┘
                               │ HTTPS / WiFi (2-Way REST Sync)
                               │ (Upsert on conflict & Command Poll)
 ┌─────────────────────────────┴───────────────────────────────┐
 │               ESP32-S3 UNIFIED CONTROLLER                   │
 │                                                             │
 │  [Core 0] TaskNetwork (WiFi, Sync Slots, Command Poll, HB)  │
 │           TaskBuzzer  (Asynchronous Sound Queue)           │
 │                                                             │
 │  [Core 1] TaskUltrasonic (HC-SR04 Gate Detection <= 20cm)   │
 │           TaskSlotIR     (Active-LOW IR 3 Slots: S1,S2,S3)  │
 │           TaskGate       (Servo 0°-90°, Tailgate Monitor)   │
 │           TaskRFID       (RC522: Anti-Passback Check)       │
 │           TaskLCD        (Anti-flicker 16x2 State Display)  │
 └─────────────────────────────────────────────────────────────┘
```

---

# 8. Alur Anti-Passback & Audit Forensik

```text
1. Mobil tiba di gerbang masuk (Ultrasonic <= 20cm)
2. Kartu RFID di-tap pada RC522:
   a. Jika kartu belum terdaftar -> Ditolak (unregistered), palang tertutup, log audit tercatat.
   b. Jika kartu berstatus INACTIVE -> Ditolak (inactive), palang tertutup, log audit tercatat.
   c. Jika kartu berstatus inside_parking == TRUE (Pelanggaran Anti-Passback):
      - Akses DITOLAK
      - LCD menampilkan: "*ANTI-PASSBACK!* KARTU DITOLAK"
      - Buzzer membunyikan double warning beep
      - Sistem mencatat log audit ke 'audit_forensic_logs' dengan snapshot HUD bertuliskan 'ANTI-PASSBACK VIOLATION'
      - Palang gerbang TETAP TERTUTUP
   d. Jika kartu VALID dan inside_parking == FALSE:
      - Akses DITERIMA
      - inside_parking diubah menjadi TRUE
      - Sistem mencatat snapshot HUD kendaraan masuk ke 'audit_forensic_logs'
      - Palang gerbang terbuka (Servo 90°)
3. Saat mobil melintas melewati palang:
   - Jika jarak sensor mendeteksi mobil kedua yang membuntuti rapat (Tailgating):
     * TaskGate memicu Alarm Tailgating
     * LCD menampilkan "TAILGATING DETECTED!"
     * Sistem membunyikan sirene buzzer dan mencatat event tailgating ke audit log.
4. Saat mobil keluar (Tap Keluar):
   - inside_parking direset menjadi FALSE
   - Snapshot audit keluar dicatat.
```

---

---

# 10. Fitur Manajemen Data Menyeluruh (Comprehensive CRUD: Create, Read, Update, Delete)

Untuk menjamin fleksibilitas operasional, perawatan basis data jangka panjang, dan siklus pembelajaran mandiri, sistem dilengkapi kapabilitas pengelolaan data (CRUD) penuh pada seluruh entitas:

1. **Member & Kartu RFID (`parking_members`)**:
   - **Create**: Pendaftaran member baru via auto-fill scan kartu fisik ESP32 atau input form web.
   - **Read**: Tampilan tabel interaktif, pencarian multi-kolom (Nama, Plat Nomor, UID), dan status Anti-Passback.
   - **Update**: Pengeditan nama lengkap, nomor plat kendaraan, tipe kendaraan (mobil/motor), status keanggotaan (aktif/nonaktif), dan penyesuaian darurat flag `inside_parking`.
   - **Delete**: Penghapusan kartu member secara permanen dari basis data dengan kotak centang konfirmasi keamanan ganda.

2. **Slot Parkir Sistem (`parking_slots`)**:
   - **Create**: Penambahan slot parkir baru dengan kode slot unik (misal: P05) dan penautan perangkat.
   - **Read**: Peta kondisi visual real-time Active-LOW (Kosong/Terisi/Offline).
   - **Update**: Perubahan kode slot, penyesuaian manual status parkir (available/occupied/offline), dan pengikatan/pelepasan ID perangkat IoT.
   - **Delete**: Penghapusan slot parkir secara permanen dari sistem dengan dialog konfirmasi.

3. **Perangkat IoT (`iot_devices`)**:
   - **Create**: Pendaftaran board ESP32 siswa mandiri atau node gerbang, penerbitan `device_id` dan `api_key` khusus.
   - **Read**: Kartu status online/offline (heartbeat threshold 30s), telemetri sensor, dan waktu aktif.
   - **Update**: Perubahan nama perangkat, nama pemilik/siswa, dan kategori perangkat (multi-sensor, gate, parking-slot).
   - **Delete**: Penghapusan perangkat IoT secara permanen melalui tab inspektur maupun panel kontrol diagnostik.

4. **Pengguna Aplikasi & Hak Akses RBAC (`app_users`)**:
   - **Create**: Pembuatan akun baru (Administrator / Siswa) dengan enkripsi password bcrypt.
   - **Read**: Daftar akun pengguna, peran aktif, dan perangkat yang diasosiasikan.
   - **Update**: Perubahan nama lengkap pengguna, pengubahan peran (Role), dan penugasan perangkat IoT terkait (`update_user_profile`).
   - **Delete**: Penghapusan akun pengguna secara permanen dengan proteksi anti-self-deletion bagi admin aktif.

5. **Telemetri Sensor (`sensor_data`)**:
   - **Read**: Visualisasi riwayat pembacaan sensor jarak ultrasonik dan sensor inframerah.
   - **Delete (Single)**: Penghapusan baris data bacaan sensor individual berdasarkan ID.
   - **Delete (Bulk / Purge)**: Pembersihan masal seluruh riwayat telemetri sensor yang dikirim oleh perangkat tertentu.

6. **Riwayat Scan RFID (`rfid_scans`)**:
   - **Read**: Log riwayat kartu RFID yang di-tap pada reader fisik perangkat.
   - **Delete (Single)**: Penghapusan catatan pembacaan kartu individual.
   - **Delete (Bulk / Purge)**: Pengosongan seluruh log scan kartu RFID untuk perangkat tertentu.

7. **Log Audit Forensik (`audit_forensic_logs`)**:
   - **Read**: Feed audit visual beresolusi tinggi dengan SVG HUD, metadata pelanggaran passback, dan deteksi tailgating.
   - **Delete (Single)**: Penghapusan rekaman insiden spesifik berdasarkan ID log audit.
   - **Delete (Bulk / Purge)**: Pengosongan seluruh riwayat log audit forensik keamanan gerbang oleh Administrator.

---

# 11. Acceptance Criteria (Definisi Selesai)

Sistem memenuhi kriteria keberhasilan penuh jika:
1. **Realtime Fragment UX Tanpa Kedip**: Seluruh pembacaan dinamis (metrik slot, mirror LCD, telemetri ultrasonik, dan kartu tap RFID) terupdate berkala tanpa me-reload seluruh halaman browser, tanpa kedipan layar, dan tanpa menghilangkan input pada form isian.
2. **Penegakan Anti-Passback 100%**: Kartu yang telah berada di dalam area parkir (`inside_parking = True`) ditolak saat mencoba masuk kembali sebelum melakukan transaksi keluar.
3. **Pencatatan Audit Forensik & Snapshot Kendaraan**: Setiap event otorisasi gerbang, penolakan anti-passback, dan alarm tailgating tersimpan di `audit_forensic_logs` lengkap dengan snapshot grafis HUD kendaraan (SVG) dan metadata terperinci.
4. **Koneksi WiFi & Kesiapan Sistem**: Saat booting dan WiFi belum tersambung, LCD menampilkan animasi loading dan RFID dikunci sementara; setelah terhubung, buzzer berbunyi dan sistem siap melayani. Seluruh sensor berada dalam status dorman total sebelum sistem siap.
5. **Peta Slot 3 Posisi Akurat**: Sensor IR Active-LOW membaca `0 = Terisi (Merah)` dan `1 = Kosong (Hijau)` untuk slot `P01`, `P02`, `P03`.
6. **Sinkronisasi Cloud Bebas HTTP 409**: Endpoint batch update slot dan heartbeat menggunakan header upsert dengan parameter `?on_conflict=slot_code` dan `?on_conflict=device_id`.
7. **Kartu Siswa di Monitoring Parkir**: Admin dapat melihat kartu perangkat siswa aktif dan langsung menuju Dashboard Siswa dengan 1 klik.
8. **Pendaftaran Member 2-Way Sync**: Perintah registrasi dari web berhasil mengubah mode LCD ESP32, merekam kartu tanpa membuka palang, dan mengisi UID ke form otomatis.
9. **Manajemen CRUD Lengkap Seluruh Entitas**: Seluruh data sistem (member, slot parkir, perangkat IoT, user RBAC, telemetri sensor, log scan RFID, dan log audit forensik) memiliki kontrol Create, Read, Update, dan Delete yang aman dengan konfirmasi.
10. **Integritas Keamanan Absolut**: Tidak terdapat tombol buka/tutup palang manual di seluruh halaman website.
11. **Kestabilan Pengujian**: Seluruh unit test suite lulus 100% (130 unit test lulus tanpa kegagalan).
