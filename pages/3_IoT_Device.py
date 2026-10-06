"""
Smart Parking Monitoring & RFID Member System - IoT Device
Page: pages/3_IoT_Device.py

Adheres strictly to DRD Sec 14 & 19 and TRD Sec 21:
- Device cards for registered devices (GATE-01, PARKING-01)
- Device Name, Device ID
- Online/Offline status badge based on 30-second heartbeat threshold
- Last Seen relative and absolute timestamps
- Warning banner when devices are OFFLINE
- Auto-refresh enabled (4s)
- Strictly NO manual gate buttons
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
    format_timestamp,
    get_relative_time,
    require_auth,
    system_loading,
)
from services.device_service import (
    get_all_devices,
    is_device_online,
    update_device_heartbeat,
    register_student_device,
    generate_esp32_code_snippet,
    get_student_devices,
    get_student_device_full_details,
    get_student_device_telemetry,
    update_device,
    delete_device,
)

# 1. Page Config
st.set_page_config(
    page_title="Smart Parking - IoT Device",
    page_icon="📟",
    layout="wide",
)

# 2. Setup Auto-Refresh
setup_auto_refresh(interval_ms=4000, key="iot_autorefresh")

# 3. Retrieve Supabase Client
supabase = get_app_supabase()

# 4. Authentication Check (Admin Only)
user = require_auth(supabase, allowed_roles=["admin"], current_page_name="3_IoT_Device.py")

# 5. Sidebar Branding
render_sidebar_branding(supabase=supabase)

# 5. Header
st.title("📟 Status Perangkat IoT")
st.caption("Pemantauan Konektivitas ESP32-S3 & Node Mikrokontroler")
st.markdown("---")

# 6. Fetch Registered Devices
with system_loading(
    message="Memeriksa Status Perangkat IoT...",
    subtext="Mengambil heartbeat ESP32-S3 & node siswa...",
    key="iot_devices_list",
    only_initial=True,
):
    devices = get_all_devices(supabase)

# 7. Check Online/Offline States
any_device_offline = False
offline_device_names = []

for dev in devices:
    last_seen = dev.get("last_seen")
    online = is_device_online(last_seen, threshold_seconds=30)
    if not online:
        any_device_offline = True
        offline_device_names.append(dev.get("device_id", "Unknown"))

# 8. Offline Warning Banner (DRD Sec 19)
if any_device_offline:
    offline_list_str = ", ".join(offline_device_names)
    st.error(
        f"⚠️ **ESP32-S3 OFFLINE ({offline_list_str})**: Data sensor mungkin tidak diperbarui. "
        "Periksa koneksi WiFi atau daya perangkat."
    )
else:
    st.success("🟢 **Semua Node IoT Beroperasi Normal**: Koneksi ESP32-S3 stabil dan mengirimkan heartbeat berkala.")

st.markdown("---")

# 9. Device Nodes Sections
infra_devices = [d for d in devices if not d.get("owner_name") and not d.get("device_id", "").startswith("DEV-SISWA")]
student_devices = [d for d in devices if d.get("owner_name") or d.get("device_id", "").startswith("DEV-SISWA")]

# --- SECTION A: INFRASTRUKTUR SISTEM ---
st.subheader("🏢 Node Infrastruktur Utama")
if not infra_devices:
    st.info("Tidak ada perangkat infrastruktur terdaftar.")
else:
    cols_infra = st.columns(len(infra_devices) if len(infra_devices) <= 3 else 3)
    for idx, dev in enumerate(infra_devices):
        with cols_infra[idx % 3]:
            dev_id = dev.get("device_id", "-")
            dev_name = dev.get("device_name", "ESP32-S3 Node")
            last_seen_raw = dev.get("last_seen")
            online = is_device_online(last_seen_raw, threshold_seconds=30)
            status_str = "ONLINE" if online else "OFFLINE"
            badge = render_status_badge(status_str)
            last_seen_fmt = format_timestamp(last_seen_raw)
            rel_seen = get_relative_time(last_seen_raw)
            border_clr = "#10B981" if online else "#EF4444"
            bg_clr = "#F0FDF4" if online else "#FEF2F2"

            st.markdown(
                f"""
                <div style="border: 2px solid {border_clr}; background-color: {bg_clr}; 
                            border-radius: 12px; padding: 18px; margin-bottom: 16px;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
                        <div>
                            <div style="font-size: 1.15rem; font-weight: 800; color: #0F172A;">{dev_name}</div>
                            <div style="font-family: monospace; font-size: 0.9rem; color: #475569; font-weight: 600;">ID: {dev_id}</div>
                        </div>
                        <div>{badge}</div>
                    </div>
                    <div style="border-top: 1px solid rgba(0,0,0,0.08); padding-top: 10px; font-size: 0.84rem;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                            <span style="color: #64748B;">Aktif:</span>
                            <span style="font-weight: 600; color: #1E293B;">{rel_seen}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; font-size: 0.76rem; color: #64748B;">
                            <span>Timestamp:</span>
                            <span>{last_seen_fmt}</span>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.markdown("---")

# --- SECTION B: NODE PERANGKAT SISWA ---
st.subheader("🎓 Node Perangkat Siswa (Student IoT Cards)")
st.caption("Monitoring kartu node perangkat milik siswa dan inspeksi menyeluruh:")

# Student Metrics Row
total_student_nodes = len(student_devices)
online_student_nodes = sum(1 for d in student_devices if is_device_online(d.get("last_seen"), threshold_seconds=30))
offline_student_nodes = total_student_nodes - online_student_nodes

col_sm1, col_sm2, col_sm3, col_sm4 = st.columns([1, 1, 1, 2])
with col_sm1:
    st.metric("Total Perangkat Siswa", total_student_nodes)
with col_sm2:
    st.metric("Siswa Online", online_student_nodes)
with col_sm3:
    st.metric("Siswa Offline", offline_student_nodes)
with col_sm4:
    search_student = st.text_input("🔍 Cari Siswa / Device ID:", placeholder="Ketik nama atau ID perangkat...").strip().lower()

if not student_devices:
    st.info("💡 Belum ada perangkat siswa yang terdaftar. Siswa dapat mendaftar akun di portal registrasi atau melalui tab 'Tambah Device' di bawah.")
else:
    # Filter search
    filtered_students = [
        d for d in student_devices
        if not search_student or
        search_student in d.get("owner_name", "").lower() or
        search_student in d.get("device_id", "").lower() or
        search_student in d.get("device_name", "").lower()
    ]

    if not filtered_students:
        st.warning(f"Tidak ada perangkat siswa yang cocok dengan pencarian '{search_student}'.")
    else:
        cols_student = st.columns(3)
        for idx, dev in enumerate(filtered_students):
            with cols_student[idx % 3]:
                dev_id = dev.get("device_id", "-")
                dev_name = dev.get("device_name", "ESP32-S3 Siswa")
                owner_name = dev.get("owner_name", "Siswa")
                dev_type = dev.get("device_type", "multi-sensor")
                last_seen_raw = dev.get("last_seen")
                online = is_device_online(last_seen_raw, threshold_seconds=30)
                status_str = "ONLINE" if online else "OFFLINE"
                badge = render_status_badge(status_str)
                last_seen_fmt = format_timestamp(last_seen_raw)
                rel_seen = get_relative_time(last_seen_raw)

                # Fetch isolated telemetry overview
                telem = get_student_device_telemetry(supabase, dev_id)
                latest_dist = telem.get("latest_ultrasonic")
                total_telems = len(telem.get("sensors", []))
                total_scans = len(telem.get("scans", []))

                dist_str = f"{latest_dist:.1f} cm" if latest_dist is not None else "-"
                border_clr = "#10B981" if online else "#EF4444"
                bg_clr = "#F0FDF4" if online else "#FEF2F2"

                st.markdown(
                    f"""
                    <div style="border: 2px solid {border_clr}; background-color: {bg_clr}; 
                                border-radius: 12px; padding: 18px; margin-bottom: 12px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                            <div>
                                <span style="font-size: 0.75rem; font-weight: 700; color: #4338CA; text-transform: uppercase;">🎓 {owner_name}</span>
                                <div style="font-size: 1.15rem; font-weight: 800; color: #0F172A;">{dev_name}</div>
                                <div style="font-family: monospace; font-size: 0.85rem; color: #475569; font-weight: 600;">ID: {dev_id}</div>
                            </div>
                            <div>{badge}</div>
                        </div>
                        <div style="background: white; border: 1px solid rgba(0,0,0,0.06); border-radius: 8px; padding: 8px 12px; margin: 8px 0; font-size: 0.82rem;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 3px;">
                                <span style="color: #64748B;">Ultrasonik:</span>
                                <b>{dist_str}</b>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 3px;">
                                <span style="color: #64748B;">Data Telemetri:</span>
                                <b>{total_telems} rekaman</b>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: #64748B;">Scan RFID:</span>
                                <b>{total_scans} kartu</b>
                            </div>
                        </div>
                        <div style="font-size: 0.78rem; color: #64748B; margin-bottom: 8px;">
                            Aktif: <b>{rel_seen}</b> ({last_seen_fmt})
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if st.button(f"🔍 Lihat Detail Lengkap", key=f"btn_inspect_{dev_id}", use_container_width=True):
                    st.session_state["admin_inspecting_device_id"] = dev_id
                    st.rerun()

# --- SECTION C: INSPEKTUR DETAIL PERANGKAT SISWA ---
inspect_id = st.session_state.get("admin_inspecting_device_id")
if inspect_id:
    details = get_student_device_full_details(supabase, inspect_id)
    if details:
        dev_info = details.get("device", {})
        dev_online = details.get("online", False)
        telem_data = details.get("telemetry", {})
        sensors_list = telem_data.get("sensors", [])
        scans_list = telem_data.get("scans", [])

        st.markdown("---")
        col_hdr1, col_hdr2 = st.columns([4, 1])
        with col_hdr1:
            st.markdown(f"### 📋 Inspeksi Menyeluruh: {dev_info.get('device_name')} (`{inspect_id}`)")
            st.caption(f"Pemilik Perangkat: **{dev_info.get('owner_name')}** • Status: {'ONLINE' if dev_online else 'OFFLINE'}")
        with col_hdr2:
            if st.button("✕ Tutup Detail", use_container_width=True):
                st.session_state.pop("admin_inspecting_device_id", None)
                st.rerun()

        tab_dt1, tab_dt2, tab_dt3, tab_dt4, tab_dt5 = st.tabs([
            "📊 Riwayat Telemetri Sensor",
            "💳 Riwayat Scan Kartu RFID",
            "🔑 Kredensial & Firmware C++",
            "🛠️ Diagnostik & Kontrol Uji",
            "⚙️ Edit & Hapus Perangkat",
        ])

        with tab_dt1:
            st.write("##### Log Telemetri Sensor Siswa:")
            if sensors_list:
                col_dm1, col_dm2, col_dm3 = st.columns(3)
                latest_u = details.get("latest_ultrasonic")
                with col_dm1:
                    if latest_u is not None:
                        u_val = float(latest_u)
                        st.metric("Jarak Ultrasonik Terbaru", f"{u_val:.1f} cm", delta="Mobil Terdeteksi (&le; 20cm)" if (u_val > 0 and u_val <= 20.0) else "Tidak Ada Mobil")
                    else:
                        st.metric("Jarak Ultrasonik Terbaru", "- cm")
                with col_dm2:
                    ir_vals = [s.get("sensor_value") for s in sensors_list if s.get("sensor_type") == "ir"]
                    st.metric("Nilai ADC IR Terbaru", f"{ir_vals[0]}" if ir_vals else "-")
                with col_dm3:
                    st.metric("Total Rekaman Sensor", len(sensors_list))

                df_sens = pd.DataFrame(sensors_list)
                st.dataframe(df_sens[["sensor_type", "sensor_value", "created_at"]], width="stretch", height=250)
            else:
                st.info(f"Belum ada data sensor yang masuk dari perangkat `{inspect_id}`.")

        with tab_dt2:
            st.write("##### Log Pembacaan Kartu RFID Siswa:")
            if scans_list:
                st.success(f"💳 Kartu Terakhir: UID **`{scans_list[0].get('uid')}`** (Waktu: {format_timestamp(scans_list[0].get('created_at'))})")
                df_scans = pd.DataFrame(scans_list)
                st.dataframe(df_scans[["uid", "created_at"]], width="stretch", height=250)
            else:
                st.info(f"Belum ada data scan RFID yang dikirim oleh perangkat `{inspect_id}`.")

        with tab_dt3:
            st.write("##### Kredensial Perangkat & Source Code:")
            supa_url = os.getenv("SUPABASE_URL", "https://wxowndnwwzryzdkdkkqx.supabase.co")
            supa_key = os.getenv("SUPABASE_KEY", "sb_publishable_...")
            col_k1, col_k2 = st.columns(2)
            with col_k1:
                st.text_input("Device ID:", value=inspect_id, disabled=True, key=f"insp_id_{inspect_id}")
                st.text_input("API Key Khusus Siswa:", value=dev_info.get("api_key", "-"), disabled=True, key=f"insp_key_{inspect_id}")
            with col_k2:
                st.text_input("Pemilik:", value=dev_info.get("owner_name", "-"), disabled=True, key=f"insp_own_{inspect_id}")
                st.text_input("Tanggal Dibuat:", value=format_timestamp(dev_info.get("created_at")), disabled=True, key=f"insp_date_{inspect_id}")

            with st.expander("📄 Tampilkan Template Firmware ESP32-S3 Arduino C++"):
                code_cpp = generate_esp32_code_snippet(
                    device_id=inspect_id,
                    api_key=dev_info.get("api_key", "-"),
                    supabase_url=supa_url,
                    supabase_anon_key=supa_key
                )
                st.code(code_cpp, language="cpp")

        with tab_dt4:
            st.write("##### Uji Konektivitas Perangkat:")
            col_act1, col_act2 = st.columns(2)
            with col_act1:
                if st.button(f"📡 Kirim Ping Heartbeat ({inspect_id})", use_container_width=True, key=f"ping_btn_{inspect_id}"):
                    try:
                        update_device_heartbeat(supabase, inspect_id, status="online", device_name=dev_info.get("device_name"))
                        st.success(f"Heartbeat berhasil dikirim untuk {inspect_id}! Status berubah menjadi ONLINE.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal mengirim heartbeat: {str(e)}")
            with col_act2:
                sim_test_dist = st.number_input("Jarak Uji (cm):", value=18.5, min_value=1.0, max_value=300.0, step=0.5, key=f"num_{inspect_id}")
                if st.button(f"🧪 Kirim Data Sensor Uji", use_container_width=True, key=f"test_sensor_{inspect_id}"):
                    try:
                        supabase.table("sensor_data").insert({
                            "device_id": inspect_id,
                            "sensor_type": "ultrasonic",
                            "sensor_value": float(sim_test_dist),
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }).execute()
                        st.success(f"Data sensor {sim_test_dist} cm berhasil dikirim ke {inspect_id}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal mengirim data sensor: {str(e)}")

        with tab_dt5:
            st.write(f"##### ⚙️ Pengaturan & Penghapusan Perangkat: `{inspect_id}`")
            col_ed1, col_ed2 = st.columns(2)
            with col_ed1:
                st.write("**✏️ Edit Detail Perangkat**")
                with st.form(f"form_edit_dev_{inspect_id}"):
                    curr_dname = dev_info.get("device_name", "")
                    curr_owner = dev_info.get("owner_name", "")
                    curr_dtype = dev_info.get("device_type", "multi-sensor")
                    dtype_options = ["multi-sensor", "gate", "parking-slot"]
                    default_dtype_idx = dtype_options.index(curr_dtype) if curr_dtype in dtype_options else 0

                    edit_name = st.text_input("Nama Perangkat:", value=curr_dname).strip()
                    edit_owner = st.text_input("Pemilik / Siswa:", value=curr_owner).strip()
                    edit_dtype = st.selectbox(
                        "Tipe Perangkat:",
                        options=dtype_options,
                        index=default_dtype_idx,
                        format_func=lambda x: {
                            "multi-sensor": "All-in-One (Ultrasonik + IR + RFID)",
                            "gate": "Gerbang Masuk (RFID + Servo)",
                            "parking-slot": "Slot Parkir (IR ADC Sensor)"
                        }.get(x, x),
                        key=f"edit_dtype_{inspect_id}",
                    )
                    submit_dev_edit = st.form_submit_button("💾 Simpan Perubahan Perangkat", use_container_width=True)
                    if submit_dev_edit:
                        if not edit_name or not edit_owner:
                            st.error("Nama perangkat dan pemilik tidak boleh kosong!")
                        else:
                            try:
                                update_device(
                                    supabase,
                                    inspect_id,
                                    device_name=edit_name,
                                    owner_name=edit_owner,
                                    device_type=edit_dtype,
                                )
                                st.success(f"Perangkat {inspect_id} berhasil diperbarui!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal memperbarui perangkat: {str(e)}")

            with col_ed2:
                st.write("**🗑️ Hapus Perangkat**")
                st.warning(f"Tindakan ini akan menghapus perangkat `{inspect_id}` dari sistem database secara permanen.")
                with st.form(f"form_del_dev_{inspect_id}"):
                    confirm_del_dev = st.checkbox(f"Saya yakin ingin menghapus perangkat '{inspect_id}' secara permanen.")
                    submit_dev_del = st.form_submit_button("🗑️ Hapus Perangkat Permanen", use_container_width=True)
                    if submit_dev_del:
                        if not confirm_del_dev:
                            st.error("Silakan centang kotak konfirmasi sebelum menghapus.")
                        else:
                            try:
                                delete_device(supabase, inspect_id)
                                st.session_state.pop("admin_inspecting_device_id", None)
                                st.success(f"Perangkat {inspect_id} berhasil dihapus.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal menghapus perangkat: {str(e)}")


st.markdown("---")

# 10. Device Diagnostics & Technical Parameters
col_diag1, col_diag2 = st.columns(2)

with col_diag1:
    st.subheader("⚙️ Parameter Teknis IoT")
    st.markdown(
        """
        - **Protokol Komunikasi**: WiFi 2.4 GHz • HTTPS REST API / Supabase Client
        - **Heartbeat Interval**: 10 detik (dikirim otomatis oleh ESP32-S3 firmware)
        - **Offline Threshold**: 30 detik (jika tidak ada data diterima selama >30s, status berubah menjadi OFFLINE)
        - **Gate Controller**: Dikendalikan lokal di ESP32-S3 (tanpa tombol manual web)
        """
    )

with col_diag2:
    st.subheader("🧪 Simulasi & Tambah Device")
    
    # Tab 1: Heartbeat Simulation, Tab 2: Registrasi Perangkat Baru, Tab 3: Edit Device, Tab 4: Hapus Device
    tab_sim, tab_add, tab_edit, tab_del = st.tabs(["📡 Ping Heartbeat", "➕ Tambah Device", "✏️ Edit Device", "🗑️ Hapus Device"])
    
    with tab_sim:
        st.caption("Uji perubahan status perangkat secara manual tanpa unit fisik:")
        test_dev = st.selectbox("Pilih Perangkat untuk Ping:", options=[d.get("device_id") for d in devices] if devices else [], key="sel_test_dev")
        if test_dev:
            if st.button(f"📡 Kirim Heartbeat ke {test_dev}", use_container_width=True):
                try:
                    update_device_heartbeat(supabase, test_dev, status="online")
                    st.success(f"Heartbeat berhasil dikirim untuk {test_dev}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal mengirim heartbeat: {str(e)}")

    with tab_add:
        st.caption("Pendaftaran perangkat ESP32-S3 siswa untuk mendapatkan API Key & URL Koneksi:")
        with st.form("form_add_device", clear_on_submit=False):
            col_in1, col_in2 = st.columns(2)
            with col_in1:
                owner_name = st.text_input("Nama Siswa / Mahasiswa:", placeholder="Contoh: Ahmad Zaki / Kelompok 1").strip()
                new_dev_id = st.text_input("Device ID (Opsional, kosongkan untuk otomatis):", placeholder="Contoh: DEV-SISWA-01").strip().upper()
            with col_in2:
                new_dev_name = st.text_input("Nama Perangkat:", placeholder="Contoh: ESP32 Gerbang Masuk Siswa A").strip()
                dev_type = st.selectbox(
                    "Tipe Perangkat:",
                    options=["multi-sensor", "gate", "parking-slot"],
                    format_func=lambda x: {
                        "multi-sensor": "All-in-One (Ultrasonik + IR + RFID)",
                        "gate": "Gerbang Masuk (RFID + Servo)",
                        "parking-slot": "Slot Parkir (IR ADC Sensor)"
                    }.get(x, x)
                )

            submit_dev = st.form_submit_button("🚀 Daftarkan Device & Dapatkan API Key", use_container_width=True)
            
            if submit_dev:
                if not owner_name:
                    st.error("Nama siswa / pemilik tidak boleh kosong!")
                elif not new_dev_name:
                    st.error("Nama perangkat tidak boleh kosong!")
                else:
                    try:
                        registered = register_student_device(
                            supabase,
                            owner_name=owner_name,
                            device_name=new_dev_name,
                            device_type=dev_type,
                            device_id=new_dev_id if new_dev_id else None
                        )
                        st.session_state["recent_registered_device"] = registered
                        st.success(f"Perangkat {registered.get('device_id')} berhasil didaftarkan!")
                    except Exception as e:
                        st.error(f"Gagal mendaftarkan perangkat: {str(e)}")

        # Display Credentials if a device was recently registered
        recent = st.session_state.get("recent_registered_device")
        if recent:
            st.markdown("---")
            st.success("🎉 **Kredensial Koneksi IoT Perangkat Anda**")
            
            supa_url = os.getenv("SUPABASE_URL", "https://wxowndnwwzryzdkdkkqx.supabase.co")
            supa_key = os.getenv("SUPABASE_KEY", "sb_publishable_...")
            dev_id_val = recent.get("device_id", "-")
            api_key_val = recent.get("api_key", "-")
            
            st.markdown(
                f"""
                <div style="background: rgba(148, 163, 184, 0.08); border: 1px solid rgba(148, 163, 184, 0.25); border-radius: 12px; padding: 18px 20px; margin-bottom: 16px;">
                    <div style="font-size: 1rem; font-weight: 700; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                        <span>📋</span> <span>Kredensial Siap Pakai:</span>
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; padding-bottom: 8px; border-bottom: 1px solid rgba(148, 163, 184, 0.15);">
                            <span style="font-weight: 600; font-size: 0.88rem; opacity: 0.85;">Device ID:</span>
                            <code style="font-size: 0.95rem; font-weight: 700; padding: 3px 8px; border-radius: 6px;">{dev_id_val}</code>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; padding-bottom: 8px; border-bottom: 1px solid rgba(148, 163, 184, 0.15);">
                            <span style="font-weight: 600; font-size: 0.88rem; opacity: 0.85;">API Key Khusus:</span>
                            <code style="font-size: 0.95rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; word-break: break-all;">{api_key_val}</code>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
                            <span style="font-weight: 600; font-size: 0.88rem; opacity: 0.85;">REST Endpoint URL:</span>
                            <code style="font-size: 0.85rem; padding: 3px 8px; border-radius: 6px; word-break: break-all;">{supa_url}/rest/v1/iot_devices</code>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            
            with st.expander("📄 Tampilkan Template Kode Firmware C++ (ESP32 Arduino IDE)", expanded=False):
                cpp_code = generate_esp32_code_snippet(
                    device_id=dev_id_val,
                    api_key=api_key_val,
                    supabase_url=supa_url,
                    supabase_anon_key=supa_key
                )
                st.code(cpp_code, language="cpp")
                st.info("Salin kode di atas ke Arduino IDE Anda, ubah konfigurasi WiFi SSID & Password, lalu upload ke board ESP32-S3.")

    with tab_edit:
        st.caption("Perbarui nama, pemilik, atau tipe perangkat IoT terdaftar:")
        dev_ids_list = [d.get("device_id") for d in devices if d.get("device_id")]
        if not dev_ids_list:
            st.info("Belum ada perangkat terdaftar untuk diedit.")
        else:
            selected_edit_id = st.selectbox("Pilih Perangkat yang Ingin Diedit:", options=dev_ids_list, key="sel_dev_to_edit_gen")
            curr_dev_to_edit = next((d for d in devices if d.get("device_id") == selected_edit_id), {})
            with st.form("form_edit_device_general"):
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    e_name = st.text_input("Nama Perangkat:", value=curr_dev_to_edit.get("device_name", "")).strip()
                    e_owner = st.text_input("Nama Siswa / Pemilik:", value=curr_dev_to_edit.get("owner_name", "")).strip()
                with col_e2:
                    curr_t = curr_dev_to_edit.get("device_type", "multi-sensor")
                    t_opts = ["multi-sensor", "gate", "parking-slot"]
                    def_t_idx = t_opts.index(curr_t) if curr_t in t_opts else 0
                    e_type = st.selectbox(
                        "Tipe Perangkat:",
                        options=t_opts,
                        index=def_t_idx,
                        format_func=lambda x: {
                            "multi-sensor": "All-in-One (Ultrasonik + IR + RFID)",
                            "gate": "Gerbang Masuk (RFID + Servo)",
                            "parking-slot": "Slot Parkir (IR ADC Sensor)"
                        }.get(x, x),
                        key="sel_dtype_general"
                    )
                sub_edit_gen = st.form_submit_button("💾 Simpan Perubahan Perangkat", use_container_width=True)
                if sub_edit_gen:
                    if not e_name or not e_owner:
                        st.error("Nama perangkat dan pemilik tidak boleh kosong!")
                    else:
                        try:
                            update_device(supabase, selected_edit_id, device_name=e_name, owner_name=e_owner, device_type=e_type)
                            st.success(f"Perangkat {selected_edit_id} berhasil diperbarui!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Gagal memperbarui perangkat: {str(e)}")

    with tab_del:
        st.caption("Hapus perangkat IoT terdaftar secara permanen:")
        dev_ids_del_list = [d.get("device_id") for d in devices if d.get("device_id")]
        if not dev_ids_del_list:
            st.info("Belum ada perangkat terdaftar untuk dihapus.")
        else:
            with st.form("form_del_device_general"):
                target_dev_to_del = st.selectbox("Pilih Perangkat yang Ingin Dihapus:", options=dev_ids_del_list, key="sel_dev_to_del_gen")
                confirm_del_general = st.checkbox(f"Saya yakin ingin menghapus perangkat '{target_dev_to_del}' secara permanen.")
                sub_del_gen = st.form_submit_button("🗑️ Hapus Perangkat Permanen", use_container_width=True)
                if sub_del_gen:
                    if not confirm_del_general:
                        st.error("Silakan centang kotak konfirmasi sebelum menghapus.")
                    else:
                        try:
                            delete_device(supabase, target_dev_to_del)
                            st.success(f"Perangkat {target_dev_to_del} berhasil dihapus.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Gagal menghapus perangkat: {str(e)}")


