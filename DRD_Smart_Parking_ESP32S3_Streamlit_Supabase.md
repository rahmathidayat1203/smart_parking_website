# DRD — Smart Parking Monitoring & RFID Member System (Enhanced Version)

## 1. Document Purpose

Dokumen **Design Requirements Document (DRD)** ini merinci panduan desain antarmuka (UI), arsitektur informasi, alur pengalaman pengguna (UX), sistem komponen visual berbasis **Selective Realtime Fragments (`@st.fragment`)**, komponen penegakan **Anti-Passback**, dan visualisasi **Audit Forensik Kendaraan** untuk aplikasi web **Smart Parking Monitoring & RFID Member System**.

Aplikasi dirancang responsif, modern, bebas kedipan (zero-flicker), dan mendukung kolaborasi multi-role (**Administrator** dan **Siswa**).

> [!IMPORTANT]
> **Prinsip Keamanan Absolut**: Seluruh halaman website **TIDAK MENYEDIAKAN** tombol kontrol buka/tutup palang gerbang secara manual. Palang gerbang hanya dapat beroperasi melalui otorisasi otomatis di controller ESP32-S3.

---

# 2. Design Principles & Color Tokens

## 2.1 Design Principles
1. **Flicker-Free Realtime Experience (Fragment-Based UX)**:
   - Pembaruan nilai dinamis (ketersediaan slot, telemetri sensor, tap RFID terakhir, dan audit log) diperbarui di latar belakang tanpa me-reload satu halaman penuh. Pengguna tidak mengalami kedipan layar, lompatan posisi scroll, maupun hilangnya teks yang sedang diketik pada formulir.
2. **Glanceable Forensic Awareness**:
   - Status keamanan gerbang, termasuk deteksi pelanggaran anti-passback dan mobil membuntuti (tailgating), langsung terlihat melalui kartu visual HUD berskala resolusi tinggi.
3. **Physical-Digital Synchronized Feedback**:
   - Interaksi pendaftaran kartu di web secara instan mengubah status LCD 16x2 dan melodi buzzer perangkat fisik.
4. **Role-Tailored Workspaces**:
   - Administrator memiliki akses pemantauan global, log audit forensik lengkap, dan manajemen pengguna; Siswa memiliki ruang kerja terisolasi (slot mandiri, telemetri, kredensial unik, dan simulator).

## 2.2 Semantic Color Tokens

```text
┌─────────────────┬───────────┬──────────────────────────────────────────────┐
│ Semantic Role   │ Color Hex │ Penggunaan dalam Antarmuka                   │
├─────────────────┼───────────┼──────────────────────────────────────────────┤
│ Success / Free  │ #10B981   │ Slot Tersedia (Hijau), Device Online         │
│ Danger / Busy   │ #EF4444   │ Slot Terisi (Merah), Device Offline, Error   │
│ Warning / Alert │ #F59E0B   │ Mode Registrasi RFID, Mobil Terdeteksi <=20cm│
│ Forensic Purple │ #8B5CF6   │ Reticle HUD Audit, Kamera Forensik Gerbang   │
│ Security Indigo │ #4F46E5   │ Status Anti-Passback, Badge Keamanan         │
│ Info / Brand    │ #3B82F6   │ Primary Action, Status Siap, Navigasi Tab    │
│ Dark Neutral    │ #1F2937   │ Background Kartu Metrik, Kontainer Slot      │
│ Light Neutral   │ #F3F4F6   │ Surface Background, Border Divider           │
└─────────────────┴───────────┴──────────────────────────────────────────────┘
```

---

# 3. Information Architecture & Navigation

## 3.1 Role-Based Navigation Hierarchy

```text
SMART PARKING PORTAL
│
├── 🛡️ ADMINISTRATOR VIEW
│   ├── 🏠 Dashboard (Realtime Fragment: Ringkasan, Mirror LCD, Log Forensik)
│   ├── 🅿️ Monitoring Parkir (Fragment: Peta 3 Slot & Kartu Perangkat Siswa)
│   ├── 💳 Member RFID (Fragment: 2-Way Reg, Anti-Passback Status, Audit Logs)
│   ├── 📱 IoT Device (Fragment: Status Online, Kunci API `sk_dev_...`)
│   ├── 📊 Monitoring Sensor (Fragment: Gauge Ultrasonic & Telemetri IR)
│   ├── 🎓 Dashboard Siswa (Mode Inspeksi Administrator)
│   └── 👥 Manajemen User (Multi-Role User CRUD & Device Binding)
│
└── 🎓 SISWA (STUDENT) VIEW
    ├── 🏠 Dashboard (Ringkasan Status Global)
    ├── 🎓 Dashboard Siswa (Ruang Kerja Mandiri: Slot, Reg RFID, C++, Sim)
    └── 📊 Monitoring Sensor (Grafik Telemetri Jarak & Status Slot)
```

---

# 4. User Experience: Selective Realtime Fragments vs Legacy Refresh

| Karakteristik | Legacy Polling (`st_autorefresh`) | Selective Realtime Fragment (`@st.fragment`) |
|---|---|---|
| **Cakupan Update** | Seluruh halaman di-re-render dari atas ke bawah | Hanya blok komponen target yang didekorasi |
| **Dampak Visual** | White flicker / berkedip setiap 3 detik | 100% Mulus, tanpa kedip (Smooth In-Place Delta) |
| **Posisi Scroll** | Kerap meloncat ke bagian atas halaman | Posisi scroll pengguna tetap stabil dan terkunci |
| **Input Form** | Teks yang sedang diketik terhapus / kehilangan fokus | Input teks, dropdown, dan form tetap fokus & utuh |
| **Koneksi Jaringan** | Re-render DOM masif | Pertukaran paket JSON patch delta via WebSocket |

---

# 5. Detail Desain Komponen Halaman

## 5.1 Monitoring Parkir (`pages/1_Monitoring_Parkir.py`)
- **Peta Slot Real-Time**: Dibungkus dalam `@realtime_fragment(run_every="3s")`. Menampilkan kartu slot `P01`, `P02`, `P03` berwarna hijau/merah dengan nilai raw sensor IR (`LOW=Terisi`, `HIGH=Bebas`).
- **Kartu Perangkat Siswa Aktif**: Grid kartu interaktif untuk setiap board siswa yang terhubung dengan tombol "Buka Dashboard Siswa" untuk inspeksi langsung.

## 5.2 Member RFID & Audit Forensik (`pages/2_Member_RFID.py`)
- **Penegakan Anti-Passback**:
  - Kolom status lokasi kendaraan pada tabel member:
    - `🚗 SEDANG DI DALAM` (badge biru tua) jika `inside_parking == True`.
    - `🟢 BERADA DI LUAR` (badge hijau muda) jika `inside_parking == False`.
  - Tombol pemulihan darurat: `[ 🔄 Reset Semua Status Anti-Passback ]` bagi Administrator jika terjadi disinkronisasi sensor lapangan.
- **Log Audit Forensik & Snapshot HUD**:
  - Galeri snapshot visual resolusi tinggi (SVG HUD) menampilkan siluet mobil, plat nomor, tanggal/jam mikrodetik, dan status izin (`ENTRY GRANTED`, `ANTI-PASSBACK VIOLATION`, `TAILGATING DETECTED`).
  - Indikator peringatan mobil membuntuti (Tailgating Alarm) dengan badge merah mencolok.

## 5.3 Dashboard Siswa (`pages/5_Dashboard_Siswa.py`)
- **Header Overview Card**: Menampilkan status online/offline dan timestamp heartbeat perangkat terpilih secara live via fragment 3s.
- **Tab 1: Slot Parkir Siswa**: Status slot parkir mandiri siswa diupdate setiap 3s.
- **Tab 2: Pendaftaran Member RFID**:
  - Kartu tap terakhir membaca UID instan tanpa tombol reload manual.
  - Form pendaftaran tetap berada di luar siklus reload sehingga siswa bebas mengetik tanpa interupsi.
- **Tab 3: Telemetri Sensor**: Nilai jarak HC-SR04 dan log IR terupdate berkala 3s.
- **Tab 5: Simulator Uji Coba Web**:
  - Tombol simulasi tap masuk, tap keluar, uji coba pelanggaran anti-passback, dan simulasi mobil membuntuti (tailgating) lengkap dengan tampilan snapshot HUD forensik instan.

## 5.4 IoT Device Inspector & Management (`pages/3_IoT_Device.py`)
- **Inspektur Detail Perangkat**: Tab 5 "⚙️ Edit & Hapus Perangkat" memungkinkan pengeditan nama, pemilik, dan tipe perangkat, serta penghapusan permanen dengan konfirmasi.
- **Panel Diagnostik & Manajemen**: Tab "✏️ Edit Device" dan "🗑️ Hapus Device" untuk mengelola semua perangkat IoT terdaftar secara terpusat.

## 5.5 Manajemen User & RBAC (`pages/6_Manajemen_User.py`)
- **Tab 1: ✏️ Edit Profil & Hak Akses**: Pengeditan nama lengkap, peran (Admin/Siswa), dan penugasan perangkat IoT secara simultan (`update_user_profile`).
- **Tab 2: 🔑 Reset Password**: Penggantian kata sandi dengan verifikasi minimal 6 karakter.
- **Tab 3: ➕ Tambah Akun Pengguna**: Pendaftaran langsung akun baru.
- **Tab 4: 🗑️ Hapus Pengguna**: Penghapusan akun pengguna permanen dengan kotak centang konfirmasi dan proteksi anti-self-deletion.

## 5.6 Pola Desain CRUD Aman (Safe CRUD Design Pattern)
1. **Isolasi Formulir di Luar Fragment Realtime**:
   - Seluruh formulir penambahan, pengeditan, dan penghapusan diletakkan di luar fragment periodic rerender atau di dalam `st.expander` stabil sehingga tidak pernah kehilangan fokus kursor saat pengguna mengetik.
2. **Proteksi Konfirmasi Ganda (Dual-Action Confirmation)**:
   - Setiap operasi penghapusan destruktif (delete) mewajibkan centang eksplisit pada `st.checkbox("Saya yakin...")` sebelum tombol submit diaktifkan.
3. **Umpan Balik Visual Instan**:
   - Menampilkan notifikasi banner `st.success` / `st.error` segera setelah mutasi basis data berhasil dijalankan.

---

# 6. Design Acceptance Criteria

Desain sistem dinyatakan memenuhi seluruh spesifikasi DRD apabila:
1. Pembaruan data real-time berlangsung **tanpa flicker halaman**, tanpa mengganggu proses pengetikan form dan tanpa mengubah posisi scroll pengguna.
2. Status Anti-Passback (`inside_parking`) tertera secara eksplisit dan intuitif pada antarmuka master member RFID.
3. Snapshot audit forensik kendaraan (SVG HUD) dirender secara tajam dan responsif di seluruh resolusi layar desktop maupun mobile.
4. Seluruh entitas data (Member, Slot Parkir, Device IoT, Akun Pengguna, Sensor, Scan RFID, dan Log Audit) memiliki antarmuka Create, Read, Update, dan Delete yang intuitif, aman, dan konsisten.
5. Seluruh antarmuka **TIDAK MEMILIKI** tombol kontrol buka/tutup palang gerbang secara manual.
6. Hak akses Administrator dan Siswa terisolasi secara sempurna pada menu navigasi.
