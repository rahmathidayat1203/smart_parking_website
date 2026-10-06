"""
UI Helper module for Smart Parking Streamlit frontend.
Provides Supabase client retrieval with mock fallback, status badges,
sidebar branding, timestamps, and safe auto-refresh integration.
"""

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, Union, Any
import streamlit as st

from services.supabase_client import get_supabase_client, is_supabase_configured
from services.device_service import get_device_status, is_device_online, register_student_device
from services.auth_service import authenticate_user, register_student_user, can_access_page


def get_current_user(supabase: Optional[Any] = None) -> Optional[dict]:
    """Retrieves currently authenticated user from st.session_state or persistent query_params."""
    user = st.session_state.get("authenticated_user")
    if user:
        return user

    # Auto-restore session across browser refresh (F5 atau Ctrl+Shift+R)
    try:
        if hasattr(st, "query_params") and "u_auth" in st.query_params:
            stored_user = st.query_params.get("u_auth")
            if stored_user:
                sb = supabase if supabase is not None else get_app_supabase()
                from services.auth_service import get_user_by_username
                found = get_user_by_username(sb, stored_user)
                if found:
                    found_copy = dict(found)
                    found_copy.pop("password_hash", None)
                    st.session_state["authenticated_user"] = found_copy
                    return found_copy
    except Exception:
        pass

    return None


def set_current_user(user: Optional[dict]) -> None:
    """Sets the authenticated user in st.session_state and persists in query_params."""
    st.session_state["authenticated_user"] = user
    try:
        if hasattr(st, "query_params"):
            if user and user.get("username"):
                st.query_params["u_auth"] = user.get("username")
            else:
                st.query_params.pop("u_auth", None)
    except Exception:
        pass


def logout_user() -> None:
    """Clears authentication session, removes persistent query_params, and reruns."""
    st.session_state.pop("authenticated_user", None)
    for k in list(st.session_state.keys()):
        if k.startswith("_ready_"):
            st.session_state.pop(k, None)
    try:
        if hasattr(st, "query_params"):
            st.query_params.pop("u_auth", None)
    except Exception:
        pass
    st.rerun()


def get_app_supabase() -> Any:
    """
    Retrieves or initializes the Supabase client for the Streamlit app.
    Checks st.session_state first for state persistence across interactions.
    If live credentials are dummy, missing, or connection fails, falls back gracefully
    to an in-memory MockSupabaseClient.
    """
    if "supabase_client" in st.session_state and st.session_state["supabase_client"] is not None:
        return st.session_state["supabase_client"]

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()

    # Determine if credentials are placeholders / dummy
    is_dummy = (
        not url or not key or
        "dummy" in url.lower() or
        "dummy" in key.lower() or
        "your-project" in url.lower()
    )

    if not is_dummy:
        try:
            with st.spinner("🌐 Menghubungkan ke server database Supabase..."):
                client_options = None
                try:
                    import httpx
                    from supabase import ClientOptions
                    # Pasang custom transport dengan auto-retries dan generous timeout
                    # untuk mencegah [WinError 10035] WSAEWOULDBLOCK pada Windows
                    custom_transport = httpx.HTTPTransport(retries=3)
                    custom_httpx = httpx.Client(
                        timeout=httpx.Timeout(20.0, connect=10.0, read=20.0, write=10.0),
                        transport=custom_transport,
                        follow_redirects=True,
                    )
                    client_options = ClientOptions(httpx_client=custom_httpx)
                except Exception:
                    client_options = None

                client = get_supabase_client(require_real=True, options=client_options)
                # Test connectivity by querying iot_devices
                test_query = client.table("iot_devices").select("id").limit(1).execute()
                st.session_state["supabase_client"] = client
                st.session_state["is_mock"] = False
                return client
        except Exception:
            # Fall back to mock if network or credentials fail
            pass

    # Use Mock Client
    from tests.conftest import MockSupabaseClient
    mock_client = MockSupabaseClient()
    st.session_state["supabase_client"] = mock_client
    st.session_state["is_mock"] = True
    return mock_client


def is_client_mock() -> bool:
    """Returns True if the active Supabase client is a mock instance."""
    return st.session_state.get("is_mock", False)


@contextmanager
def system_loading(
    message: str = "Menyiapkan Sistem Smart Parking...",
    subtext: str = "Sedang menyinkronkan data dengan server & perangkat IoT...",
    key: Optional[str] = None,
    only_initial: bool = False,
):
    """
    Displays an elegant animated loading card while the system or data is preparing.
    Automatically clears when the enclosed block completes.
    If only_initial=True, displays on initial load or manual refresh to avoid
    flicker during background auto-refreshes.
    """
    should_show = True
    state_key = f"_ready_{key}" if key else None

    if only_initial and state_key:
        if st.session_state.get(state_key, False):
            should_show = False

    placeholder = None
    if should_show:
        try:
            placeholder = st.empty()
            placeholder.markdown(
                f"""
                <div style="background: linear-gradient(135deg, #1E3A8A 0%, #2563EB 100%);
                            color: white; padding: 18px 24px; border-radius: 12px; margin-bottom: 20px;
                            box-shadow: 0 4px 14px rgba(37, 99, 235, 0.25); display: flex; align-items: center; gap: 16px;">
                    <div style="width: 28px; height: 28px; border: 3px solid rgba(255,255,255,0.3);
                                border-radius: 50%; border-top-color: #FFFFFF; animation: sys-spin 0.8s linear infinite; flex-shrink: 0;"></div>
                    <div>
                        <div style="font-weight: 700; font-size: 1.02rem; letter-spacing: -0.01em;">{message}</div>
                        <div style="font-size: 0.84rem; color: #DBEAFE; margin-top: 2px;">{subtext}</div>
                    </div>
                </div>
                <style>
                    @keyframes sys-spin {{
                        0% {{ transform: rotate(0deg); }}
                        100% {{ transform: rotate(360deg); }}
                    }}
                </style>
                """,
                unsafe_allow_html=True,
            )
        except Exception:
            placeholder = None

    try:
        yield placeholder
    except Exception as e:
        # Tangani error koneksi / socket Windows secara aman tanpa crash
        if placeholder is not None:
            try:
                placeholder.empty()
            except Exception:
                pass
        st.warning(f"⚠️ **Koneksi Jaringan Terkendala**: Sistem sedang mencoba menyinkronkan ulang data ({type(e).__name__}).")
    finally:
        if placeholder is not None:
            try:
                placeholder.empty()
            except Exception:
                pass
        if state_key:
            st.session_state[state_key] = True


def render_status_badge(status: str, label: Optional[str] = None) -> str:
    """
    Generates an HTML status badge styled according to status value.
    Green for available/online/active/kosong.
    Red for occupied/offline/inactive/terisi.
    Yellow/Orange for waiting/idle/unknown.
    """
    clean_status = (status or "").lower().strip()
    display_label = label if label is not None else status.upper()

    if clean_status in ["available", "kosong", "online", "active", "aktif", "success"]:
        bg_color = "#DEF7EC"
        text_color = "#03543F"
        border_color = "#31C48D"
        icon = "&bull; "
    elif clean_status in ["occupied", "terisi", "offline", "inactive", "nonaktif", "danger", "error"]:
        bg_color = "#FDE8E8"
        text_color = "#9B1C1C"
        border_color = "#F98080"
        icon = "&bull; "
    elif clean_status in ["waiting", "menunggu", "warning", "idle", "connecting", "menghubungkan", "loading"]:
        bg_color = "#FEF08A"
        text_color = "#713F12"
        border_color = "#FACC15"
        icon = "&#9203; "
    else:
        bg_color = "#F3F4F6"
        text_color = "#374151"
        border_color = "#D1D5DB"
        icon = "&#9675; "

    badge_html = (
        f'<span style="display: inline-block; padding: 3px 10px; font-size: 0.82rem; '
        f'font-weight: 600; border-radius: 9999px; background-color: {bg_color}; '
        f'color: {text_color}; border: 1px solid {border_color}; vertical-align: middle;">'
        f'{icon}{display_label}'
        f'</span>'
    )
    return badge_html


def render_sidebar_branding(supabase: Optional[Any] = None) -> None:
    """
    Renders standardized sidebar navigation branding, connection status,
    and system metadata.
    """
    with st.sidebar:
        # Hide default auto-generated multi-page navigation
        st.markdown(
            """
            <style>
            [data-testid="stSidebarNav"] {
                display: none !important;
            }
            /* Smooth page load transition */
            @keyframes fadeInContainer {
                from { opacity: 0.88; transform: translateY(2px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .main .block-container {
                animation: fadeInContainer 0.2s ease-out;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        st.markdown(
            """
            <div style="text-align: center; padding: 0.5rem 0 1rem 0;">
                <h2 style="margin: 0; color: #1E3A8A;">🚗 SMART PARKING</h2>
                <p style="margin: 4px 0 0 0; font-size: 0.85rem; color: #64748B;">
                    ESP32-S3 & Supabase IoT System
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Authenticated User Status in Sidebar
        user = get_current_user()
        if user:
            role_label = "Administrator" if user.get("role") == "admin" else "Siswa / Mahasiswa"
            user_icon = "👑" if user.get("role") == "admin" else "🎓"
            full_name = user.get("full_name", user.get("username"))
            dev_badge = f"<div style='font-size: 0.72rem; color: #4338CA; margin-top: 3px;'>Device: <code>{user.get('device_id')}</code></div>" if user.get("device_id") else ""

            st.markdown(
                f"""
                <div style="background: #EEF2FF; border: 1px solid #C7D2FE; border-radius: 8px; padding: 10px; margin-bottom: 10px;">
                    <div style="font-size: 0.72rem; font-weight: 700; color: #4338CA; text-transform: uppercase;">{user_icon} {role_label}</div>
                    <div style="font-size: 0.88rem; font-weight: 700; color: #1E1B4B; margin-top: 2px;">{full_name}</div>
                    {dev_badge}
                </div>
                """,
                unsafe_allow_html=True
            )

            # Role-Adaptive Navigation Links
            st.markdown(
                """
                <div style="font-size: 0.72rem; font-weight: 700; color: #475569; margin: 6px 0 4px 0; text-transform: uppercase; letter-spacing: 0.05em;">
                    🧭 MENU NAVIGASI:
                </div>
                """,
                unsafe_allow_html=True
            )
            role = user.get("role", "student")
            if role == "admin":
                st.page_link("app.py", label="Dashboard Utama", icon="🚗")
                st.page_link("pages/1_Monitoring_Parkir.py", label="Monitoring Parkir", icon="🅿️")
                st.page_link("pages/2_Member_RFID.py", label="Member RFID", icon="💳")
                st.page_link("pages/3_IoT_Device.py", label="Perangkat IoT & Siswa", icon="📟")
                st.page_link("pages/4_Monitoring_Sensor.py", label="Monitoring Sensor", icon="📡")
                st.page_link("pages/5_Dashboard_Siswa.py", label="Audit Dashboard Siswa", icon="🎓")
                st.page_link("pages/6_Manajemen_User.py", label="Manajemen User & Hak Akses", icon="👥")
            elif role in ["student", "siswa"]:
                st.page_link("pages/1_Monitoring_Parkir.py", label="Monitoring Parkir", icon="🅿️")
                st.page_link("pages/5_Dashboard_Siswa.py", label="Dashboard Saya & Perangkat", icon="🎓")

            st.markdown("---")

            if st.button("🚪 Keluar (Logout)", use_container_width=True, key="sidebar_logout_btn"):
                logout_user()

        # Connection Mode Indicator
        if is_client_mock():
            st.info("💡 **Mode Demo / Mock Storage**\n\nData tersimpan di sesi Streamlit lokal.")
        else:
            st.success("🌐 **Supabase Terhubung**\n\nKoneksi database PostgreSQL aktif.")

        # ESP32-S3 Live Device Health Check in Sidebar (Cached for 5s to ensure fast navigation)
        if supabase is not None:
            try:
                now_t = datetime.now(timezone.utc).timestamp()
                cached_gate = st.session_state.get("_sb_gate_status")
                cached_park = st.session_state.get("_sb_park_status")
                last_sb_check = st.session_state.get("_sb_last_check", 0)

                if now_t - last_sb_check > 5 or cached_gate is None:
                    cached_gate = get_device_status(supabase, "GATE-01")
                    cached_park = get_device_status(supabase, "PARKING-01")
                    st.session_state["_sb_gate_status"] = cached_gate
                    st.session_state["_sb_park_status"] = cached_park
                    st.session_state["_sb_last_check"] = now_t

                gate_online = is_device_online(cached_gate.get("last_seen") if cached_gate else None)
                gate_badge = render_status_badge("ONLINE" if gate_online else "OFFLINE")

                parking_online = is_device_online(cached_park.get("last_seen") if cached_park else None)
                parking_badge = render_status_badge("ONLINE" if parking_online else "OFFLINE")

                st.markdown(
                    f"""
                    <div style="background: rgba(148, 163, 184, 0.08); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 8px; padding: 10px; margin-bottom: 12px;">
                        <div style="font-size: 0.78rem; font-weight: 600; margin-bottom: 6px; opacity: 0.85;">STATUS PERANGKAT UTAMA:</div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; font-size: 0.82rem;">
                            <span>GATE-01</span>
                            {gate_badge}
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.82rem;">
                            <span>PARKING-01</span>
                            {parking_badge}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            except Exception:
                pass

        if st.button("🔄 Refresh Halaman", use_container_width=True):
            for k in list(st.session_state.keys()):
                if k.startswith("_ready_"):
                    st.session_state.pop(k, None)
            st.rerun()

        st.divider()
        st.markdown(
            """
            <div style="font-size: 0.75rem; color: #94A3B8; line-height: 1.4;">
                <b>Design Principles:</b><br/>
                • Status-oriented & Read-only UID<br/>
                • Automatic Gate Control (No Manual Button)<br/>
                • Offline Threshold: 30 detik<br/>
                • Auto-refresh: 4 detik
            </div>
            """,
            unsafe_allow_html=True
        )


def realtime_fragment(run_every: Union[int, str] = "3s"):
    """
    Decorator for Streamlit fragments (Streamlit 1.33+ / 1.37+).
    Enables selective partial component re-rendering without refreshing the whole page.
    Prevents annoying full-page flickering, scrolling jumps, and input focus loss.
    Falls back gracefully if st.fragment is unavailable.
    """
    if hasattr(st, "fragment"):
        return st.fragment(run_every=run_every)
    def decorator(func):
        return func
    return decorator


def setup_auto_refresh(interval_ms: int = 4000, key: str = "auto_refresh_counter", enable_full_page_refresh: bool = False) -> None:
    """
    Safely triggers automatic page refresh ONLY if enable_full_page_refresh is explicitly True.
    By default, disruptive full-page reruns are disabled in favor of selective component
    updates using `@realtime_fragment(run_every="3s")`.
    """
    if not enable_full_page_refresh:
        return
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=interval_ms, key=key)
    except Exception:
        pass


def format_timestamp(ts: Optional[Union[str, datetime]]) -> str:
    """
    Formats an ISO timestamp or datetime object to readable 'YYYY-MM-DD HH:MM:SS' string.
    """
    if ts is None:
        return "-"
    if isinstance(ts, str):
        normalized = ts.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except Exception:
            return ts
    elif isinstance(ts, datetime):
        dt = ts
    else:
        return str(ts)

    # Format localized string
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def get_relative_time(ts: Optional[Union[str, datetime]]) -> str:
    """
    Calculates the relative time difference from now in Indonesian (e.g. '15 detik yang lalu').
    """
    if ts is None:
        return "Tidak diketahui"

    if isinstance(ts, str):
        normalized = ts.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except Exception:
            return str(ts)
    elif isinstance(ts, datetime):
        dt = ts
    else:
        return str(ts)

    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    diff = (now - dt).total_seconds()
    if diff < 0:
        return "Baru saja"
    if diff < 5:
        return "Baru saja"
    elif diff < 60:
        return f"{int(diff)} detik yang lalu"
    elif diff < 3600:
        minutes = int(diff / 60)
        return f"{minutes} menit yang lalu"
    elif diff < 86400:
        hours = int(diff / 3600)
        return f"{hours} jam yang lalu"
    else:
        days = int(diff / 86400)
        return f"{days} hari yang lalu"


def render_login_widget(supabase: Any) -> None:
    """
    Renders an authentication dialog / card for Admin & Student Login / Registration.
    Completely hides the sidebar on the login screen for a clean, distraction-free view.
    """
    # Sembunyikan sidebar dan tombol toggle chevron sepenuhnya di layar login
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            display: none !important;
        }
        [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }
        /* Buat form login berada di tengah layar secara elegan */
        .main .block-container {
            max-width: 800px !important;
            padding-top: 3.5rem !important;
            margin: 0 auto !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <div style="text-align: center; margin: 1rem 0 1.5rem 0;">
            <h1 style="color: #1E3A8A; margin-bottom: 4px;">🚗 Smart Parking System</h1>
            <p style="color: #64748B; font-size: 1.05rem;">Sistem Otentikasi & Portal Akses Berbasis IoT</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        tab_login, tab_register = st.tabs(["🔐 Masuk (Login)", "📝 Registrasi Siswa Baru"])

        with tab_login:
            st.caption("Masuk menggunakan akun Administrator atau Akun Siswa:")
            with st.form("login_form"):
                username_in = st.text_input("Username:", placeholder="admin / siswa1").strip()
                password_in = st.text_input("Password:", type="password", placeholder="••••••••").strip()
                submit_login = st.form_submit_button("🚀 Masuk ke Sistem", use_container_width=True)

                if submit_login:
                    with st.spinner("🔐 Memverifikasi kredensial & menyiapkan sesi akun..."):
                        user = authenticate_user(supabase, username_in, password_in)
                        if user:
                            set_current_user(user)
                            st.success(f"Selamat datang kembali, {user.get('full_name')}!")
                            st.rerun()
                        else:
                            st.error("Username atau password salah. Silakan coba lagi.")


        with tab_register:
            st.caption("Pendaftaran akun siswa dan pembuatan perangkat IoT mandiri:")
            with st.form("student_reg_form"):
                reg_name = st.text_input("Nama Lengkap Siswa / Kelompok:", placeholder="Contoh: Budi Santoso").strip()
                reg_user = st.text_input("Username Pilihan:", placeholder="Contoh: budi_iot").strip().lower()
                reg_pass = st.text_input("Password (min 6 karakter):", type="password", placeholder="••••••••").strip()
                reg_dev_name = st.text_input("Nama Perangkat IoT:", placeholder="Contoh: ESP32 Gerbang Siswa B").strip()
                reg_dev_type = st.selectbox(
                    "Tipe Perangkat:",
                    options=["multi-sensor", "gate", "parking-slot"],
                    format_func=lambda x: {
                        "multi-sensor": "All-in-One (Ultrasonik + IR + RFID)",
                        "gate": "Gerbang Masuk (RFID + Servo)",
                        "parking-slot": "Slot Parkir (IR ADC Sensor)"
                    }.get(x, x),
                    key="reg_dev_type_sel"
                )
                submit_reg = st.form_submit_button("✨ Buat Akun & Dapatkan Perangkat", use_container_width=True)

                if submit_reg:
                    if not reg_name or not reg_user or not reg_pass:
                        st.error("Nama lengkap, username, dan password wajib diisi!")
                    elif len(reg_pass) < 6:
                        st.error("Password minimal 6 karakter!")
                    else:
                        try:
                            with st.spinner("✨ Mendaftarkan akun siswa & membuat kunci API perangkat IoT..."):
                                # 1. Register student device
                                new_dev = register_student_device(
                                    supabase,
                                    owner_name=reg_name,
                                    device_name=reg_dev_name or f"ESP32 {reg_name}",
                                    device_type=reg_dev_type,
                                )
                                # 2. Register student user account bound to this device
                                new_user = register_student_user(
                                    supabase,
                                    username=reg_user,
                                    password=reg_pass,
                                    full_name=reg_name,
                                    device_id=new_dev.get("device_id")
                                )
                                # Set session
                                set_current_user(new_user)
                                st.session_state["recent_registered_device"] = new_dev
                                st.success(f"Akun dan perangkat {new_dev.get('device_id')} berhasil didaftarkan!")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Gagal mendaftar: {str(e)}")


def require_auth(
    supabase: Any,
    allowed_roles: Optional[list] = None,
    current_page_name: str = ""
) -> dict:
    """
    Guards a page with authentication and role-based access control.
    If unauthenticated, renders login widget and halts page execution via st.stop().
    If authenticated but role is forbidden, displays warning and halts execution.
    Returns the authenticated user dict.
    """
    user = get_current_user()

    if not user:
        render_login_widget(supabase)
        st.stop()
        return {}

    user_role = user.get("role", "student")

    # If role-based restrictions provided
    if allowed_roles and user_role not in allowed_roles:
        st.error("⛔ **Akses Dibatasi**: Halaman ini dikhususkan untuk Administrator.")
        st.info("Sebagai Siswa, Anda memiliki akses penuh ke menu **Monitoring Parkir** dan **Dashboard Siswa**.")
        st.stop()

    if current_page_name and not can_access_page(user_role, current_page_name):
        st.error(f"⛔ **Akses Dibatasi**: Peran '{user_role}' tidak memiliki izin membuka halaman ini.")
        st.info("Sebagai Siswa, Anda dapat mengakses menu: **Monitoring Parkir** dan **Dashboard Siswa**.")
        st.stop()

    return user

