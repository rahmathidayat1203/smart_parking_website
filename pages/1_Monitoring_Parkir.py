"""
Smart Parking Monitoring & RFID Member System - Monitoring Parkir
Page: pages/1_Monitoring_Parkir.py

Adheres strictly to DRD Sec 8 & 19 and TRD Sec 20:
- Summary metrics (Total, Kosong, Terisi)
- Offline warning banner if IoT device is offline
- Slot Grid (P01-P04) with clear status-oriented visual cards
- Detailed slot information: status, IR value, updated timestamp
- Empty state handling if no slots available
- Auto-refresh enabled (4s)
- Strictly NO manual gate buttons
"""

import streamlit as st

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
from services.parking_service import (
    get_parking_slots,
    calculate_slot_metrics,
    check_slot_offline,
    create_parking_slot,
    update_parking_slot,
    delete_parking_slot,
)
from services.device_service import (
    get_all_devices,
    get_device_status,
    is_device_online,
)
from services.audit_service import (
    get_audit_logs,
    delete_audit_log,
    clear_all_audit_logs,
)

# 1. Page Config
st.set_page_config(
    page_title="Smart Parking - Monitoring Parkir",
    page_icon="🅿️",
    layout="wide",
)

# 2. Setup Auto-Refresh
setup_auto_refresh(interval_ms=4000, key="parking_autorefresh")

# 3. Retrieve Supabase Client
supabase = get_app_supabase()

# 4. Authentication Check (Accessible by both Admin and Student)
user = require_auth(supabase, allowed_roles=["admin", "student"], current_page_name="1_Monitoring_Parkir.py")

# 5. Sidebar Branding
render_sidebar_branding(supabase=supabase)

# 5. Header
st.title("🅿️ Monitoring Parkir")
st.caption("Visualisasi dan Pemantauan Kondisi Slot Parkir Real-Time")
st.markdown("---")

@realtime_fragment(run_every="3s")
def render_live_parking_monitoring():
    # 6. Fetch Devices & Slots Data
    import os

    with system_loading(
        message="Memuat Data Slot Parkir...",
        subtext="Menyinkronkan status sensor IR (Active-LOW) & jarak ultrasonik...",
        key="parking_monitoring",
        only_initial=True,
    ):
        primary_device_id = os.getenv("DEVICE_ID", "GATE-01")
        primary_device = get_device_status(supabase, primary_device_id)
        primary_online = is_device_online(primary_device.get("last_seen") if primary_device else None)

        parking_device = get_device_status(supabase, "PARKING-01")
        has_separate_parking = parking_device is not None and parking_device.get("device_id") != primary_device_id
        parking_online = is_device_online(parking_device.get("last_seen") if parking_device else None) if has_separate_parking else primary_online

        slots = get_parking_slots(supabase)
        metrics = calculate_slot_metrics(slots)
        devices = get_all_devices(supabase)

    # 7. Device Offline Warning Banner (DRD Sec 19)
    if not primary_online or (has_separate_parking and not parking_online):
        offline_devs = []
        if not primary_online:
            offline_devs.append(f"{primary_device_id} (ESP32 Master Controller)")
        if has_separate_parking and not parking_online:
            offline_devs.append("PARKING-01 (Sensor Slot)")
        dev_str = ", ".join(offline_devs)

        st.error(
            f"⚠️ **ESP32 OFFLINE ({dev_str})**: Data sensor mungkin tidak diperbarui. "
            "Periksa koneksi WiFi atau daya perangkat."
        )

    # 7.1 Tailgating Incident Security Alert Banner
    recent_tailgate = get_audit_logs(supabase, limit=1, tailgating_only=True)
    if recent_tailgate:
        t_log = recent_tailgate[0]
        st.error(
            f"🚨 **ALARM KEAMANAN: DETEKSI TAILGATING (MOBIL MEMBUNTUTI)!**\n\n"
            f"Terdeteksi kendaraan membuntuti tanpa otorisasi kartu pada `{t_log.get('device_id', 'GATE-01')}`! "
            f"Waktu: {format_timestamp(t_log.get('created_at'))}. "
            f"Kamera gerbang telah merekam insiden ini ke dalam Log Audit Forensik."
        )

    # 8. Student Device Cards (Admin Quick Access to Student Dashboard)
    if user.get("role") == "admin":
        st.subheader("🎓 Perangkat Siswa Terdaftar")
        st.caption("Pilih card perangkat siswa untuk masuk ke Dashboard Siswa, memantau slot parkir mereka, dan mendaftarkan member RFID:")

        student_devices = [d for d in devices if d.get("owner_name") or d.get("device_id", "").startswith("DEV-SISWA")]
        active_count = sum(1 for d in student_devices if is_device_online(d.get("last_seen"), threshold_seconds=30))

        col_h1, col_h2 = st.columns([3, 1])
        with col_h1:
            st.markdown(f"Total **{len(student_devices)}** perangkat siswa terdaftar (**{active_count} Aktif / Online**):")
        with col_h2:
            filter_status = st.selectbox("Filter Status:", options=["Semua Siswa", "Hanya Online", "Hanya Offline"], key="sel_filter_student_status")

        if filter_status == "Hanya Online":
            filtered_student_devs = [d for d in student_devices if is_device_online(d.get("last_seen"), threshold_seconds=30)]
        elif filter_status == "Hanya Offline":
            filtered_student_devs = [d for d in student_devices if not is_device_online(d.get("last_seen"), threshold_seconds=30)]
        else:
            filtered_student_devs = student_devices

        if not filtered_student_devs:
            st.info("💡 Tidak ada perangkat siswa yang sesuai dengan filter.")
        else:
            num_cards = len(filtered_student_devs)
            cols_count = 3 if num_cards >= 3 else (2 if num_cards == 2 else 1)
            row_chunks = [filtered_student_devs[i:i + cols_count] for i in range(0, num_cards, cols_count)]

            for row in row_chunks:
                dev_cols = st.columns(cols_count)
                for idx, dev in enumerate(row):
                    with dev_cols[idx]:
                        d_id = dev.get("device_id", "-")
                        d_name = dev.get("device_name", "ESP32 Node")
                        d_owner = dev.get("owner_name", "Siswa")
                        d_seen = dev.get("last_seen")
                        d_online = is_device_online(d_seen, threshold_seconds=30)
                        d_rel_seen = get_relative_time(d_seen)

                        dev_slots = [s for s in slots if s.get("device_id") == d_id]
                        avail_slots = sum(1 for s in dev_slots if s.get("status") == "available")
                        slot_info = f"🅿️ {avail_slots}/{len(dev_slots)} Slot Kosong" if dev_slots else "🅿️ Belum ada slot terikat"

                        card_border = "#10B981" if d_online else "#EF4444"
                        card_bg = "#F0FDF4" if d_online else "#FEF2F2"
                        status_badge = render_status_badge("ONLINE" if d_online else "OFFLINE")

                        st.markdown(
                            f"""
                            <div style="border: 2px solid {card_border}; background-color: {card_bg};
                                        border-radius: 12px; padding: 18px; margin-bottom: 12px;
                                        box-shadow: 0 2px 4px rgba(0,0,0,0.04);">
                                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                                    <div>
                                        <span style="font-size: 1.15rem; font-weight: 800; color: #0F172A;">👤 {d_owner}</span>
                                        <div style="font-size: 0.85rem; color: #475569;"><b>{d_name}</b></div>
                                    </div>
                                    <div>{status_badge}</div>
                                </div>
                                <div style="font-size: 0.85rem; color: #334155; margin-bottom: 6px;">
                                    <code>{d_id}</code> &bull; <span style="color: #64748B;">{d_rel_seen}</span>
                                </div>
                                <div style="font-size: 0.9rem; font-weight: 600; color: #1E293B;">
                                    {slot_info}
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            f"👉 Masuk ke Dashboard {d_owner}",
                            key=f"btn_nav_dash_{d_id}",
                            use_container_width=True,
                            type="primary" if d_online else "secondary",
                        ):
                            st.session_state["target_student_device_id"] = d_id
                            st.switch_page("pages/5_Dashboard_Siswa.py")

        st.markdown("---")
    elif user.get("role") == "student":
        assigned_id = user.get("device_id")
        if assigned_id:
            st.info(f"🎓 Anda terhubung dengan perangkat **{assigned_id}**. Ingin memantau slot atau mendaftarkan RFID?")
            if st.button("🚀 Buka Dashboard Perangkat Saya", key="btn_student_goto_dash", type="primary"):
                st.session_state["target_student_device_id"] = assigned_id
                st.switch_page("pages/5_Dashboard_Siswa.py")
            st.markdown("---")

    # 9. Summary Metrics (Total, Kosong, Terisi) per DRD Sec 8
    m1, m2, m3 = st.columns(3)

    with m1:
        st.metric(
            label="Total Slot",
            value=metrics["total"],
            help=f"Total slot parkir terpasang ({metrics['total']} Slot)",
        )

    with m2:
        st.metric(
            label="Slot Kosong (Available)",
            value=metrics["available"],
            delta=f"{metrics['available']} Tersedia",
            delta_color="normal",
            help="Jumlah slot kosong yang siap digunakan",
        )

    with m3:
        st.metric(
            label="Slot Terisi (Occupied)",
            value=metrics["occupied"],
            delta=f"-{metrics['occupied']} Terisi" if metrics["occupied"] > 0 else "0",
            delta_color="inverse",
            help="Jumlah slot parkir yang sedang terisi kendaraan",
        )

    st.markdown("---")

    # 10. Parking Slot Grid (Adaptif untuk 3 Slot ESP32 atau Grid)
    device_options = ["Semua Perangkat (Global)"]
    unique_dev_ids = sorted(list(set(s.get("device_id") for s in slots if s.get("device_id"))))
    device_options.extend(unique_dev_ids)

    col_grid_head, col_grid_filter = st.columns([3, 1])
    with col_grid_head:
        st.subheader("Peta Slot Parkir")
    with col_grid_filter:
        chosen_slot_dev = st.selectbox("Filter Perangkat Slot:", options=device_options, key="slot_grid_dev_filter")

    displayed_slots = slots if chosen_slot_dev == "Semua Perangkat (Global)" else [s for s in slots if s.get("device_id") == chosen_slot_dev]

    if not displayed_slots:
        st.info("⏳ **Tidak ada slot parkir yang sesuai dengan filter perangkat terpilih.**")
    else:
        # Jika 3 slot, gunakan 3 kolom sejajar; jika lebih banyak, gunakan 2 kolom per baris
        if len(displayed_slots) <= 3:
            cols = st.columns(len(displayed_slots))
            for idx, slot in enumerate(displayed_slots):
                with cols[idx]:
                    slot_code = slot.get("slot_code", f"Slot {idx+1}")
                    display_code = f"{slot_code} (Slot {idx+1})" if not slot_code.lower().startswith("slot") else slot_code
                    raw_val = slot.get("sensor_value")
                    updated_at_raw = slot.get("updated_at")
                    updated_at_fmt = format_timestamp(updated_at_raw)
                    rel_time = get_relative_time(updated_at_raw)

                    # Offline detection with unified controller
                    slot_dev_id = slot.get("device_id") or primary_device_id
                    dev_for_slot = get_device_status(supabase, slot_dev_id) if slot_dev_id != primary_device_id else primary_device
                    dev_online = is_device_online(dev_for_slot.get("last_seen") if dev_for_slot else None) if dev_for_slot else primary_online
                    is_offline = check_slot_offline(slot) or not dev_online
                    effective_status = "offline" if is_offline else slot.get("status", "available")

                    if effective_status == "available":
                        card_status = "KOSONG"
                        border_color = "#10B981"
                        bg_color = "#F0FDF4"
                        status_text_color = "#047857"
                        accent_icon = "🟢"
                    elif effective_status == "occupied":
                        card_status = "TERISI"
                        border_color = "#EF4444"
                        bg_color = "#FEF2F2"
                        status_text_color = "#B91C1C"
                        accent_icon = "🔴"
                    else:
                        card_status = "OFFLINE"
                        border_color = "#9CA3AF"
                        bg_color = "#F3F4F6"
                        status_text_color = "#4B5563"
                        accent_icon = "⚪"

                    badge = render_status_badge(card_status)
                    if raw_val is None:
                        val_text = "N/A"
                    elif raw_val == 0:
                        val_text = "0 (LOW • Terhalang)"
                    elif raw_val == 1:
                        val_text = "1 (HIGH • Bebas)"
                    else:
                        val_text = f"{raw_val}"

                    st.markdown(
                        f"""
                        <div style="border: 2px solid {border_color}; background-color: {bg_color}; 
                                    border-radius: 14px; padding: 24px; margin-bottom: 20px;
                                    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.06);">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                <span style="font-size: 1.6rem; font-weight: 800; color: #0F172A; letter-spacing: -0.5px;">
                                    {accent_icon} {display_code}
                                </span>
                                <div>{badge}</div>
                            </div>
                            <div style="border-top: 1px solid rgba(0,0,0,0.06); padding-top: 12px; margin-bottom: 10px;">
                                <div style="display: flex; justify-content: space-between; font-size: 1.05rem; margin-bottom: 6px;">
                                    <span style="color: #475569; font-weight: 500;">Status Parkir:</span>
                                    <span style="font-weight: 700; color: {status_text_color};">{card_status}</span>
                                </div>
                                <div style="display: flex; justify-content: space-between; font-size: 1.05rem; margin-bottom: 6px;">
                                    <span style="color: #475569; font-weight: 500;">Nilai Sensor IR:</span>
                                    <span style="font-family: monospace; font-size: 1.05rem; font-weight: 700; color: #1E293B;">
                                        {val_text}
                                    </span>
                                </div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: #64748B;">
                                    <span>Terakhir Diperbarui:</span>
                                    <span>{updated_at_fmt} ({rel_time})</span>
                                </div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        else:
            # Render slots in chunks of 2
            row_chunks = [displayed_slots[i:i + 2] for i in range(0, len(displayed_slots), 2)]
            for row_idx, chunk in enumerate(row_chunks):
                cols = st.columns(2)
                for col_idx, slot in enumerate(chunk):
                    with cols[col_idx]:
                        slot_code = slot.get("slot_code", "P--")
                        raw_val = slot.get("sensor_value")
                        updated_at_raw = slot.get("updated_at")
                        updated_at_fmt = format_timestamp(updated_at_raw)
                        rel_time = get_relative_time(updated_at_raw)

                        slot_dev_id = slot.get("device_id") or primary_device_id
                        dev_for_slot = get_device_status(supabase, slot_dev_id) if slot_dev_id != primary_device_id else primary_device
                        dev_online = is_device_online(dev_for_slot.get("last_seen") if dev_for_slot else None) if dev_for_slot else primary_online
                        is_offline = check_slot_offline(slot) or not dev_online
                        effective_status = "offline" if is_offline else slot.get("status", "available")

                        if effective_status == "available":
                            card_status = "KOSONG"
                            border_color = "#10B981"
                            bg_color = "#F0FDF4"
                            status_text_color = "#047857"
                            accent_icon = "🟢"
                        elif effective_status == "occupied":
                            card_status = "TERISI"
                            border_color = "#EF4444"
                            bg_color = "#FEF2F2"
                            status_text_color = "#B91C1C"
                            accent_icon = "🔴"
                        else:
                            card_status = "OFFLINE"
                            border_color = "#9CA3AF"
                            bg_color = "#F3F4F6"
                            status_text_color = "#4B5563"
                            accent_icon = "⚪"

                        badge = render_status_badge(card_status)
                        if raw_val is None:
                            val_text = "N/A"
                        elif raw_val == 0:
                            val_text = "0 (LOW • Terhalang)"
                        elif raw_val == 1:
                            val_text = "1 (HIGH • Bebas)"
                        else:
                            val_text = f"{raw_val}"

                        st.markdown(
                            f"""
                            <div style="border: 2px solid {border_color}; background-color: {bg_color}; 
                                        border-radius: 14px; padding: 24px; margin-bottom: 20px;
                                        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.06);">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                    <span style="font-size: 1.8rem; font-weight: 800; color: #0F172A; letter-spacing: -0.5px;">
                                        {accent_icon} {slot_code}
                                    </span>
                                    <div>{badge}</div>
                                </div>
                                <div style="border-top: 1px solid rgba(0,0,0,0.06); padding-top: 12px; margin-bottom: 10px;">
                                    <div style="display: flex; justify-content: space-between; font-size: 1.05rem; margin-bottom: 6px;">
                                        <span style="color: #475569; font-weight: 500;">Status Parkir:</span>
                                        <span style="font-weight: 700; color: {status_text_color};">{card_status}</span>
                                    </div>
                                    <div style="display: flex; justify-content: space-between; font-size: 1.05rem; margin-bottom: 6px;">
                                        <span style="color: #475569; font-weight: 500;">Nilai Sensor IR:</span>
                                        <span style="font-family: monospace; font-size: 1.05rem; font-weight: 700; color: #1E293B;">
                                            {val_text}
                                        </span>
                                    </div>
                                    <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: #64748B;">
                                        <span>Terakhir Diperbarui:</span>
                                        <span>{updated_at_fmt} ({rel_time})</span>
                                    </div>
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

    # 10. Information Guide
    with st.expander("ℹ️ Keterangan Indikator & Ambang Batas Sensor"):
        st.markdown(
            """
            - **KOSONG (Hijau)**: Sensor IR membaca logika **HIGH (1)** (tidak ada halangan mobil pada slot).
            - **TERISI (Merah)**: Sensor IR membaca logika **LOW (0)** (modul Active-LOW mendeteksi pantulan kendaraan di slot).
            - **OFFLINE (Abu-abu)**: Tidak ada pembaruan data sensor dalam 30 detik terakhir atau ESP32 terputus dari WiFi.
            """
        )

    # 11. Log Audit Forensik & Rekaman Kamera Gerbang
    st.markdown("---")
    st.subheader("🚨 Log Audit Forensik & Rekaman Kamera Gerbang")
    st.caption("Pencatatan visual insiden akses gerbang, verifikasi Anti-Passback, dan deteksi kendaraan membuntuti (Tailgating)")

    audit_logs = get_audit_logs(supabase, limit=6)
    if not audit_logs:
        st.info("Belum ada catatan log audit forensik gerbang.")
    else:
        cols = st.columns(min(len(audit_logs), 3))
        for idx, log in enumerate(audit_logs[:6]):
            col = cols[idx % 3]
            with col:
                evt = log.get("event_type", "unknown")
                is_warn = "violation" in evt or "tailgating" in evt or "unauthorized" in evt
                border = "#EF4444" if is_warn else "#10B981"
                title = "🚨 " + evt.replace("_", " ").upper() if is_warn else "✅ " + evt.replace("_", " ").upper()

                photo_url = log.get("photo_url")
                if photo_url:
                    st.image(photo_url, use_column_width=True)

                st.markdown(
                    f"""
                    <div style="border-left: 4px solid {border}; padding-left: 10px; margin-bottom: 15px;">
                        <div style="font-weight: bold; font-size: 0.95rem; color: {'#DC2626' if is_warn else '#059669'};">{title}</div>
                        <div style="font-size: 0.85rem; color: #334155;"><b>Member:</b> {log.get('member_name') or '-'} ({log.get('license_plate') or '-'})</div>
                        <div style="font-size: 0.85rem; color: #475569;"><b>Device:</b> {log.get('device_id') or '-'} | <b>UID:</b> {log.get('rfid_uid') or '-'}</div>
                        <div style="font-size: 0.8rem; color: #64748B;">{format_timestamp(log.get('created_at'))}</div>
                        <div style="font-size: 0.8rem; color: #64748B; margin-top: 4px;"><i>{log.get('details') or ''}</i></div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )



# Jalankan fragment live monitoring parkir
render_live_parking_monitoring()

# 12. Slot Parkir & Audit Log Management (Admin / Operator)
if user.get("role") == "admin":
    st.markdown("---")
    with st.expander("🛠️ Manajemen Slot Parkir (Tambah, Edit & Hapus Slot)", expanded=False):
        tab_slot_add, tab_slot_edit, tab_slot_del = st.tabs([
            "➕ Tambah Slot Parkir",
            "✏️ Edit Slot Parkir",
            "🗑️ Hapus Slot Parkir"
        ])

        all_current_slots = get_parking_slots(supabase)
        all_devs = get_all_devices(supabase)
        dev_id_options = ["(Tidak Terikat)"] + [d.get("device_id") for d in all_devs if d.get("device_id")]

        with tab_slot_add:
            st.caption("Tambahkan slot parkir baru ke dalam sistem:")
            with st.form("form_add_slot"):
                col_as1, col_as2 = st.columns(2)
                with col_as1:
                    new_scode = st.text_input("Kode Slot Parkir:", placeholder="Contoh: P05").strip().upper()
                with col_as2:
                    new_sdev = st.selectbox("Asosiasi Perangkat:", options=dev_id_options)
                sub_add_slot = st.form_submit_button("➕ Tambah Slot Baru", use_container_width=True)
                if sub_add_slot:
                    if not new_scode:
                        st.error("Kode slot tidak boleh kosong!")
                    else:
                        try:
                            assigned = None if new_sdev == "(Tidak Terikat)" else new_sdev
                            create_parking_slot(supabase, slot_code=new_scode, device_id=assigned)
                            st.success(f"Slot parkir {new_scode} berhasil ditambahkan!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Gagal menambahkan slot: {str(e)}")

        with tab_slot_edit:
            st.caption("Ubah kode slot, status parkir manual, atau asosiasi perangkat IoT:")
            if not all_current_slots:
                st.info("Belum ada slot parkir terdaftar.")
            else:
                slot_code_list = [s.get("slot_code") for s in all_current_slots]
                target_slot_to_edit = st.selectbox("Pilih Slot yang Ingin Diedit:", options=slot_code_list, key="sel_slot_edit")
                curr_sl_data = next((s for s in all_current_slots if s.get("slot_code") == target_slot_to_edit), {})
                with st.form("form_edit_slot"):
                    col_es1, col_es2, col_es3 = st.columns(3)
                    with col_es1:
                        new_edit_code = st.text_input("Kode Slot:", value=curr_sl_data.get("slot_code", "")).strip().upper()
                    with col_es2:
                        curr_status = curr_sl_data.get("status", "available")
                        status_opts = ["available", "occupied", "offline"]
                        def_stat_idx = status_opts.index(curr_status) if curr_status in status_opts else 0
                        new_edit_status = st.selectbox(
                            "Status Slot:",
                            options=status_opts,
                            index=def_stat_idx,
                            format_func=lambda x: {"available": "KOSONG (Available)", "occupied": "TERISI (Occupied)", "offline": "OFFLINE"}.get(x, x),
                            key="sel_stat_slot"
                        )
                    with col_es3:
                        curr_sdev = curr_sl_data.get("device_id") or ""
                        def_dev_idx = dev_id_options.index(curr_sdev) if curr_sdev in dev_id_options else 0
                        new_edit_dev = st.selectbox("Perangkat Terkait:", options=dev_id_options, index=def_dev_idx, key="sel_sdev_edit")

                    sub_edit_slot = st.form_submit_button("💾 Simpan Perubahan Slot", use_container_width=True)
                    if sub_edit_slot:
                        if not new_edit_code:
                            st.error("Kode slot tidak boleh kosong!")
                        else:
                            try:
                                assigned = None if new_edit_dev == "(Tidak Terikat)" else new_edit_dev
                                update_parking_slot(
                                    supabase,
                                    target_slot_to_edit,
                                    new_slot_code=new_edit_code if new_edit_code != target_slot_to_edit else None,
                                    status=new_edit_status,
                                    device_id=assigned
                                )
                                st.success(f"Slot {target_slot_to_edit} berhasil diperbarui!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal memperbarui slot: {str(e)}")

        with tab_slot_del:
            st.caption("Hapus slot parkir dari sistem:")
            if not all_current_slots:
                st.info("Belum ada slot parkir terdaftar.")
            else:
                with st.form("form_del_slot"):
                    target_slot_del = st.selectbox("Pilih Slot yang Ingin Dihapus:", options=[s.get("slot_code") for s in all_current_slots], key="sel_slot_del")
                    confirm_del_slot = st.checkbox(f"Saya yakin ingin menghapus slot '{target_slot_del}' secara permanen.")
                    sub_del_slot = st.form_submit_button("🗑️ Hapus Slot Permanen", use_container_width=True)
                    if sub_del_slot:
                        if not confirm_del_slot:
                            st.error("Silakan centang kotak konfirmasi sebelum menghapus.")
                        else:
                            try:
                                delete_parking_slot(supabase, target_slot_del)
                                st.success(f"Slot {target_slot_del} berhasil dihapus.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal menghapus slot: {str(e)}")

    with st.expander("🧹 Pembersihan Log Audit Forensik", expanded=False):
        st.caption("Kelola atau bersihkan catatan log audit forensik keamanan gerbang:")
        col_lg1, col_lg2 = st.columns(2)
        with col_lg1:
            all_audits = get_audit_logs(supabase, limit=50)
            if all_audits:
                with st.form("form_del_single_audit"):
                    log_opts = {f"#{l.get('id')} - {l.get('event_type')} ({l.get('rfid_uid', '-')})": l.get('id') for l in all_audits if l.get('id')}
                    sel_log_label = st.selectbox("Pilih Log Audit:", options=list(log_opts.keys()))
                    sub_del_audit = st.form_submit_button("🗑️ Hapus Log Ini", use_container_width=True)
                    if sub_del_audit:
                        try:
                            delete_audit_log(supabase, log_opts[sel_log_label])
                            st.success("Log audit berhasil dihapus.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Gagal menghapus log: {str(e)}")
            else:
                st.info("Tidak ada log audit.")
        with col_lg2:
            with st.form("form_clear_all_audits"):
                st.write("**Hapus Seluruh Log Audit**")
                confirm_clear_audits = st.checkbox("Saya yakin ingin menghapus SEMUA riwayat log audit forensik.")
                sub_clear_audits = st.form_submit_button("⚠️ Kosongkan Semua Log Audit", use_container_width=True)
                if sub_clear_audits:
                    if not confirm_clear_audits:
                        st.error("Centang konfirmasi terlebih dahulu.")
                    else:
                        try:
                            clear_all_audit_logs(supabase)
                            st.success("Semua log audit forensik berhasil dibersihkan.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Gagal membersihkan log audit: {str(e)}")
