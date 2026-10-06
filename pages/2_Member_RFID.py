"""
Smart Parking Monitoring & RFID Member System - Member RFID
Page: pages/2_Member_RFID.py

Adheres strictly to DRD Sec 9-13 and TRD Sec 19:
- Two main sections / tabs: [ Registrasi Member ] and [ Daftar Member ]
- Registrasi Member:
  * Hardware RFID scan workflow from ESP32-S3 (no manual UID typing!)
  * State transitions: IDLE -> WAITING -> DETECTED / ALREADY_REGISTERED
  * UID is strictly READONLY (disabled text input)
  * Duplicate check blocks duplicate registration
  * Member registration form (Name, License Plate, Vehicle Type, Status)
- Daftar Member:
  * st.dataframe with search/filter
  * Action controls: Edit, Aktifkan/Nonaktifkan (toggle), Hapus with confirmation
  * Empty state handling
- Strictly NO manual gate buttons
"""

import random
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
from services.member_service import (
    register_member,
    get_all_members,
    get_member_by_uid,
    is_uid_registered,
    update_member,
    toggle_member_status,
    delete_member,
    get_latest_rfid_scan,
    normalize_rfid_uid,
    set_member_inside_parking,
    reset_all_passback,
)
from services.device_service import (
    set_device_registration_mode,
    get_device_registration_mode,
    get_all_devices,
)

# 1. Page Config
st.set_page_config(
    page_title="Smart Parking - Member RFID",
    page_icon="💳",
    layout="wide",
)

# 2. Setup Auto-Refresh (conditional or 4s)
setup_auto_refresh(interval_ms=4000, key="rfid_autorefresh")

# 3. Retrieve Supabase Client
supabase = get_app_supabase()

# 4. Authentication Check (Admin Only)
user = require_auth(supabase, allowed_roles=["admin"], current_page_name="2_Member_RFID.py")

# 5. Sidebar Branding
render_sidebar_branding(supabase=supabase)

# 5. Header
st.title("💳 Manajemen Member RFID")
st.caption("Pendaftaran Kartu RFID Otomatis & Pengelolaan Data Anggota")
st.markdown("---")

# 6. Session State Initialization
if "rfid_scan_step" not in st.session_state:
    st.session_state["rfid_scan_step"] = "IDLE"  # IDLE, WAITING, DETECTED, ALREADY_REGISTERED
if "baseline_scan_id" not in st.session_state:
    st.session_state["baseline_scan_id"] = None
if "detected_uid" not in st.session_state:
    st.session_state["detected_uid"] = None
if "detected_device" not in st.session_state:
    st.session_state["detected_device"] = None
if "detected_time" not in st.session_state:
    st.session_state["detected_time"] = None
if "target_rfid_device" not in st.session_state:
    st.session_state["target_rfid_device"] = "GATE-01"
if "scan_start_timestamp" not in st.session_state:
    st.session_state["scan_start_timestamp"] = 0

# 7. Navigation Tabs
tab_registrasi, tab_daftar = st.tabs(["📝 Registrasi Member", "📋 Daftar Member"])

# ==============================================================================
# TAB 1: REGISTRASI MEMBER
# ==============================================================================
with tab_registrasi:
    st.subheader("Pendaftaran Member Baru Berbasis Scan RFID")
    st.markdown(
        """
        <p style="color: #64748B; font-size: 0.9rem;">
            Pendaftaran member <b>wajib</b> membaca UID secara otomatis melalui sensor RFID RC522 
            pada ESP32. UID tidak dapat diketik manual untuk memastikan validitas kartu fisik.
        </p>
        """,
        unsafe_allow_html=True,
    )

    col_workflow, col_form = st.columns([1, 1], gap="large")

    with col_workflow:
        st.markdown("#### 1. Pembacaan Kartu RFID")

        # Device selection for RFID scanning
        all_devs = get_all_devices(supabase)
        dev_id_list = [d.get("device_id") for d in all_devs if d.get("device_id")]
        if "GATE-01" not in dev_id_list:
            dev_id_list.insert(0, "GATE-01")

        curr_dev = st.session_state.get("target_rfid_device", "GATE-01")
        dev_idx = dev_id_list.index(curr_dev) if curr_dev in dev_id_list else 0

        selected_dev = st.selectbox(
            "Pilih Perangkat Input RFID (ESP32):",
            options=dev_id_list,
            index=dev_idx,
            key="select_reg_target_device",
            help="Pilih alat fisik ESP32 yang akan digunakan membaca kartu baru (misal GATE-01 atau perangkat siswa)."
        )
        st.session_state["target_rfid_device"] = selected_dev

        current_step = st.session_state["rfid_scan_step"]

        # Action Buttons row
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("📡 MULAI SCAN RFID", use_container_width=True, type="primary"):
                with st.spinner(f"⏳ Mengirim sinyal pendaftaran ke {selected_dev}..."):
                    set_device_registration_mode(supabase, selected_dev, enable=True)
                    latest = get_latest_rfid_scan(supabase, device_id=selected_dev)
                    st.session_state["baseline_scan_id"] = latest.get("id") if latest else 0
                    st.session_state["scan_start_timestamp"] = datetime.now(timezone.utc).timestamp()
                    st.session_state["rfid_scan_step"] = "WAITING"
                    st.session_state["detected_uid"] = None
                    st.rerun()

        with btn_col2:
            if st.button("🔄 REFRESH SCAN TERBARU", use_container_width=True):
                with st.spinner("⏳ Memeriksa data scan kartu terbaru..."):
                    latest = get_latest_rfid_scan(supabase, device_id=selected_dev)
                    if latest:
                        uid = normalize_rfid_uid(latest.get("uid", ""))
                        st.session_state["detected_uid"] = uid
                        st.session_state["detected_device"] = latest.get("device_id", selected_dev)
                        st.session_state["detected_time"] = latest.get("created_at")
                        if is_uid_registered(supabase, uid):
                            st.session_state["rfid_scan_step"] = "ALREADY_REGISTERED"
                        else:
                            st.session_state["rfid_scan_step"] = "DETECTED"
                    st.rerun()

        # Realtime Fragment Listener when in WAITING state
        if current_step == "WAITING":
            @realtime_fragment(run_every="2s")
            def render_rfid_scan_listener(target_device: str):
                start_t = st.session_state.get("scan_start_timestamp", 0)
                now_t = datetime.now(timezone.utc).timestamp()
                elapsed = now_t - start_t
                remaining = max(0, int(60 - elapsed))

                if elapsed > 60:
                    set_device_registration_mode(supabase, target_device, enable=False)
                    st.session_state["rfid_scan_step"] = "IDLE"
                    st.warning("⏱️ **Waktu scan habis (60 detik).** Mode registrasi dinonaktifkan otomatis.")
                    st.rerun()
                    return

                latest = get_latest_rfid_scan(supabase, device_id=target_device)
                baseline = st.session_state.get("baseline_scan_id", 0)
                if latest and latest.get("id", 0) != baseline:
                    uid = normalize_rfid_uid(latest.get("uid", ""))
                    st.session_state["detected_uid"] = uid
                    st.session_state["detected_device"] = latest.get("device_id", target_device)
                    st.session_state["detected_time"] = latest.get("created_at")
                    set_device_registration_mode(supabase, target_device, enable=False)
                    if is_uid_registered(supabase, uid):
                        st.session_state["rfid_scan_step"] = "ALREADY_REGISTERED"
                    else:
                        st.session_state["rfid_scan_step"] = "DETECTED"
                    st.rerun()

                st.warning(
                    f"📡 **Mode Registrasi Aktif pada {target_device}!**\n\n"
                    f"• Layar LCD alat sedang menampilkan `*REGISTRASI RFID* TEMPEL KARTU...`.\n"
                    f"• Silakan tempelkan kartu RFID baru pada reader RC522 alat sekarang.\n"
                    f"• *(Palang gerbang tidak akan membuka saat proses registrasi)*.\n"
                    f"• Sisa waktu: **{remaining} detik**."
                )

            render_rfid_scan_listener(selected_dev)

            if st.button("❌ Batalkan Scan", key="btn_cancel_scan", use_container_width=True):
                set_device_registration_mode(supabase, selected_dev, enable=False)
                st.session_state["rfid_scan_step"] = "IDLE"
                st.rerun()

            # Simulation helper for rapid testing without physical ESP32 hardware
            with st.expander("🛠️ Simulasi Kartu RFID (Demo / Testing)"):
                st.caption(f"Gunakan tombol ini untuk menyimulasikan tap kartu pada `{selected_dev}`:")
                sim_col1, sim_col2 = st.columns(2)
                with sim_col1:
                    if st.button("Simulasikan Kartu Baru"):
                        random_hex = "".join(random.choices("0123456789ABCDEF", k=8))
                        supabase.table("rfid_scans").insert({
                            "uid": random_hex,
                            "device_id": selected_dev,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }).execute()
                        st.session_state["detected_uid"] = random_hex
                        st.session_state["detected_device"] = selected_dev
                        st.session_state["detected_time"] = datetime.now(timezone.utc).isoformat()
                        set_device_registration_mode(supabase, selected_dev, enable=False)
                        st.session_state["rfid_scan_step"] = "DETECTED"
                        st.rerun()
                with sim_col2:
                    if st.button("Simulasikan Kartu Terdaftar"):
                        existing_uid = "A3F21C12"
                        supabase.table("rfid_scans").insert({
                            "uid": existing_uid,
                            "device_id": selected_dev,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }).execute()
                        st.session_state["detected_uid"] = existing_uid
                        st.session_state["detected_device"] = selected_dev
                        st.session_state["detected_time"] = datetime.now(timezone.utc).isoformat()
                        set_device_registration_mode(supabase, selected_dev, enable=False)
                        st.session_state["rfid_scan_step"] = "ALREADY_REGISTERED"
                        st.rerun()

        elif st.session_state["rfid_scan_step"] == "IDLE":
            st.info(f"ℹ️ **Status:** Belum ada kartu dibaca.\n\nPilih alat ESP32 dan klik **[ MULAI SCAN RFID ]** untuk mengaktifkan mode registrasi.")

        elif st.session_state["rfid_scan_step"] == "ALREADY_REGISTERED":
            uid = st.session_state.get("detected_uid", "")
            existing = get_member_by_uid(supabase, uid)
            existing_name = existing.get("member_name", "N/A") if existing else "N/A"
            existing_plate = existing.get("license_plate", "N/A") if existing else "N/A"

            st.error(
                f"🚫 **RFID SUDAH TERDAFTAR**\n\n"
                f"• **UID:** `{uid}`\n"
                f"• **Member:** {existing_name}\n"
                f"• **Nomor Polisi:** {existing_plate}\n\n"
                "Sistem menolak pendaftaran kartu ganda. Silakan gunakan kartu RFID lain."
            )
            if st.button("🔄 Scan Kartu Lain", key="btn_rescan_dup", use_container_width=True):
                st.session_state["rfid_scan_step"] = "WAITING"
                st.session_state["scan_start_timestamp"] = datetime.now(timezone.utc).timestamp()
                set_device_registration_mode(supabase, selected_dev, enable=True)
                st.rerun()

        elif st.session_state["rfid_scan_step"] == "DETECTED":
            uid = st.session_state.get("detected_uid", "")
            dev = st.session_state.get("detected_device", selected_dev)
            sc_time = format_timestamp(st.session_state.get("detected_time"))

            st.success(
                f"✅ **RFID TERDETEKSI**\n\n"
                f"• **UID:** `{uid}` (Siap Didaftarkan)\n"
                f"• **Device:** `{dev}`\n"
                f"• **Waktu:** `{sc_time}`"
            )
            if st.button("🔄 Scan Ulang / Ganti Kartu", key="btn_rescan_detected", use_container_width=True):
                st.session_state["rfid_scan_step"] = "WAITING"
                st.session_state["scan_start_timestamp"] = datetime.now(timezone.utc).timestamp()
                set_device_registration_mode(supabase, selected_dev, enable=True)
                st.rerun()

    # Column 2: Member Data Form (Only active when DETECTED)
    with col_form:
        st.markdown("#### 2. Formulir Data Member")

        if st.session_state["rfid_scan_step"] == "DETECTED":
            detected_uid = st.session_state.get("detected_uid", "")

            # Form fields
            st.text_input(
                "UID Kartu RFID (Read-Only)",
                value=detected_uid,
                disabled=True,
                help="UID didapatkan langsung dari sensor RFID ESP32-S3 dan tidak dapat diubah secara manual.",
            )

            with st.form("form_register_member", clear_on_submit=True):
                member_name = st.text_input("Nama Lengkap Member*", placeholder="Contoh: Rahmat Hidayat")
                license_plate = st.text_input("Nomor Polisi (Plat Kendaraan)*", placeholder="Contoh: BG 1234 RH")

                veh_col, stat_col = st.columns(2)
                with veh_col:
                    vehicle_option = st.selectbox(
                        "Jenis Kendaraan",
                        ["Mobil", "Motor", "Truk / Lainnya"],
                    )
                with stat_col:
                    status_option = st.selectbox(
                        "Status Awal",
                        ["Aktif", "Nonaktif"],
                    )

                submitted = st.form_submit_button("💾 SIMPAN MEMBER", use_container_width=True, type="primary")

                if submitted:
                    if not member_name.strip() or not license_plate.strip():
                        st.error("Nama member dan nomor polisi wajib diisi!")
                    else:
                        # Map choices to schema values
                        veh_map = {"Mobil": "car", "Motor": "motorcycle", "Truk / Lainnya": "other"}
                        stat_map = {"Aktif": "active", "Nonaktif": "inactive"}

                        try:
                            new_member = register_member(
                                supabase,
                                rfid_uid=detected_uid,
                                member_name=member_name.strip(),
                                license_plate=license_plate.strip().upper(),
                                vehicle_type=veh_map.get(vehicle_option, "car"),
                                status=stat_map.get(status_option, "active"),
                            )

                            st.session_state["rfid_scan_step"] = "IDLE"
                            st.session_state["detected_uid"] = None
                            st.success(
                                f"🎉 **Member Berhasil Didaftarkan!**\n\n"
                                f"• **UID:** `{detected_uid}`\n"
                                f"• **Nama:** {member_name}\n"
                                f"• **Plat:** {license_plate.upper()}"
                            )
                        except Exception as e:
                            st.error(f"Gagal menyimpan member: {str(e)}")

        elif st.session_state["rfid_scan_step"] == "ALREADY_REGISTERED":
            st.info("Pendaftaran diblokir karena kartu RFID ini sudah memiliki pemilik terdaftar.")
        else:
            st.markdown(
                """
                <div style="border: 2px dashed #CBD5E1; border-radius: 10px; padding: 40px; text-align: center; color: #94A3B8;">
                    <div style="font-size: 2rem; margin-bottom: 8px;">💳</div>
                    <div>Formulir pendaftaran akan aktif otomatis setelah kartu RFID dibaca oleh scanner.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# ==============================================================================
# TAB 2: DAFTAR MEMBER
# ==============================================================================
with tab_daftar:
    st.subheader("Daftar Anggota RFID Terdaftar")

    with system_loading(
        message="Memuat Data Member RFID...",
        subtext="Mengambil daftar kartu RFID & status keanggotaan...",
        key="rfid_member_list",
        only_initial=True,
    ):
        all_members = get_all_members(supabase)

    if not all_members:
        st.info("Belum ada member RFID terdaftar.")
    else:
        # Search & Filter
        search_query = st.text_input("🔍 Cari Member (Nama, Nomor Polisi, atau UID)...", "").strip().lower()

        filtered_members = [
            m for m in all_members
            if (
                search_query in m.get("member_name", "").lower() or
                search_query in m.get("license_plate", "").lower() or
                search_query in m.get("rfid_uid", "").lower()
            )
        ]

        st.caption(f"Menampilkan {len(filtered_members)} dari {len(all_members)} member terdaftar.")

        # Dataframe View
        df_display = []
        for m in filtered_members:
            veh_disp = "Mobil" if m.get("vehicle_type") == "car" else ("Motor" if m.get("vehicle_type") == "motorcycle" else "Lainnya")
            stat_disp = "Aktif" if m.get("status") == "active" else "Nonaktif"
            pos_disp = "🚗 Di Dalam" if m.get("inside_parking") else "🟢 Di Luar"
            df_display.append({
                "ID": m.get("id"),
                "UID": m.get("rfid_uid"),
                "Nama Member": m.get("member_name"),
                "Nomor Polisi": m.get("license_plate"),
                "Kendaraan": veh_disp,
                "Status": stat_disp,
                "Posisi (Anti-Passback)": pos_disp,
                "Terdaftar Pada": format_timestamp(m.get("created_at")),
            })

        st.dataframe(
            pd.DataFrame(df_display),
            width="stretch",
            hide_index=True,
        )

        st.markdown("---")

        # Actions Section (DRD Sec 13)
        st.markdown("#### Kelola Member Terpilih")

        member_options = {
            f"{m.get('member_name')} ({m.get('license_plate')}) - UID: {m.get('rfid_uid')}": m
            for m in all_members
        }

        selected_label = st.selectbox(
            "Pilih Member untuk Dikelola:",
            options=list(member_options.keys()),
        )

        if selected_label:
            selected_member = member_options[selected_label]
            m_id = selected_member.get("id")
            m_uid = selected_member.get("rfid_uid")
            m_name = selected_member.get("member_name")
            m_plate = selected_member.get("license_plate")
            m_veh = selected_member.get("vehicle_type", "car")
            m_stat = selected_member.get("status", "active")

            act_col1, act_col2 = st.columns([1, 1], gap="medium")

            with act_col1:
                st.markdown("**Perbarui Data Member (Edit)**")
                with st.form(f"edit_member_form_{m_id}"):
                    edit_name = st.text_input("Nama Member", value=m_name)
                    edit_plate = st.text_input("Nomor Polisi", value=m_plate)

                    veh_index = 0 if m_veh == "car" else (1 if m_veh == "motorcycle" else 2)
                    edit_veh = st.selectbox("Jenis Kendaraan", ["Mobil", "Motor", "Truk / Lainnya"], index=veh_index)

                    stat_index = 0 if m_stat == "active" else 1
                    edit_stat = st.selectbox("Status", ["Aktif", "Nonaktif"], index=stat_index)

                    save_edit = st.form_submit_button("Simpan Perubahan Data", use_container_width=True)

                    if save_edit:
                        veh_map = {"Mobil": "car", "Motor": "motorcycle", "Truk / Lainnya": "other"}
                        stat_map = {"Aktif": "active", "Nonaktif": "inactive"}
                        try:
                            update_member(
                                supabase,
                                member_id=m_id,
                                member_name=edit_name.strip(),
                                license_plate=edit_plate.strip().upper(),
                                vehicle_type=veh_map.get(edit_veh, "car"),
                                status=stat_map.get(edit_stat, "active"),
                            )
                            st.success("Data member berhasil diperbarui!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Gagal memperbarui: {str(e)}")

            with act_col2:
                st.markdown("**Aksi Cepat Status, Anti-Passback & Hapus**")

                toggle_label = "🔴 Nonaktifkan Member" if m_stat == "active" else "🟢 Aktifkan Member"
                if st.button(toggle_label, use_container_width=True):
                    try:
                        toggle_member_status(supabase, m_id, m_stat)
                        st.success(f"Status member berhasil diubah menjadi {'Nonaktif' if m_stat == 'active' else 'Aktif'}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal mengubah status: {str(e)}")

                m_inside = bool(selected_member.get("inside_parking"))
                passback_btn_label = "🟢 Ubah Posisi ke Luar (Reset Passback)" if m_inside else "🚗 Ubah Posisi ke Dalam"
                if st.button(passback_btn_label, use_container_width=True, key=f"btn_passback_{m_id}"):
                    try:
                        set_member_inside_parking(supabase, m_id, not m_inside)
                        st.success(f"Posisi {m_name} berhasil diubah menjadi {'Luar' if m_inside else 'Dalam'}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal mengubah posisi: {str(e)}")

                st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

                st.markdown("**Hapus Member**")
                confirm_delete = st.checkbox(f"Saya yakin ingin menghapus data {m_name}", key=f"del_chk_{m_id}")
                if st.button("🗑️ Hapus Member Secara Permanen", type="secondary", use_container_width=True, disabled=not confirm_delete):
                    try:
                        delete_member(supabase, m_id)
                        st.success("Member berhasil dihapus dari sistem.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal menghapus member: {str(e)}")

        st.markdown("---")
        st.markdown("##### 🚨 Pengaturan Darurat Anti-Passback")
        st.caption("Jika sistem sempat offline dan status posisi member tidak sinkron, Anda dapat mereset seluruh member menjadi di luar area parkir:")
        if st.button("🔄 Reset Semua Posisi Member ke Luar (Emergency Passback Reset)", type="secondary"):
            try:
                reset_all_passback(supabase)
                st.success("Seluruh posisi member berhasil direset menjadi 'Di Luar'!")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal mereset passback: {str(e)}")

