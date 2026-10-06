"""
Smart Parking Monitoring & RFID Member System - Manajemen User & Hak Akses
Page: pages/6_Manajemen_User.py

Admin-only management portal to oversee application users, assign roles (Admin/Student),
link IoT devices, reset passwords, and register or delete user accounts.
"""

from datetime import datetime, timezone
import streamlit as st
import pandas as pd

from utils.ui_helpers import (
    get_app_supabase,
    render_status_badge,
    render_sidebar_branding,
    setup_auto_refresh,
    format_timestamp,
    require_auth,
    system_loading,
)
from services.auth_service import (
    get_all_users,
    update_user_role,
    update_user_device,
    update_user_profile,
    reset_user_password,
    delete_user,
    register_student_user,
    hash_password,
)
from services.device_service import get_all_devices

# 1. Page Config
st.set_page_config(
    page_title="Smart Parking - Manajemen User & Hak Akses",
    page_icon="👥",
    layout="wide",
)

# 2. Setup Auto-Refresh
setup_auto_refresh(interval_ms=4000, key="user_mgmt_autorefresh")

# 3. Retrieve Supabase Client
supabase = get_app_supabase()

# 4. Authentication Check (Strictly Admin Only)
current_user = require_auth(supabase, allowed_roles=["admin"], current_page_name="6_Manajemen_User.py")

# 5. Sidebar Branding
render_sidebar_branding(supabase=supabase)

# 6. Header
st.title("👥 Manajemen Pengguna & Hak Akses (RBAC)")
st.caption("Kelola Akun, Penugasan Peran (Admin/Siswa), Asosiasi Perangkat IoT, dan Keamanan")
st.markdown("---")

# 7. Fetch Users & Devices Data
with system_loading(
    message="Memuat Manajemen Pengguna...",
    subtext="Mengambil daftar akun, penugasan perangkat, dan hak akses...",
    key="user_mgmt",
    only_initial=True,
):
    users = get_all_users(supabase)
    devices = get_all_devices(supabase)
device_ids = [d.get("device_id") for d in devices if d.get("device_id")]

# 8. User Summary Metrics
total_users = len(users)
admin_count = sum(1 for u in users if u.get("role") == "admin")
student_count = sum(1 for u in users if u.get("role") == "student")

col_m1, col_m2, col_m3, col_m4 = st.columns([1, 1, 1, 2])
with col_m1:
    st.metric("Total Pengguna", total_users)
with col_m2:
    st.metric("Administrator", admin_count)
with col_m3:
    st.metric("Siswa / Mahasiswa", student_count)
with col_m4:
    search_query = st.text_input("🔍 Cari Pengguna:", placeholder="Ketik username, nama, atau device ID...").strip().lower()

st.markdown("---")

# 9. Registered Users Table
st.subheader("📋 Daftar Pengguna Terdaftar")

filtered_users = [
    u for u in users
    if not search_query or
    search_query in u.get("username", "").lower() or
    search_query in u.get("full_name", "").lower() or
    search_query in str(u.get("device_id", "")).lower() or
    search_query in u.get("role", "").lower()
]

if filtered_users:
    df_users = pd.DataFrame(filtered_users)
    display_df = df_users[["id", "username", "full_name", "role", "device_id", "created_at"]].copy()
    display_df["role"] = display_df["role"].apply(lambda r: "👑 Administrator" if r == "admin" else "🎓 Siswa")
    display_df["device_id"] = display_df["device_id"].fillna("-")
    display_df["created_at"] = display_df["created_at"].apply(format_timestamp)
    display_df.columns = ["ID", "Username", "Nama Lengkap", "Peran (Role)", "Device ID Terkait", "Tanggal Terdaftar"]

    st.dataframe(display_df, width="stretch", height=240)
else:
    st.info("Tidak ada pengguna yang cocok dengan kriteria pencarian.")

st.markdown("---")

# 10. User Management Action Tabs
st.subheader("⚙️ Aksi Pengelolaan Pengguna")

tab_role, tab_pass, tab_create, tab_del = st.tabs([
    "✏️ Edit Profil & Hak Akses",
    "🔑 Reset Password",
    "➕ Tambah Akun Pengguna",
    "🗑️ Hapus Pengguna",
])

usernames_list = [u.get("username") for u in users]

# -------------------------------------------------------------
# TAB 1: Edit Profil, Hak Akses / Peran & Asosiasi Device
# -------------------------------------------------------------
with tab_role:
    st.caption("Ubah nama lengkap, peran akun (Administrator/Siswa), dan kaitkan ID perangkat IoT:")
    if usernames_list:
        with st.form("form_edit_user_profile"):
            target_user = st.selectbox("Pilih Pengguna yang Ingin Diedit:", options=usernames_list, key="sel_user_role")
            current_profile = next((u for u in users if u.get("username") == target_user), {})
            current_role = current_profile.get("role", "student")
            current_fname = current_profile.get("full_name", "")
            current_dev = current_profile.get("device_id") or ""

            col_r1, col_r2 = st.columns(2)
            with col_r1:
                edit_fname = st.text_input("Nama Lengkap:", value=current_fname).strip()
                new_role = st.selectbox(
                    "Pilih Peran (Role):",
                    options=["admin", "student"],
                    index=0 if current_role == "admin" else 1,
                    format_func=lambda x: "👑 Administrator (Akses Penuh)" if x == "admin" else "🎓 Siswa (Akses Mandiri)"
                )

            with col_r2:
                dev_options = ["(Tanpa Perangkat)"] + device_ids
                default_dev_idx = dev_options.index(current_dev) if current_dev in dev_options else 0
                selected_dev = st.selectbox("Asosiasi Perangkat Siswa:", options=dev_options, index=default_dev_idx)
                st.caption(f"Username: **`{target_user}`** (ID User tidak dapat diubah)")

            submit_profile_edit = st.form_submit_button("💾 Simpan Perubahan Profil & Hak Akses", use_container_width=True)

            if submit_profile_edit:
                if not edit_fname:
                    st.error("Nama lengkap tidak boleh kosong!")
                else:
                    try:
                        assigned_dev = None if selected_dev == "(Tanpa Perangkat)" else selected_dev
                        update_user_profile(
                            supabase,
                            username=target_user,
                            full_name=edit_fname,
                            role=new_role,
                            device_id=assigned_dev
                        )
                        st.success(f"Data pengguna **{target_user}** berhasil diperbarui!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal memperbarui pengguna: {str(e)}")

# -------------------------------------------------------------
# TAB 2: Reset Password
# -------------------------------------------------------------
with tab_pass:
    st.caption("Atur ulang kata sandi pengguna jika lupa password:")
    if usernames_list:
        with st.form("form_reset_pass"):
            target_pass_user = st.selectbox("Pilih Pengguna:", options=usernames_list, key="sel_user_pass")
            new_pass = st.text_input("Password Baru (Minimal 6 karakter):", type="password", placeholder="••••••••").strip()
            submit_pass = st.form_submit_button("🔐 Reset Password Pengguna", use_container_width=True)

            if submit_pass:
                if len(new_pass) < 6:
                    st.error("Password baru minimal 6 karakter!")
                else:
                    try:
                        reset_user_password(supabase, target_pass_user, new_pass)
                        st.success(f"Password untuk **{target_pass_user}** berhasil diubah!")
                    except Exception as e:
                        st.error(f"Gagal mereset password: {str(e)}")

# -------------------------------------------------------------
# TAB 3: Tambah Pengguna Baru
# -------------------------------------------------------------
with tab_create:
    st.caption("Daftarkan akun pengguna baru langsung dari portal Administrator:")
    with st.form("form_create_user", clear_on_submit=True):
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            new_u_name = st.text_input("Nama Lengkap:", placeholder="Contoh: Rahmat Hidayat").strip()
            new_u_username = st.text_input("Username:", placeholder="Contoh: rahmat_iot").strip().lower()
            new_u_pass = st.text_input("Password (min 6 karakter):", type="password", placeholder="••••••••").strip()
        with col_c2:
            new_u_role = st.selectbox(
                "Peran Pengguna:",
                options=["student", "admin"],
                format_func=lambda x: "🎓 Siswa / Mahasiswa" if x == "student" else "👑 Administrator"
            )
            new_u_dev = st.selectbox("Kaitkan ke Device (Opsional):", options=["(Tidak ada)"] + device_ids)

        submit_create = st.form_submit_button("✨ Daftarkan Pengguna Baru", use_container_width=True)

        if submit_create:
            if not new_u_name or not new_u_username or not new_u_pass:
                st.error("Semua field wajib diisi!")
            elif len(new_u_pass) < 6:
                st.error("Password minimal 6 karakter!")
            else:
                try:
                    chosen_dev = None if new_u_dev == "(Tidak ada)" else new_u_dev
                    if new_u_role == "admin":
                        # Insert admin directly
                        now_iso = datetime.now(timezone.utc).isoformat()
                        payload = {
                            "username": new_u_username,
                            "password_hash": hash_password(new_u_pass),
                            "role": "admin",
                            "full_name": new_u_name,
                            "device_id": chosen_dev,
                            "created_at": now_iso,
                        }
                        supabase.table("app_users").insert(payload).execute()
                    else:
                        register_student_user(
                            supabase,
                            username=new_u_username,
                            password=new_u_pass,
                            full_name=new_u_name,
                            device_id=chosen_dev
                        )
                    st.success(f"Pengguna **{new_u_username}** ({new_u_role.upper()}) berhasil didaftarkan!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal menambahkan pengguna: {str(e)}")

# -------------------------------------------------------------
# TAB 4: Hapus Pengguna
# -------------------------------------------------------------
with tab_del:
    st.caption("Hapus akun pengguna yang sudah tidak aktif atau selesai masa pembelajaran:")
    if usernames_list:
        with st.form("form_del_user"):
            target_del_user = st.selectbox("Pilih Pengguna yang Ingin Dihapus:", options=usernames_list, key="sel_user_del")
            confirm_del = st.checkbox(f"Saya yakin ingin menghapus akun '{target_del_user}' secara permanen.")
            submit_del = st.form_submit_button("🗑️ Hapus Akun Pengguna", use_container_width=True)

            if submit_del:
                if not confirm_del:
                    st.error("Silakan centang kotak konfirmasi sebelum menghapus.")
                else:
                    try:
                        active_admin = current_user.get("username")
                        delete_user(supabase, username_to_delete=target_del_user, current_admin_username=active_admin)
                        st.success(f"Akun pengguna **{target_del_user}** berhasil dihapus.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Gagal menghapus pengguna: {str(e)}")
