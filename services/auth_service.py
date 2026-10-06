"""
Authentication and Role-Based Access Control (RBAC) service for Smart Parking.
Handles user credential verification, password hashing, student registration,
and page permission validation.
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any


def hash_password(password: str) -> str:
    """Computes SHA-256 hash of plaintext password."""
    if not password:
        return ""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """Verifies that the plaintext password matches the stored hash."""
    if not password or not password_hash:
        return False
    return hash_password(password) == password_hash


def get_user_by_username(supabase: Any, username: str) -> Optional[Dict[str, Any]]:
    """Retrieves user profile by username from app_users table."""
    if not username:
        return None
    res = supabase.table("app_users").select("*").eq("username", username.strip().lower()).execute()
    if res.data and len(res.data) > 0:
        return res.data[0]
    return None


def authenticate_user(
    supabase: Any,
    username: str,
    password: str
) -> Optional[Dict[str, Any]]:
    """
    Authenticates a user by username and password.
    Returns the user dict if valid, otherwise None.
    """
    clean_user = (username or "").strip().lower()
    clean_pass = (password or "").strip()

    if not clean_user or not clean_pass:
        return None

    user = get_user_by_username(supabase, clean_user)
    if not user:
        return None

    stored_hash = user.get("password_hash", "")
    if verify_password(clean_pass, stored_hash):
        # Do not expose password_hash
        user_copy = dict(user)
        user_copy.pop("password_hash", None)
        return user_copy

    return None


def register_student_user(
    supabase: Any,
    username: str,
    password: str,
    full_name: str,
    device_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Registers a new student user account.
    """
    clean_user = (username or "").strip().lower()
    if not clean_user:
        raise ValueError("Username tidak boleh kosong.")

    clean_pass = (password or "").strip()
    if len(clean_pass) < 6:
        raise ValueError("Password minimal 6 karakter.")

    clean_name = (full_name or "").strip()
    if not clean_name:
        raise ValueError("Nama lengkap tidak boleh kosong.")

    # Check for duplicate username
    existing = get_user_by_username(supabase, clean_user)
    if existing:
        raise ValueError(f"Username '{clean_user}' sudah digunakan.")

    pwd_hash = hash_password(clean_pass)
    now_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "username": clean_user,
        "password_hash": pwd_hash,
        "role": "student",
        "full_name": clean_name,
        "device_id": device_id.strip().upper() if device_id else None,
        "created_at": now_iso,
    }

    res = supabase.table("app_users").insert(payload).execute()
    created = res.data[0] if isinstance(res.data, list) else res.data
    created_copy = dict(created)
    created_copy.pop("password_hash", None)
    return created_copy


def can_access_page(role: str, page_name: str) -> bool:
    """
    Determines if a given user role is permitted to view a page.
    Admin has full access to all pages.
    Student can access monitoring and their dedicated dashboard.
    """
    norm_role = (role or "").strip().lower()
    clean_page = (page_name or "").strip().lower()

    if norm_role == "admin":
        return True

    if norm_role in ["student", "siswa"]:
        allowed_pages = [
            "app.py",
            "1_monitoring_parkir.py",
            "5_dashboard_siswa.py",
        ]
        return any(allowed in clean_page for allowed in allowed_pages)

    return False


def get_all_users(supabase: Any) -> list:
    """
    Retrieves all registered application users from app_users with password_hash removed.
    """
    res = supabase.table("app_users").select("*").order("id").execute()
    data = res.data if res.data else []
    safe_users = []
    for u in data:
        u_copy = dict(u)
        u_copy.pop("password_hash", None)
        safe_users.append(u_copy)
    return safe_users


def update_user_role(supabase: Any, username: str, new_role: str) -> dict:
    """
    Updates the role of a user ('admin' or 'student').
    """
    clean_role = (new_role or "").strip().lower()
    if clean_role not in ["admin", "student"]:
        raise ValueError(f"Peran tidak valid: '{new_role}'. Harus 'admin' atau 'student'.")

    clean_user = (username or "").strip().lower()
    user = get_user_by_username(supabase, clean_user)
    if not user:
        raise ValueError(f"Pengguna dengan username '{clean_user}' tidak ditemukan.")

    res = supabase.table("app_users").update({"role": clean_role}).eq("username", clean_user).execute()
    updated = res.data[0] if isinstance(res.data, list) else res.data
    up_copy = dict(updated)
    up_copy.pop("password_hash", None)
    return up_copy


def update_user_device(supabase: Any, username: str, device_id: Optional[str]) -> dict:
    """
    Updates the linked IoT device_id for a user account.
    """
    clean_user = (username or "").strip().lower()
    user = get_user_by_username(supabase, clean_user)
    if not user:
        raise ValueError(f"Pengguna dengan username '{clean_user}' tidak ditemukan.")

    clean_dev = device_id.strip().upper() if device_id else None
    res = supabase.table("app_users").update({"device_id": clean_dev}).eq("username", clean_user).execute()
    updated = res.data[0] if isinstance(res.data, list) else res.data
    up_copy = dict(updated)
    up_copy.pop("password_hash", None)
    return up_copy


def reset_user_password(supabase: Any, username: str, new_password: str) -> dict:
    """
    Resets the password for a user account.
    """
    clean_pass = (new_password or "").strip()
    if len(clean_pass) < 6:
        raise ValueError("Password minimal 6 karakter.")

    clean_user = (username or "").strip().lower()
    user = get_user_by_username(supabase, clean_user)
    if not user:
        raise ValueError(f"Pengguna dengan username '{clean_user}' tidak ditemukan.")

    new_hash = hash_password(clean_pass)
    res = supabase.table("app_users").update({"password_hash": new_hash}).eq("username", clean_user).execute()
    updated = res.data[0] if isinstance(res.data, list) else res.data
    up_copy = dict(updated)
    up_copy.pop("password_hash", None)
    return up_copy


def delete_user(
    supabase: Any,
    username_to_delete: str,
    current_admin_username: Optional[str] = None
) -> bool:
    """
    Deletes a user account. Prevents the active administrator from deleting themselves.
    """
    del_user = (username_to_delete or "").strip().lower()
    if current_admin_username and del_user == current_admin_username.strip().lower():
        raise ValueError("Anda tidak dapat menghapus akun Anda sendiri.")

    user = get_user_by_username(supabase, del_user)
    if not user:
        raise ValueError(f"Pengguna '{del_user}' tidak ditemukan.")

    supabase.table("app_users").delete().eq("username", del_user).execute()
    return True


def update_user_profile(
    supabase: Any,
    username: str,
    full_name: Optional[str] = None,
    role: Optional[str] = None,
    device_id: Optional[str] = None,
) -> dict:
    """
    Updates a user profile's full_name, role, and linked device_id simultaneously.
    """
    clean_user = (username or "").strip().lower()
    user = get_user_by_username(supabase, clean_user)
    if not user:
        raise ValueError(f"Pengguna dengan username '{clean_user}' tidak ditemukan.")

    payload: Dict[str, Any] = {}
    if full_name is not None and full_name.strip():
        payload["full_name"] = full_name.strip()

    if role is not None:
        clean_role = role.strip().lower()
        if clean_role not in ["admin", "student"]:
            raise ValueError(f"Peran tidak valid: '{role}'. Harus 'admin' atau 'student'.")
        payload["role"] = clean_role

    if device_id is not None:
        clean_dev = device_id.strip().upper() if device_id and device_id != "(Tanpa Perangkat)" else None
        payload["device_id"] = clean_dev

    if not payload:
        return user

    res = supabase.table("app_users").update(payload).eq("username", clean_user).execute()
    updated = res.data[0] if isinstance(res.data, list) and res.data else user
    up_copy = dict(updated)
    up_copy.pop("password_hash", None)
    return up_copy


