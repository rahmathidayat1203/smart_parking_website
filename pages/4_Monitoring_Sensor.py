"""
Smart Parking Monitoring & RFID Member System - Monitoring Sensor
Page: pages/4_Monitoring_Sensor.py

Adheres strictly to DRD Sec 15 & 16 and TRD Sec 22:
- HC-SR04 Ultrasonic Card: Distance (cm) and vehicle detection status
  ("Mobil Terdeteksi" if <= 40cm, "Tidak Ada Mobil" if > 40cm)
- IR Sensor Cards per slot (P01-P04): Raw ADC sensor value & calculated slot status
- Sensor Data Table: historical sensor logs (Sensor type, Device ID, Value, Status, Timestamp)
- Auto-refresh enabled (4s)
- Strictly NO manual gate buttons
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
from services.sensor_service import (
    get_latest_sensor_by_type,
    get_recent_sensor_data,
    add_sensor_reading,
    CAR_DETECTION_DISTANCE_CM,
)
from services.parking_service import (
    get_parking_slots,
    evaluate_slot_status,
)

# 1. Page Config
st.set_page_config(
    page_title="Smart Parking - Monitoring Sensor",
    page_icon="📡",
    layout="wide",
)

# 2. Setup Auto-Refresh
setup_auto_refresh(interval_ms=4000, key="sensor_autorefresh")

# 3. Retrieve Supabase Client
supabase = get_app_supabase()

# 4. Authentication Check (Admin Only)
user = require_auth(supabase, allowed_roles=["admin"], current_page_name="4_Monitoring_Sensor.py")

# 5. Sidebar Branding
render_sidebar_branding(supabase=supabase)

# 5. Header
st.title("📡 Monitoring Sensor")
st.caption("Pemantauan Sensor Ultrasonik HC-SR04 & Sensor IR Digital Slot Parkir ESP32")
st.markdown("---")

@realtime_fragment(run_every="3s")
def render_live_sensors():
    # 6. Top Section: Live Sensor Overview
    with system_loading(
        message="Mengambil Telemetri Sensor...",
        subtext="Menyinkronkan pembacaan sensor ultrasonik & IR...",
        key="sensor_monitoring",
        only_initial=True,
    ):
        latest_us = get_latest_sensor_by_type(supabase, "ultrasonic")
        slots = get_parking_slots(supabase)

    col_us, col_ir_overview = st.columns([1, 2], gap="large")

    # 6.1 HC-SR04 Ultrasonic Card
    with col_us:
        st.subheader("🏎️ Sensor Ultrasonik (Gate)")
        st.caption("Mendeteksi keberadaan kendaraan di depan pintu gerbang (Ambang &le; 20 cm).")

        if not latest_us or latest_us.get("sensor_value") is None:
            st.info("Belum ada data sensor ultrasonik.")
        else:
            dist = float(latest_us.get("sensor_value"))
            car_detected = (dist > 0 and dist <= CAR_DETECTION_DISTANCE_CM)
            status_label = "Mobil Terdeteksi (&le; 20 cm)" if car_detected else ("Tidak Ada Mobil (> 20 cm)" if dist > 0 else "Di Luar Jangkauan")
            badge_type = "occupied" if car_detected else "available"
            badge = render_status_badge(badge_type, label=status_label)
            last_seen_ts = format_timestamp(latest_us.get("created_at"))
            rel_time = get_relative_time(latest_us.get("created_at"))
            dev_id = latest_us.get("device_id", "GATE-01")

            card_border = "#EF4444" if car_detected else "#10B981"
            card_bg = "#FEF2F2" if car_detected else "#F0FDF4"
            dist_str = f"{dist:.1f}" if dist >= 0 else "--"

            st.markdown(
                f"""
                <div style="border: 2px solid {card_border}; background-color: {card_bg}; 
                            border-radius: 12px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <span style="font-weight: 700; color: #1E293B;">HC-SR04 Gate Node</span>
                        <div>{badge}</div>
                    </div>
                    <div style="text-align: center; padding: 15px 0;">
                        <div style="font-size: 0.85rem; color: #64748B; margin-bottom: 4px;">JARAK TERUKUR:</div>
                        <div style="font-size: 2.5rem; font-weight: 800; color: #0284C7; font-family: monospace;">
                            {dist_str} <span style="font-size: 1.2rem;">cm</span>
                        </div>
                    </div>
                    <div style="border-top: 1px solid rgba(0,0,0,0.08); padding-top: 10px; font-size: 0.8rem; color: #475569;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                            <span>Node ID:</span>
                            <span style="font-weight: 600;">{dev_id}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between;">
                            <span>Pembaruan:</span>
                            <span>{last_seen_ts} ({rel_time})</span>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # 6.2 IR Sensor Cards per Slot
    with col_ir_overview:
        st.subheader("📶 Sensor IR Slot Parkir (3 Slot IR)")
        st.caption("Pembacaan sensor infra-merah digital Active-LOW (0=LOW/Terisi, 1=HIGH/Bebas).")

        if not slots:
            st.info("⏳ **Sistem Sedang Menyiapkan Slot Parkir...**\n\nMenunggu inisialisasi data slot dari database atau sensor ESP32.")
        else:
            num_ir_cols = len(slots) if len(slots) <= 3 else 2
            grid_cols = st.columns(num_ir_cols)
            for idx, s in enumerate(slots):
                with grid_cols[idx % num_ir_cols]:
                    s_code = s.get("slot_code", f"Slot {idx+1}")
                    display_s_code = f"{s_code} (Slot {idx+1})" if not s_code.lower().startswith("slot") else s_code
                    s_val = s.get("sensor_value")
                    s_time = format_timestamp(s.get("updated_at"))
                    s_rel = get_relative_time(s.get("updated_at"))

                    # Evaluate slot status from IR value
                    evaluated_stat = evaluate_slot_status(s_val, ir_threshold=1000)
                    status_str = "TERISI" if evaluated_stat == "occupied" else "KOSONG"
                    badge = render_status_badge(status_str)

                    border_clr = "#EF4444" if evaluated_stat == "occupied" else "#10B981"
                    bg_clr = "#FEF2F2" if evaluated_stat == "occupied" else "#F0FDF4"

                    if s_val is None:
                        val_text = "-"
                    elif s_val == 0:
                        val_text = "0 (LOW • Terhalang)"
                    elif s_val == 1:
                        val_text = "1 (HIGH • Bebas)"
                    else:
                        val_text = f"{s_val}"

                    st.markdown(
                        f"""
                        <div style="border: 1px solid {border_clr}; background-color: {bg_clr}; 
                                    border-radius: 10px; padding: 14px; margin-bottom: 12px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <span style="font-size: 1.15rem; font-weight: 800; color: #1E293B;">{display_s_code}</span>
                                <div>{badge}</div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px;">
                                <span style="font-size: 0.85rem; color: #64748B;">Logika / Nilai:</span>
                                <span style="font-family: monospace; font-size: 1.05rem; font-weight: 700; color: #1E293B;">
                                    {val_text}
                                </span>
                            </div>
                            <div style="font-size: 0.75rem; color: #94A3B8; text-align: right;">
                                {s_time} ({s_rel})
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

    st.markdown("---")

    # 7. Sensor Data History Table (DRD Sec 16)
    st.subheader("📊 Riwayat Log Pembacaan Sensor")

    filter_col1, filter_col2 = st.columns([1, 3])
    with filter_col1:
        sensor_filter = st.selectbox(
            "Filter Tipe Sensor:",
            options=["Semua Sensor", "Ultrasonik (HC-SR04)", "Infra-Red (IR)"],
        )

    with filter_col2:
        limit_count = st.slider("Jumlah Riwayat:", min_value=10, max_value=100, value=30, step=10)

    recent_data = get_recent_sensor_data(supabase, limit=limit_count)

    if not recent_data:
        st.info("Belum ada log sensor yang tercatat.")
    else:
        # Filter
        if sensor_filter == "Ultrasonik (HC-SR04)":
            filtered_logs = [d for d in recent_data if d.get("sensor_type") == "ultrasonic"]
        elif sensor_filter == "Infra-Red (IR)":
            filtered_logs = [d for d in recent_data if d.get("sensor_type") == "ir"]
        else:
            filtered_logs = recent_data

        table_rows = []
        for r in filtered_logs:
            stype = r.get("sensor_type", "-")
            sval = r.get("sensor_value")
            sval_fmt = f"{sval:.1f} cm" if stype == "ultrasonic" and sval is not None else (f"{int(sval)}" if sval is not None else "-")

            # Estimation status
            if stype == "ultrasonic":
                status_est = "Mobil Terdeteksi (&le; 20cm)" if (sval is not None and 0 < sval <= CAR_DETECTION_DISTANCE_CM) else "Tidak Ada Mobil"
            elif stype == "ir":
                stat = evaluate_slot_status(sval)
                status_est = "Slot Terisi" if stat == "occupied" else "Slot Kosong"
            else:
                status_est = "-"

            table_rows.append({
                "ID Log": r.get("id"),
                "Tipe Sensor": stype.upper(),
                "Device ID": r.get("device_id", "-"),
                "Nilai Sensor": sval_fmt,
                "Estimasi Status": status_est,
                "Waktu Tercatat": format_timestamp(r.get("created_at")),
            })

        st.dataframe(
            pd.DataFrame(table_rows),
            width="stretch",
            hide_index=True,
        )

    st.markdown("---")

    # 8. Testing / Simulation Helper
    with st.expander("🧪 Simulasi Pengiriman Data Sensor (Testing / Demo)"):
        st.caption("Tambahkan pembacaan sensor baru ke Supabase untuk keperluan demonstrasi:")
        sim_c1, sim_c2, sim_c3 = st.columns(3)
        with sim_c1:
            sim_type = st.selectbox("Jenis Sensor", ["ultrasonic", "ir"])
        with sim_c2:
            sim_dev = st.selectbox("Device ID", ["GATE-01", "PARKING-01"])
        with sim_c3:
            sim_val = st.number_input("Nilai Sensor (cm untuk US, ADC untuk IR)", min_value=0.0, value=25.5, step=1.0)

        if st.button("📤 Kirim Data Sensor Baru"):
            try:
                add_sensor_reading(supabase, device_id=sim_dev, sensor_type=sim_type, sensor_value=sim_val)
                st.success("Data sensor berhasil ditambahkan ke database!")
                st.rerun()
            except Exception as e:
                st.error(f"Gagal menambahkan data: {str(e)}")

# Jalankan fragment telemetri sensor
render_live_sensors()
