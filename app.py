"""
Smart Parking Monitoring & RFID Member System - Dashboard Utama (app.py)

Fokus Halaman Dashboard Utama (Admin & User):
- Pemantauan seluruh Perangkat Siswa (Student IoT Device Fleet Monitor)
- Ringkasan metrik: Total Perangkat Siswa, Perangkat Aktif (Online), Perangkat Tidak Aktif (Offline)
- Filter status koneksi (Semua, Online, Offline)
- Kartu status perangkat siswa dengan indikator ONLINE/OFFLINE, waktu terakhir terhubung (heartbeat), slot terikat, dan jenis sensor
- Pintasan langsung untuk audit / buka Dashboard Siswa dan registrasi perangkat siswa baru
- Auto-refresh realtime fragment (3 detik)
"""

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
    get_student_devices,
    get_all_devices,
    is_device_online,
    register_student_device,
)
from services.parking_service import get_parking_slots

# 1. Page Configuration
st.set_page_config(
    page_title="Smart Parking - Dashboard Perangkat Siswa",
    page_icon="🎓",
    layout="wide",
)

# 2. Setup Auto-Refresh (Realtime fragment 3s)
setup_auto_refresh(interval_ms=4000, key="dashboard_autorefresh")

# 3. Retrieve Supabase Client
supabase = get_app_supabase()

# 4. Authentication Check
user = require_auth(supabase, allowed_roles=None, current_page_name="app.py")

# 5. Sidebar Navigation & Branding
render_sidebar_branding(supabase=supabase)

# 6. Header
is_admin = user.get("role") == "admin"
st.title("🎓 DASHBOARD MONITORING PERANGKAT SISWA")

if is_admin:
    st.caption("Panel Administrator: Memantau Seluruh Perangkat IoT Siswa yang Terdaftar, Status Aktif / Tidak Aktif (Real-Time), dan Konektivitas.")
else:
    st.info(f"👋 Halo, **{user.get('full_name')}** (Siswa). Anda dapat memantau status perangkat Anda di bawah ini atau membuka menu **🎓 5_Dashboard_Siswa** untuk kontrol lengkap.")
    st.caption("Status Perangkat IoT dan Konektivitas Real-Time")

st.markdown("---")


@realtime_fragment(run_every="3s")
def render_live_device_fleet():
    with system_loading(
        message="Memeriksa Status Perangkat Siswa...",
        subtext="Mengambil data koneksi, heartbeat, dan status aktif/tidak aktif...",
        key="student_device_fleet",
        only_initial=True,
    ):
        student_devices = get_student_devices(supabase)
        slots = get_parking_slots(supabase)

    # Hitung metrik perangkat
    total_devs = len(student_devices)
    online_count = sum(1 for d in student_devices if is_device_online(d.get("last_seen"), threshold_seconds=30))
    offline_count = total_devs - online_count

    # 1. Summary Metric Cards
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric(
            label="Total Perangkat Siswa",
            value=total_devs,
            help="Total unit modul ESP32 siswa yang telah didaftarkan ke sistem",
        )
    with m2:
        st.metric(
            label="🟢 Perangkat Aktif (Online)",
            value=online_count,
            delta="Terhubung (Heartbeat < 30s)",
            delta_color="normal",
            help="Perangkat yang saat ini aktif berkomunikasi dan mengirimkan data",
        )
    with m3:
        st.metric(
            label="🔴 Perangkat Tidak Aktif (Offline)",
            value=offline_count,
            delta="-Tidak Aktif" if offline_count > 0 else "0",
            delta_color="inverse" if offline_count > 0 else "normal",
            help="Perangkat yang mati, terputus dari WiFi, atau tidak mengirim heartbeat lebih dari 30 detik",
        )

    st.markdown("---")

    # 2. Controls: Filter Status & Pencarian
    f_col1, f_col2 = st.columns([2, 1])
    with f_col1:
        search_query = st.text_input(
            "🔍 Cari Siswa / Device ID / Tipe Sensor:",
            placeholder="Ketik nama siswa atau ID perangkat...",
            key="dash_dev_search",
        ).strip().lower()

    with f_col2:
        filter_status = st.selectbox(
            "Filter Status Koneksi:",
            options=["Semua Status", "Hanya Aktif (Online)", "Hanya Tidak Aktif (Offline)"],
            key="dash_dev_filter_status",
        )

    # Filtering logic
    filtered_list = []
    for d in student_devices:
        d_online = is_device_online(d.get("last_seen"), threshold_seconds=30)
        
        # Filter status
        if filter_status == "Hanya Aktif (Online)" and not d_online:
            continue
        if filter_status == "Hanya Tidak Aktif (Offline)" and d_online:
            continue

        # Filter query
        owner = str(d.get("owner_name", "")).lower()
        dev_id = str(d.get("device_id", "")).lower()
        dev_name = str(d.get("device_name", "")).lower()
        dev_type = str(d.get("device_type", "")).lower()

        if search_query and not (search_query in owner or search_query in dev_id or search_query in dev_name or search_query in dev_type):
            continue

        filtered_list.append((d, d_online))

    st.caption(f"Menampilkan **{len(filtered_list)}** dari **{total_devs}** perangkat siswa terdaftar.")

    # 3. Grid Tampilan Perangkat
    if not filtered_list:
        st.info("💡 Tidak ada perangkat siswa yang sesuai dengan filter atau kriteria pencarian.")
    else:
        num_cards = len(filtered_list)
        cols_count = 3 if num_cards >= 3 else (2 if num_cards == 2 else 1)
        row_chunks = [filtered_list[i:i + cols_count] for i in range(0, num_cards, cols_count)]

        for row in row_chunks:
            dev_cols = st.columns(cols_count)
            for idx, (dev, d_online) in enumerate(row):
                with dev_cols[idx]:
                    d_id = dev.get("device_id", "-")
                    d_name = dev.get("device_name", "ESP32 Node")
                    d_owner = dev.get("owner_name", "Siswa")
                    d_type = dev.get("device_type", "multi-sensor")
                    d_seen = dev.get("last_seen")
                    d_rel_seen = get_relative_time(d_seen)
                    d_abs_seen = format_timestamp(d_seen)

                    # Info slot parkir yang terikat dengan perangkat ini
                    dev_slots = [s for s in slots if s.get("device_id") == d_id]
                    if dev_slots:
                        avail_s = sum(1 for s in dev_slots if s.get("status") == "available")
                        slot_str = f"🅿️ {avail_s}/{len(dev_slots)} Slot Kosong ({', '.join([s.get('slot_code', '') for s in dev_slots])})"
                    else:
                        slot_str = "🅿️ Belum ada slot parkir terikat"

                    card_border = "#10B981" if d_online else "#EF4444"
                    card_bg = "#F0FDF4" if d_online else "#FEF2F2"
                    status_text = "AKTIF (ONLINE)" if d_online else "TIDAK AKTIF (OFFLINE)"
                    status_badge = render_status_badge("ONLINE" if d_online else "OFFLINE", label=status_text)

                    type_label = {
                        "multi-sensor": "All-in-One (Ultrasonik + IR + RFID)",
                        "gate": "Gerbang (RFID + Servo)",
                        "parking-slot": "Sensor Slot IR",
                    }.get(d_type, d_type)

                    st.markdown(
                        f"""
                        <div style="border: 2px solid {card_border}; background-color: {card_bg};
                                    border-radius: 14px; padding: 18px; margin-bottom: 12px;
                                    box-shadow: 0 2px 6px rgba(0,0,0,0.04);">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                                <div>
                                    <span style="font-size: 1.2rem; font-weight: 800; color: #0F172A;">👤 {d_owner}</span>
                                    <div style="font-size: 0.9rem; font-weight: 600; color: #334155;">{d_name}</div>
                                </div>
                                <div>{status_badge}</div>
                            </div>
                            <div style="border-top: 1px solid rgba(0,0,0,0.06); padding-top: 10px; margin-bottom: 8px;">
                                <div style="font-size: 0.85rem; color: #475569; margin-bottom: 4px;">
                                    <b>Device ID:</b> <code style="font-size: 0.88rem; background: #E2E8F0; padding: 2px 6px; border-radius: 4px;">{d_id}</code>
                                </div>
                                <div style="font-size: 0.85rem; color: #475569; margin-bottom: 4px;">
                                    <b>Tipe Node:</b> {type_label}
                                </div>
                                <div style="font-size: 0.85rem; color: #475569; margin-bottom: 4px;">
                                    <b>Status Slot:</b> <span style="color: #1E293B; font-weight: 600;">{slot_str}</span>
                                </div>
                                <div style="font-size: 0.82rem; color: #64748B;">
                                    <b>Terakhir Terhubung:</b> {d_abs_seen} ({d_rel_seen})
                                </div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    btn_text = f"👉 Buka Dashboard {d_owner}"
                    if st.button(
                        btn_text,
                        key=f"dash_btn_nav_{d_id}",
                        use_container_width=True,
                        type="primary" if d_online else "secondary",
                    ):
                        st.session_state["target_student_device_id"] = d_id
                        st.switch_page("pages/5_Dashboard_Siswa.py")

    # 4. Tabel Ringkasan Komprehensif
    st.markdown("---")
    st.subheader("📋 Tabel Detail Perangkat Siswa")
    
    if student_devices:
        table_rows = []
        for d in student_devices:
            d_on = is_device_online(d.get("last_seen"), threshold_seconds=30)
            table_rows.append({
                "Nama Siswa / Pemilik": d.get("owner_name", "-"),
                "Device ID": d.get("device_id", "-"),
                "Nama Perangkat": d.get("device_name", "-"),
                "Tipe Perangkat": d.get("device_type", "-"),
                "Status Koneksi": "🟢 Aktif (Online)" if d_on else "🔴 Tidak Aktif (Offline)",
                "Terakhir Terhubung": format_timestamp(d.get("last_seen")),
                "Waktu Relatif": get_relative_time(d.get("last_seen")),
                "Dibuat Pada": format_timestamp(d.get("created_at")),
            })
        
        df_table = pd.DataFrame(table_rows)
        st.dataframe(df_table, width="stretch", hide_index=True)


# Render komponen utama secara realtime fragment
render_live_device_fleet()

# 7. Opsi Tambah Perangkat Siswa Cepat (Khusus Admin)
if is_admin:
    st.markdown("---")
    with st.expander("➕ Tambah Perangkat Siswa Baru (Registrasi Cepat)", expanded=False):
        st.caption("Daftarkan perangkat ESP32 untuk siswa baru langsung dari Dashboard Utama:")
        with st.form("quick_add_student_device_form"):
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                in_owner = st.text_input("Nama Lengkap Siswa / Kelompok:*", placeholder="Contoh: Rian Pratama")
                in_name = st.text_input("Nama Perangkat IoT:*", placeholder="Contoh: ESP32 Gerbang Siswa Rian")
            with col_a2:
                in_type = st.selectbox(
                    "Tipe Perangkat IoT:",
                    options=["multi-sensor", "gate", "parking-slot"],
                    format_func=lambda x: {
                        "multi-sensor": "All-in-One (Ultrasonik + IR + RFID)",
                        "gate": "Gerbang Masuk (RFID + Servo)",
                        "parking-slot": "Slot Parkir (Sensor IR)"
                    }.get(x, x)
                )
                in_custom_id = st.text_input("Custom Device ID (Opsional, kosongkan untuk auto):", placeholder="DEV-SISWA-XXXX").strip().upper()

            submit_add = st.form_submit_button("🚀 Daftarkan Perangkat Siswa", use_container_width=True, type="primary")

            if submit_add:
                if not in_owner.strip() or not in_name.strip():
                    st.error("Nama siswa dan nama perangkat wajib diisi!")
                else:
                    try:
                        new_dev = register_student_device(
                            supabase,
                            owner_name=in_owner.strip(),
                            device_name=in_name.strip(),
                            device_type=in_type,
                            device_id=in_custom_id if in_custom_id else None
                        )
                        st.success(f"🎉 Perangkat **{new_dev.get('device_id')}** milik **{in_owner}** berhasil ditambahkan!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal mendaftarkan perangkat: {str(e)}")
