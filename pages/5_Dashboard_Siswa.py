"""
Smart Parking Monitoring & RFID Member System - Dashboard Siswa
Page: pages/5_Dashboard_Siswa.py

Dedicated workspace for students to monitor their individual ESP32-S3 IoT device,
inspect real-time sensor telemetries, review RFID scans, obtain connection credentials
(API Key & Connection URL), and simulate telemetry data.
"""

import os
from datetime import datetime, timezone
import streamlit as st
import pandas as pd

from utils.ui_helpers import (
    get_app_supabase,
    render_status_badge,
    render_sidebar_branding,
    setup_auto_refresh,
    realtime_fragment,
    format_timestamp,
    get_relative_time,
    require_auth,
    system_loading,
)
from services.device_service import (
    get_all_devices,
    is_device_online,
    update_device_heartbeat,
    get_student_device_telemetry,
    generate_esp32_code_snippet,
    register_student_device,
    set_device_registration_mode,
    get_device_registration_mode,
)
from services.auth_service import update_user_device
from services.sensor_service import (
    CAR_DETECTION_DISTANCE_CM,
    delete_sensor_reading,
    clear_sensor_data_by_device,
)
from services.parking_service import (
    get_parking_slots,
    calculate_slot_metrics,
    check_slot_offline,
    assign_slots_to_device,
)
from services.member_service import (
    register_member,
    is_uid_registered,
    get_all_members,
    normalize_rfid_uid,
    update_member,
    delete_member,
    delete_rfid_scan,
    clear_rfid_scans_by_device,
    get_latest_rfid_scan,
)
from services.audit_service import (
    process_gate_entry,
    process_gate_exit,
    report_tailgating,
)

# 1. Page Config
st.set_page_config(
    page_title="Smart Parking - Dashboard Siswa",
    page_icon="🎓",
    layout="wide",
)

# 2. Setup Auto-Refresh
setup_auto_refresh(interval_ms=4000, key="student_dash_autorefresh")

# 3. Retrieve Supabase Client
supabase = get_app_supabase()

# 4. Authentication Check (Accessible by Admin and Student)
user = require_auth(supabase, allowed_roles=["admin", "student"], current_page_name="5_Dashboard_Siswa.py")

# 5. Sidebar Branding
render_sidebar_branding(supabase=supabase)

# 6. Header
st.title("🎓 Dashboard Mandiri Siswa (IoT Device Workspace)")
st.caption("Pemantauan Telemetri Real-time & Manajemen Kredensial Perangkat Siswa")
st.markdown("---")

# 7. Device Registration Expander (Memungkinkan Siswa Mendaftarkan Device Sendiri)
with st.expander("➕ Daftarkan / Hubungkan Perangkat ESP32 Saya", expanded=(not bool(user.get("device_id")))):
    st.caption("Daftarkan board ESP32 Anda untuk mendapatkan Device ID dan API Key khusus perangkat Anda:")
    with st.form("student_device_registration_form"):
        r_col1, r_col2 = st.columns(2)
        with r_col1:
            dev_custom_name = st.text_input("Nama Perangkat:", value=f"ESP32 Smart Parking - {user.get('full_name', 'Siswa')}")
        with r_col2:
            dev_custom_id = st.text_input("Device ID (Opsional, kosongkan untuk otomatis):", placeholder="Contoh: DEV-SISWA-01").strip().upper()

        submit_reg = st.form_submit_button("🚀 Daftarkan Perangkat & Dapatkan API Key", use_container_width=True)
        if submit_reg:
            if not dev_custom_name:
                st.error("Nama perangkat tidak boleh kosong!")
            else:
                try:
                    with st.spinner("🚀 Mendaftarkan perangkat baru & membuat kunci API..."):
                        reg_dev = register_student_device(
                            supabase,
                            owner_name=user.get("full_name", "Siswa"),
                            device_name=dev_custom_name,
                            device_type="multi-sensor",
                            device_id=dev_custom_id if dev_custom_id else None
                        )
                        # Tautkan ke akun user siswa saat ini
                        u_name = user.get("username")
                        if u_name:
                            update_user_device(supabase, u_name, reg_dev.get("device_id"))
                            user["device_id"] = reg_dev.get("device_id")
                            if "logged_in_user" in st.session_state:
                                st.session_state["logged_in_user"]["device_id"] = reg_dev.get("device_id")
                        st.session_state["recent_registered_device"] = reg_dev
                        st.success(f"🎉 Perangkat **{reg_dev.get('device_id')}** berhasil didaftarkan dan ditautkan ke akun Anda!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Gagal mendaftarkan perangkat: {str(e)}")

# 8. Fetch All Devices
with system_loading(
    message="Memuat Dashboard Siswa...",
    subtext="Menyinkronkan data perangkat ESP32 & kredensial koneksi...",
    key="student_dash",
    only_initial=True,
):
    devices = get_all_devices(supabase)

# 8. Filter Device Sesuai Role (Isolasi Data Siswa)
is_student = (user.get("role") in ["student", "siswa"])
assigned_id = user.get("device_id")

if is_student:
    # Siswa HANYA boleh melihat perangkat miliknya sendiri (berdasarkan device_id yang terikat atau nama pemilik)
    if assigned_id:
        devices = [d for d in devices if d.get("device_id") == assigned_id]
    else:
        # Jika belum ada device_id terikat, cocokkan dengan nama pemilik
        full_name = user.get("full_name", "")
        devices = [d for d in devices if d.get("owner_name") == full_name]

if not devices:
    if is_student:
        st.warning("⚠️ **Belum Ada Perangkat yang Terhubung dengan Akun Anda.**")
        st.info("Silakan gunakan formulir **'➕ Daftarkan / Hubungkan Perangkat ESP32 Saya'** di atas untuk mendaftarkan modul ESP32 Anda.")
    else:
        st.info("💡 Belum ada perangkat IoT yang terdaftar di sistem.")
    st.stop()

# 9. Device Selector
def format_dev_label(d):
    owner = d.get("owner_name")
    dev_id = d.get("device_id", "-")
    name = d.get("device_name", "Device")
    if owner:
        return f"🎓 {dev_id} — {owner} ({name})"
    return f"📟 {dev_id} — {name}"

selected_idx = 0
target_dev_id = st.session_state.pop("target_student_device_id", None)
recent_dev = st.session_state.get("recent_registered_device")

if target_dev_id:
    for idx, d in enumerate(devices):
        if d.get("device_id") == target_dev_id:
            selected_idx = idx
            break
elif recent_dev:
    for idx, d in enumerate(devices):
        if d.get("device_id") == recent_dev.get("device_id"):
            selected_idx = idx
            break

# Tampilkan dropdown pemilihan hanya jika Admin atau memiliki lebih dari 1 perangkat
if not is_student or len(devices) > 1:
    col_sel1, col_sel2 = st.columns([3, 1])
    with col_sel1:
        selected_device = st.selectbox(
            "Pilih Perangkat Siswa:" if not is_student else "Pilih Perangkat Anda:",
            options=devices,
            index=selected_idx,
            format_func=format_dev_label,
            key="student_selected_device",
        )
    with col_sel2:
        st.write("")
        st.write("")
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()
else:
    # Siswa dengan 1 perangkat langsung terpilih secara otomatis tanpa dropdown perangkat lain
    selected_device = devices[0]

if not selected_device:
    st.stop()

dev_id = selected_device.get("device_id", "-")
dev_name = selected_device.get("device_name", "ESP32-S3 Node")
owner_name = selected_device.get("owner_name", "Umum / Laboratorium")
dev_type = selected_device.get("device_type", "multi-sensor")
api_key = selected_device.get("api_key", "sk_dev_default")
last_seen = selected_device.get("last_seen")
online = is_device_online(last_seen, threshold_seconds=30)

# Admin Inspection Mode Banner
if user.get("role") == "admin":
    adm_c1, adm_c2 = st.columns([3, 1])
    with adm_c1:
        st.info(f"👑 **Mode Inspeksi Admin**: Sedang membuka Dashboard Siswa untuk perangkat **{owner_name}** (`{dev_id}`). Anda dapat memantau slot parkir mereka dan mendaftarkan member RFID di bawah.")
    with adm_c2:
        st.write("")
        if st.button("⬅️ Kembali ke Monitoring Parkir", use_container_width=True):
            st.switch_page("pages/1_Monitoring_Parkir.py")

# 8. Device Overview Fragment
@realtime_fragment(run_every="5s")
def render_student_device_overview(device_id: str, default_name: str, owner_name: str, dev_type: str):
    devs = get_all_devices(supabase)
    curr_dev = next((d for d in devs if d.get("device_id") == device_id), {})
    l_seen = curr_dev.get("last_seen")
    d_name = curr_dev.get("device_name", default_name)
    is_on = is_device_online(l_seen, threshold_seconds=30)

    border_clr = "#10B981" if is_on else "#EF4444"
    bg_clr = "#F0FDF4" if is_on else "#FEF2F2"
    badge_html = render_status_badge("ONLINE" if is_on else "OFFLINE")
    rel_seen = get_relative_time(l_seen)
    fmt_seen = format_timestamp(l_seen)

    st.markdown(
        f"""
        <div style="border: 2px solid {border_clr}; background-color: {bg_clr}; border-radius: 12px; padding: 18px 24px; margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <div>
                    <span style="font-size: 0.8rem; font-weight: 700; color: #475569; letter-spacing: 0.05em; text-transform: uppercase;">PERANGKAT TERPILIH</span>
                    <div style="font-size: 1.5rem; font-weight: 800; color: #0F172A;">{d_name}</div>
                    <div style="font-size: 0.95rem; color: #334155; margin-top: 2px;">
                        <b>Pemilik:</b> {owner_name} &bull; <b>Device ID:</b> <code>{device_id}</code> &bull; <b>Tipe:</b> {dev_type}
                    </div>
                </div>
                <div style="text-align: right; margin-top: 8px;">
                    <div style="margin-bottom: 6px;">{badge_html}</div>
                    <div style="font-size: 0.82rem; color: #475569;">Terakhir aktif: <b>{rel_seen}</b></div>
                    <div style="font-size: 0.75rem; color: #64748B;">({fmt_seen})</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

render_student_device_overview(dev_id, dev_name, owner_name, dev_type)

# 9. Workspace Tabs (Slot Parkir, Member RFID, Telemetri, Kredensial, Simulator)
tab_slots, tab_rfid_reg, tab_telemetry, tab_credentials, tab_sim = st.tabs([
    "🅿️ Slot Parkir Siswa",
    "💳 Pendaftaran Member RFID",
    "📊 Telemetri Sensor",
    "🔑 Kredensial & Kode C++",
    "🧪 Simulator Uji Coba",
])

# -------------------------------------------------------------
# TAB 1: Slot Parkir Siswa
# -------------------------------------------------------------
@realtime_fragment(run_every="4s")
def render_student_slots_content(device_id: str):
    devs = get_all_devices(supabase)
    curr_dev = next((d for d in devs if d.get("device_id") == device_id), {})
    online_stat = is_device_online(curr_dev.get("last_seen"), threshold_seconds=30)

    all_slots = get_parking_slots(supabase)
    dev_slots = [s for s in all_slots if s.get("device_id") == device_id]

    if dev_slots:
        m_dev = calculate_slot_metrics(dev_slots)
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Total Slot Perangkat", m_dev["total"])
        with c2:
            st.metric("Slot Kosong (Available)", m_dev["available"], delta=f"{m_dev['available']} Bebas", delta_color="normal")
        with c3:
            st.metric("Slot Terisi (Occupied)", m_dev["occupied"], delta=f"-{m_dev['occupied']} Terisi" if m_dev["occupied"] > 0 else "0", delta_color="inverse")

        st.markdown("---")
        st.write("##### Peta Slot Parkir Siswa:")
        slot_cols = st.columns(len(dev_slots) if len(dev_slots) <= 3 else 2)
        for s_idx, slot in enumerate(dev_slots):
            col_target = slot_cols[s_idx] if len(dev_slots) <= 3 else slot_cols[s_idx % 2]
            with col_target:
                s_code = slot.get("slot_code", f"Slot {s_idx+1}")
                s_raw = slot.get("sensor_value")
                s_up_raw = slot.get("updated_at")
                s_up_fmt = format_timestamp(s_up_raw)
                s_rel = get_relative_time(s_up_raw)

                is_off = check_slot_offline(slot) or not online_stat
                eff_status = "offline" if is_off else slot.get("status", "available")

                if eff_status == "available":
                    c_status = "KOSONG"
                    b_color = "#10B981"
                    bg_col = "#F0FDF4"
                    txt_col = "#047857"
                    icon = "🟢"
                elif eff_status == "occupied":
                    c_status = "TERISI"
                    b_color = "#EF4444"
                    bg_col = "#FEF2F2"
                    txt_col = "#B91C1C"
                    icon = "🔴"
                else:
                    c_status = "OFFLINE"
                    b_color = "#9CA3AF"
                    bg_col = "#F3F4F6"
                    txt_col = "#4B5563"
                    icon = "⚪"

                badge = render_status_badge(c_status)
                if s_raw is None:
                    raw_desc = "N/A"
                elif s_raw == 0:
                    raw_desc = "0 (LOW • Terhalang)"
                elif s_raw == 1:
                    raw_desc = "1 (HIGH • Bebas)"
                else:
                    raw_desc = f"{s_raw}"

                st.markdown(
                    f"""
                    <div style="border: 2px solid {b_color}; background-color: {bg_col};
                                border-radius: 12px; padding: 20px; margin-bottom: 16px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <span style="font-size: 1.4rem; font-weight: 800; color: #0F172A;">{icon} {s_code}</span>
                            <div>{badge}</div>
                        </div>
                        <div style="font-size: 0.95rem; margin-bottom: 4px;">
                            <b>Status:</b> <span style="color: {txt_col}; font-weight: 700;">{c_status}</span>
                        </div>
                        <div style="font-size: 0.95rem; margin-bottom: 4px;">
                            <b>Sensor IR:</b> <code>{raw_desc}</code>
                        </div>
                        <div style="font-size: 0.8rem; color: #64748B;">
                            Terakhir update: {s_up_fmt} ({s_rel})
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
    else:
        st.info(f"ℹ️ Belum ada slot parkir yang secara spesifik tercatat untuk Device ID **{device_id}**.")
        st.caption("Jika firmware ESP32 dijalankan dengan `DEVICE_ID = \"" + device_id + "\"`, maka 3 slot parkir (P01, P02, P03) akan otomatis disinkronkan ke sini.")

with tab_slots:
    st.subheader(f"Status Slot Parkir Perangkat: {dev_name} ({dev_id})")
    render_student_slots_content(dev_id)

    all_slots_check = get_parking_slots(supabase)
    dev_slots_check = [s for s in all_slots_check if s.get("device_id") == dev_id]
    if not dev_slots_check:
        bind_c1, bind_c2 = st.columns([2, 1])
        with bind_c1:
            st.write("Atau kaitkan 3 Slot master yang ada (P01, P02, P03) ke perangkat ini sekarang:")
        with bind_c2:
            if st.button(f"🔗 Kaitkan Slot P01-P03 ke {dev_id}", use_container_width=True, type="primary"):
                assign_slots_to_device(supabase, ["P01", "P02", "P03"], dev_id)
                st.success(f"Slot P01-P03 berhasil dikaitkan ke {dev_id}!")
                st.rerun()

        st.markdown("---")
        st.write("##### Semua Slot Parkir Sistem Saat Ini:")
        if all_slots_check:
            cols_preview = st.columns(len(all_slots_check) if len(all_slots_check) <= 4 else 3)
            for idx_p, sl_p in enumerate(all_slots_check):
                with cols_preview[idx_p % len(cols_preview)]:
                    st.write(f"**{sl_p.get('slot_code')}**: `{sl_p.get('status')}` (Device: `{sl_p.get('device_id') or '-'}`)")

# -------------------------------------------------------------
# TAB 2: Pendaftaran Member RFID
# -------------------------------------------------------------
@realtime_fragment(run_every="2s")
def render_student_rfid_sync_card(device_id: str):
    """Consolidated fragment: registration status + latest tap card in one fragment."""
    is_device_reg = get_device_registration_mode(supabase, device_id)
    if is_device_reg:
        st.warning(
            f"🟡 **Mode Registrasi SEDANG AKTIF pada Perangkat {device_id}!**\n\n"
            "Layar LCD alat sedang menampilkan `*REGISTRASI RFID* TEMPEL KARTU...` (Palang gerbang tidak akan membuka saat proses ini). "
            "Silakan tempelkan kartu RFID baru Anda pada reader RC522 alat sekarang."
        )
    else:
        st.info(
            f"ℹ️ **Mode Normal**: Klik tombol **'📡 Kirim Perintah Registrasi ke ESP32'** di samping agar layar alat beralih ke mode registrasi pendaftaran kartu."
        )

    # Fast direct query for newest scan on this specific device
    latest_scan_obj = get_latest_rfid_scan(supabase, device_id=device_id)
    latest_uid = latest_scan_obj.get("uid", "") if latest_scan_obj else ""
    latest_scan_time = latest_scan_obj.get("created_at") if latest_scan_obj else None

    if latest_uid:
        is_reg = is_uid_registered(supabase, latest_uid)
        reg_status_html = '<span style="color: #047857; font-weight: 700;">🟢 Belum Terdaftar (Siap Registrasi)</span>' if not is_reg else '<span style="color: #2563EB; font-weight: 700;">ℹ️ Sudah Terdaftar sebagai Member</span>'
        st.markdown(
            f"""
            <div style="border: 2px solid {'#10B981' if not is_reg else '#3B82F6'}; background: #F8FAFC; border-radius: 12px; padding: 16px; margin-bottom: 12px;">
                <div style="font-size: 0.8rem; font-weight: 700; color: #64748B;">TAP TERAKHIR PADA ESP32 ({device_id}):</div>
                <div style="font-size: 1.5rem; font-weight: 800; color: #0F172A; font-family: monospace;">{latest_uid}</div>
                <div style="font-size: 0.85rem; color: #475569;">Waktu: {format_timestamp(latest_scan_time)} ({get_relative_time(latest_scan_time)})</div>
                <div style="margin-top: 6px;">{reg_status_html}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if not is_reg:
            if st.button("⚡ Gunakan UID Ini di Form Pendaftaran", key=f"btn_use_uid_{device_id}", use_container_width=True):
                st.session_state["student_reg_rfid_uid"] = latest_uid
                set_device_registration_mode(supabase, device_id, enable=False)
                st.rerun()
    else:
        st.info(f"Belum ada pembacaan kartu RFID yang tercatat dari `{device_id}`. Silakan tap kartu fisik pada RFID RC522 ESP32 Anda.")

@realtime_fragment(run_every="6s")
def render_rfid_history_table(device_id: str):
    telemetry = get_student_device_telemetry(supabase, device_id)
    scans = telemetry.get("scans", [])
    if scans:
        st.write("##### 📜 Riwayat Scan Kartu pada Perangkat Ini:")
        df_scans = pd.DataFrame(scans)
        scan_display = df_scans[["uid", "created_at"]].copy()
        scan_display.columns = ["UID Kartu RFID", "Waktu Scan"]
        st.dataframe(scan_display, width="stretch", height=180)

@realtime_fragment(run_every="4s")
def render_student_telemetry_live(device_id: str):
    telemetry = get_student_device_telemetry(supabase, device_id)
    sensors = telemetry.get("sensors", [])
    latest_ultrasonic = telemetry.get("latest_ultrasonic")

    col_m1, col_m2, col_m3 = st.columns(3)

    with col_m1:
        if latest_ultrasonic is not None:
            dist_val = float(latest_ultrasonic)
            is_car = (dist_val > 0 and dist_val <= CAR_DETECTION_DISTANCE_CM)
            st.metric(
                label="Jarak Sensor Ultrasonik (HC-SR04)",
                value=f"{dist_val:.1f} cm" if dist_val >= 0 else "-- cm",
                delta="Mobil Terdeteksi (<= 20cm)" if is_car else "Tidak Ada Mobil",
                delta_color="normal" if is_car else "off",
            )
        else:
            st.metric(label="Jarak Ultrasonik (HC-SR04)", value="- cm", delta="Belum ada data")

    with col_m2:
        ir_readings = [s for s in sensors if s.get("sensor_type") == "ir"]
        if ir_readings:
            latest_ir = ir_readings[0].get("sensor_value")
            st.metric(label="Nilai ADC Sensor IR Terbaru", value=f"{latest_ir}")
        else:
            st.metric(label="Nilai ADC Sensor IR", value="-", delta="Belum ada data")

    with col_m3:
        st.metric(label="Total Log Telemetri Diterima", value=len(sensors))

    st.markdown("---")

    if sensors:
        st.write("##### Riwayat Pembacaan Sensor:")
        df_sensors = pd.DataFrame(sensors)
        display_df = df_sensors[["sensor_type", "sensor_value", "created_at"]].copy()
        display_df.columns = ["Jenis Sensor", "Nilai / Pembacaan", "Waktu Terima"]
        st.dataframe(display_df, width="stretch", height=260)
    else:
        st.info("Belum ada data sensor yang masuk dari perangkat ini. Silakan jalankan firmware ESP32 atau gunakan tab Simulator.")

with tab_rfid_reg:
    st.subheader(f"💳 Pendaftaran Member RFID Perangkat ({dev_id})")
    st.caption("Pindai kartu RFID pada modul RC522 perangkat ini untuk mendaftarkan member baru secara otomatis:")

    is_device_reg = get_device_registration_mode(supabase, dev_id)

    col_cmd_status, col_cmd_btn = st.columns([2, 1])
    with col_cmd_status:
        st.write(f"Perangkat Target: **{dev_name}** (`{dev_id}`)")
    with col_cmd_btn:
        if is_device_reg:
            if st.button("❌ Batalkan Mode Registrasi", key=f"btn_cancel_reg_{dev_id}", use_container_width=True):
                set_device_registration_mode(supabase, dev_id, enable=False)
                st.rerun()
        else:
            if st.button("📡 Kirim Perintah Registrasi ke ESP32", key=f"btn_start_reg_{dev_id}", type="primary", use_container_width=True):
                set_device_registration_mode(supabase, dev_id, enable=True)
                st.rerun()

    st.markdown("---")

    rfid_card_col1, rfid_card_col2 = st.columns([1, 1])
    with rfid_card_col1:
        render_student_rfid_sync_card(dev_id)

    with rfid_card_col2:
        # Use session_state only for form default UID to prevent recalculation disrupting typing
        form_default_uid = st.session_state.get("student_reg_rfid_uid", "")

        with st.form("form_register_member_student"):
            st.write("##### Form Pendaftaran Member")
            rfid_input = st.text_input("UID Kartu RFID:", value=form_default_uid, help="UID hasil tap kartu RFID pada ESP32").strip().upper()
            m_name = st.text_input("Nama Lengkap Member:", placeholder="Contoh: Andi Pratama").strip()
            m_plate = st.text_input("Nomor Plat Kendaraan:", placeholder="Contoh: B 1234 XYZ").strip().upper()
            m_type = st.selectbox("Jenis Kendaraan:", options=["car", "motorcycle"], format_func=lambda x: "Mobil" if x == "car" else "Sepeda Motor")
            
            sub_member = st.form_submit_button("💾 Daftarkan Member RFID", type="primary", use_container_width=True)
            if sub_member:
                if not rfid_input:
                    st.error("UID Kartu RFID tidak boleh kosong! Tap kartu pada ESP32 terlebih dahulu.")
                elif not m_name or not m_plate:
                    st.error("Nama lengkap dan nomor plat kendaraan wajib diisi!")
                else:
                    try:
                        with st.spinner("Menyimpan data member ke database..."):
                            reg_res = register_member(
                                supabase,
                                rfid_uid=rfid_input,
                                member_name=m_name,
                                license_plate=m_plate,
                                vehicle_type=m_type
                            )
                            set_device_registration_mode(supabase, dev_id, enable=False)
                            st.session_state.pop("student_reg_rfid_uid", None)
                            st.success(f"🎉 Member **{m_name}** ({m_plate}) dengan UID `{rfid_input}` berhasil didaftarkan!")
                            st.rerun()
                    except ValueError as ve:
                        st.error(f"Gagal: {str(ve)}")
                    except Exception as ex:
                        st.error(f"Terjadi kesalahan: {str(ex)}")

    st.markdown("---")
    render_rfid_history_table(dev_id)

    # Tabel Member RFID yang Terdaftar
    st.write("##### 📋 Daftar Seluruh Member RFID Terdaftar:")
    all_members = get_all_members(supabase)
    if all_members:
        df_mem = pd.DataFrame(all_members)
        disp_mem = df_mem[["rfid_uid", "member_name", "license_plate", "vehicle_type", "status", "created_at"]].copy()
        disp_mem.columns = ["UID Kartu", "Nama Member", "Plat Kendaraan", "Jenis", "Status", "Waktu Daftar"]
        st.dataframe(disp_mem, width="stretch", height=220)
    else:
        st.info("Belum ada member RFID yang terdaftar di database.")

    with st.expander("⚙️ Edit & Hapus Member RFID Terdaftar", expanded=False):
        if not all_members:
            st.info("Belum ada member RFID terdaftar.")
        else:
            col_m_ed1, col_m_ed2 = st.columns(2)
            with col_m_ed1:
                st.write("**✏️ Edit Data Member**")
                member_uid_map = {f"{m.get('member_name')} ({m.get('rfid_uid')})": m.get('rfid_uid') for m in all_members}
                sel_m_label = st.selectbox("Pilih Member yang Ingin Diedit:", options=list(member_uid_map.keys()), key="sel_m_edit")
                target_uid = member_uid_map[sel_m_label]
                curr_m = next((m for m in all_members if m.get("rfid_uid") == target_uid), {})

                with st.form(f"form_edit_m_{target_uid}"):
                    e_m_name = st.text_input("Nama Member:", value=curr_m.get("member_name", "")).strip()
                    e_m_plate = st.text_input("Nomor Plat Kendaraan:", value=curr_m.get("license_plate", "")).strip().upper()
                    curr_vtype = curr_m.get("vehicle_type", "car")
                    e_m_vtype = st.selectbox(
                        "Jenis Kendaraan:",
                        options=["car", "motorcycle"],
                        index=0 if curr_vtype == "car" else 1,
                        format_func=lambda x: "Mobil" if x == "car" else "Sepeda Motor"
                    )
                    curr_m_stat = curr_m.get("status", "active")
                    e_m_stat = st.selectbox(
                        "Status Kartu:",
                        options=["active", "inactive"],
                        index=0 if curr_m_stat == "active" else 1,
                        format_func=lambda x: "🟢 Aktif (Active)" if x == "active" else "🔴 Nonaktif (Inactive)"
                    )
                    sub_edit_m = st.form_submit_button("💾 Simpan Perubahan Member", use_container_width=True)
                    if sub_edit_m:
                        if not e_m_name or not e_m_plate:
                            st.error("Nama member dan plat kendaraan tidak boleh kosong!")
                        else:
                            try:
                                update_member(
                                    supabase,
                                    target_uid,
                                    member_name=e_m_name,
                                    license_plate=e_m_plate,
                                    vehicle_type=e_m_vtype,
                                    status=e_m_stat
                                )
                                st.success(f"Data member {e_m_name} berhasil diperbarui!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal memperbarui member: {str(e)}")

            with col_m_ed2:
                st.write("**🗑️ Hapus Member RFID**")
                st.warning(f"Tindakan ini akan menghapus kartu UID `{target_uid}` dari sistem.")
                with st.form(f"form_del_m_{target_uid}"):
                    confirm_del_m = st.checkbox(f"Saya yakin ingin menghapus member '{curr_m.get('member_name')}' secara permanen.")
                    sub_del_m = st.form_submit_button("🗑️ Hapus Member Permanen", use_container_width=True)
                    if sub_del_m:
                        if not confirm_del_m:
                            st.error("Silakan centang konfirmasi sebelum menghapus.")
                        else:
                            try:
                                delete_member(supabase, target_uid)
                                st.success(f"Member {curr_m.get('member_name')} berhasil dihapus.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal menghapus member: {str(e)}")

    with st.expander("🧹 Bersihkan Riwayat Scan RFID Perangkat", expanded=False):
        st.caption(f"Hapus seluruh log scan kartu RFID yang dikirim oleh perangkat `{dev_id}`:")
        with st.form(f"form_clear_rfid_{dev_id}"):
            confirm_clear_rfid = st.checkbox(f"Saya yakin ingin mengosongkan riwayat scan RFID perangkat '{dev_id}'.")
            sub_clear_rfid = st.form_submit_button("🗑️ Kosongkan Log Scan RFID", use_container_width=True)
            if sub_clear_rfid:
                if not confirm_clear_rfid:
                    st.error("Silakan centang konfirmasi sebelum mengosongkan log scan.")
                else:
                    try:
                        clear_rfid_scans_by_device(supabase, dev_id)
                        st.success(f"Riwayat scan RFID untuk {dev_id} berhasil dikosongkan.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal mengosongkan scan: {str(e)}")

with tab_telemetry:
    st.subheader("Telemetri Sensor Perangkat")
    render_student_telemetry_live(dev_id)

    with st.expander("🧹 Bersihkan Riwayat Data Sensor Perangkat", expanded=False):
        st.caption(f"Hapus rekaman log telemetri sensor (ultrasonik & IR) yang dikirim oleh perangkat `{dev_id}`:")
        with st.form(f"form_clear_sensor_{dev_id}"):
            confirm_clear_sens = st.checkbox(f"Saya yakin ingin mengosongkan riwayat sensor perangkat '{dev_id}'.")
            sub_clear_sens = st.form_submit_button("🗑️ Kosongkan Data Sensor", use_container_width=True)
            if sub_clear_sens:
                if not confirm_clear_sens:
                    st.error("Silakan centang konfirmasi sebelum mengosongkan data sensor.")
                else:
                    try:
                        clear_sensor_data_by_device(supabase, dev_id)
                        st.success(f"Data sensor untuk perangkat {dev_id} berhasil dibersihkan.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal membersihkan data sensor: {str(e)}")

# -------------------------------------------------------------
# TAB 4: Kredensial & Kode C++
# -------------------------------------------------------------
with tab_credentials:
    st.subheader("Kredensial Koneksi IoT")
    st.caption("Gunakan kredensial ini di firmware ESP32-S3 Anda untuk menghubungkan board ke sistem:")

    supa_url = os.getenv("SUPABASE_URL", "https://wxowndnwwzryzdkdkkqx.supabase.co")
    supa_key = os.getenv("SUPABASE_KEY", "sb_publishable_...")

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.text_input("Device ID Anda:", value=dev_id, disabled=True)
        st.text_input("API Key Khusus:", value=api_key, disabled=True)
    with col_c2:
        st.text_input("Supabase Project URL:", value=supa_url, disabled=True)
        st.text_input("Supabase Anon/Publishable Key:", value=supa_key, disabled=True)

    st.markdown("##### Endpoint REST API:")
    st.code(
        f"""
POST {supa_url}/rest/v1/iot_devices    -> Kirim Heartbeat Perangkat
POST {supa_url}/rest/v1/sensor_data    -> Kirim Telemetri Sensor
POST {supa_url}/rest/v1/rfid_scans     -> Kirim Tap Kartu RFID
        """.strip(),
        language="http"
    )

    st.markdown("##### Template Firmware ESP32-S3 C++ Siap Pakai:")
    code_snippet = generate_esp32_code_snippet(
        device_id=dev_id,
        api_key=api_key,
        supabase_url=supa_url,
        supabase_anon_key=supa_key,
    )
    st.code(code_snippet, language="cpp")

# -------------------------------------------------------------
# TAB 4: Simulator Uji Coba Web
# -------------------------------------------------------------
with tab_sim:
    st.subheader("🧪 Simulator Uji Coba Telemetri (Tanpa Hardware)")
    st.caption("Uji transmisi data ke database Supabase langsung dari browser sebelum unit ESP32-S3 dirakit:")

    col_s1, col_s2 = st.columns(2)

    with col_s1:
        st.write("##### 1. Simulasi Heartbeat (Online Status)")
        if st.button(f"📡 Kirim Sinyal Heartbeat Sekarang ({dev_id})", use_container_width=True):
            try:
                update_device_heartbeat(supabase, dev_id, status="online", device_name=dev_name)
                st.success(f"Heartbeat untuk {dev_id} berhasil dikirim! Perangkat berstatus ONLINE.")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal mengirim heartbeat: {str(e)}")

        st.markdown("---")
        st.write("##### 2. Simulasi Sensor Ultrasonik HC-SR04")
        sim_dist = st.slider("Pilih Jarak Simulasi (cm):", min_value=5.0, max_value=200.0, value=25.0, step=0.5)
        if st.button("Kirim Data Jarak Ultrasonik", use_container_width=True):
            try:
                supabase.table("sensor_data").insert({
                    "device_id": dev_id,
                    "sensor_type": "ultrasonic",
                    "sensor_value": float(sim_dist),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
                st.success(f"Data jarak {sim_dist} cm berhasil dicatat!")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal mengirim data sensor: {str(e)}")

    with col_s2:
        st.write("##### 3. Simulasi Tap Kartu RFID")
        sim_uid = st.text_input("UID Kartu RFID Uji (Hex):", value="A1B2C3D4").strip().upper()
        if st.button("Kirim Data Scan RFID", use_container_width=True):
            try:
                supabase.table("rfid_scans").insert({
                    "device_id": dev_id,
                    "uid": sim_uid,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
                st.success(f"Scan RFID {sim_uid} berhasil dikirim!")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal mengirim scan RFID: {str(e)}")

        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        st.write("##### 4. Uji Anti-Passback & Audit Forensik")

        sim_col1, sim_col2 = st.columns(2)
        with sim_col1:
            if st.button("🚗 Simulasi Tap Masuk", use_container_width=True):
                res = process_gate_entry(supabase, sim_uid, device_id=dev_id)
                if res["authorized"]:
                    st.success(f"✅ Akses Masuk Diberikan! (inside_parking = True)")
                    if res.get("photo_url"):
                        st.image(res["photo_url"], caption="Snapshot Kamera Gerbang Masuk")
                elif res["status"] == "anti_passback_violation":
                    st.error(f"🚨 DITOLAK: Pelanggaran Anti-Passback! Kartu {sim_uid} sudah berada di dalam!")
                    if res.get("photo_url"):
                        st.image(res["photo_url"], caption="Snapshot Pelanggaran Anti-Passback")
                else:
                    st.warning(f"Akses ditolak: Status {res['status']}")

        with sim_col2:
            if st.button("🚙 Simulasi Tap Keluar", use_container_width=True):
                res = process_gate_exit(supabase, sim_uid, device_id=dev_id)
                if res["authorized"]:
                    st.success(f"✅ Akses Keluar Diberikan! (inside_parking direset ke False)")
                    if res.get("photo_url"):
                        st.image(res["photo_url"], caption="Snapshot Kamera Gerbang Keluar")
                else:
                    st.warning(f"Akses keluar ditolak: {res['status']}")

        if st.button("🚨 Simulasikan Insiden Mobil Membuntuti (Tailgating)", type="secondary", use_container_width=True):
            t_res = report_tailgating(supabase, device_id=dev_id)
            st.error("🚨 ALARM TAILGATING AKTIF! Kendaraan membuntuti tercatat di Log Audit Forensik.")
            if t_res.get("photo_url"):
                st.image(t_res["photo_url"], caption="Snapshot Deteksi Tailgating (Membuntuti)")

