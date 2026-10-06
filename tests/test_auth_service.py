"""
TDD Unit tests for Authentication & Role-Based Access Control (RBAC).
Tests password hashing, user authentication, student registration,
and page permission guards.
"""

import pytest
from services.auth_service import (
    hash_password,
    verify_password,
    authenticate_user,
    register_student_user,
    get_user_by_username,
    can_access_page,
)


def test_hash_and_verify_password():
    """Verify hashing produces consistent SHA-256 and matches correctly."""
    pwd = "mypassword123"
    hashed = hash_password(pwd)

    assert isinstance(hashed, str)
    assert len(hashed) == 64  # SHA-256 hex length
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrongpassword", hashed) is False
    assert verify_password("", hashed) is False


def test_authenticate_admin_success(mock_supabase):
    """Verify admin login with correct password."""
    user = authenticate_user(mock_supabase, "admin", "admin123")
    assert user is not None
    assert user["username"] == "admin"
    assert user["role"] == "admin"
    assert "Administrator" in user["full_name"]


def test_authenticate_student_success(mock_supabase):
    """Verify student login with correct password and bound device_id."""
    user = authenticate_user(mock_supabase, "siswa1", "siswa123")
    assert user is not None
    assert user["username"] == "siswa1"
    assert user["role"] == "student"
    assert user["device_id"] == "DEV-SISWA-01"


def test_authenticate_invalid_credentials(mock_supabase):
    """Verify failed logins for wrong password or missing user."""
    # Wrong password
    assert authenticate_user(mock_supabase, "admin", "wrongpassword") is None

    # Unknown user
    assert authenticate_user(mock_supabase, "nonexistent", "admin123") is None

    # Empty inputs
    assert authenticate_user(mock_supabase, "", "") is None
    assert authenticate_user(mock_supabase, "admin", "") is None


def test_register_student_account_success(mock_supabase):
    """Verify student account registration with device binding."""
    user = register_student_user(
        supabase=mock_supabase,
        username="siswa2",
        password="secretpassword",
        full_name="Dewi Lestari",
        device_id="DEV-SISWA-02",
    )

    assert user["username"] == "siswa2"
    assert user["role"] == "student"
    assert user["full_name"] == "Dewi Lestari"
    assert user["device_id"] == "DEV-SISWA-02"

    # Verify user can immediately log in
    logged_in = authenticate_user(mock_supabase, "siswa2", "secretpassword")
    assert logged_in is not None
    assert logged_in["username"] == "siswa2"


def test_register_student_account_validations(mock_supabase):
    """Verify validation errors during student registration."""
    # Empty username
    with pytest.raises(ValueError, match="Username tidak boleh kosong"):
        register_student_user(mock_supabase, "", "pass123", "Nama")

    # Short password
    with pytest.raises(ValueError, match="Password minimal 6 karakter"):
        register_student_user(mock_supabase, "siswa_short", "12345", "Nama")

    # Empty full name
    with pytest.raises(ValueError, match="Nama lengkap tidak boleh kosong"):
        register_student_user(mock_supabase, "siswa_noname", "pass1234", "")

    # Duplicate username
    with pytest.raises(ValueError, match="sudah digunakan"):
        register_student_user(mock_supabase, "admin", "pass1234", "Admin Duplicate")


def test_get_user_by_username(mock_supabase):
    """Verify fetching user by username."""
    admin = get_user_by_username(mock_supabase, "admin")
    assert admin is not None
    assert admin["role"] == "admin"

    missing = get_user_by_username(mock_supabase, "unknown_user")
    assert missing is None


def test_can_access_page_rbac():
    """Verify role-based access rules for Admin and Student."""
    # Admin can access all pages
    assert can_access_page("admin", "app.py") is True
    assert can_access_page("admin", "1_Monitoring_Parkir.py") is True
    assert can_access_page("admin", "2_Member_RFID.py") is True
    assert can_access_page("admin", "3_IoT_Device.py") is True
    assert can_access_page("admin", "4_Monitoring_Sensor.py") is True
    assert can_access_page("admin", "5_Dashboard_Siswa.py") is True
    assert can_access_page("admin", "6_Manajemen_User.py") is True

    # Student can access public monitoring and their dedicated dashboard
    assert can_access_page("student", "1_Monitoring_Parkir.py") is True
    assert can_access_page("student", "5_Dashboard_Siswa.py") is True

    # Student CANNOT access admin management pages
    assert can_access_page("student", "2_Member_RFID.py") is False
    assert can_access_page("student", "3_IoT_Device.py") is False
    assert can_access_page("student", "4_Monitoring_Sensor.py") is False
    assert can_access_page("student", "6_Manajemen_User.py") is False


def test_get_all_users(mock_supabase):
    """Verify admin can list all registered users with password_hash stripped."""
    from services.auth_service import get_all_users

    users = get_all_users(mock_supabase)
    assert len(users) >= 2
    for u in users:
        assert "password_hash" not in u
        assert "username" in u
        assert "role" in u


def test_update_user_role(mock_supabase):
    """Verify admin can change a user's role between student and admin."""
    from services.auth_service import update_user_role

    # Promote student to admin
    updated = update_user_role(mock_supabase, "siswa1", "admin")
    assert updated["role"] == "admin"

    # Demote back to student
    updated2 = update_user_role(mock_supabase, "siswa1", "student")
    assert updated2["role"] == "student"

    # Invalid role raises ValueError
    with pytest.raises(ValueError, match="Peran tidak valid"):
        update_user_role(mock_supabase, "siswa1", "superadmin_invalid")


def test_update_user_device(mock_supabase):
    """Verify admin can change or assign device_id for a user."""
    from services.auth_service import update_user_device

    updated = update_user_device(mock_supabase, "siswa1", "DEV-SISWA-99")
    assert updated["device_id"] == "DEV-SISWA-99"

    # Clear device
    cleared = update_user_device(mock_supabase, "siswa1", None)
    assert cleared["device_id"] is None


def test_reset_user_password(mock_supabase):
    """Verify admin can reset password for a user."""
    from services.auth_service import reset_user_password

    # Reset password for siswa1
    reset_user_password(mock_supabase, "siswa1", "newsecret123")

    # Verify old password fails
    assert authenticate_user(mock_supabase, "siswa1", "siswa123") is None

    # Verify new password succeeds
    user = authenticate_user(mock_supabase, "siswa1", "newsecret123")
    assert user is not None
    assert user["username"] == "siswa1"


def test_delete_user_and_self_protection(mock_supabase):
    """Verify admin can delete a user, but cannot delete themselves."""
    from services.auth_service import delete_user

    # Create temporary user
    register_student_user(mock_supabase, "tempuser", "temppass123", "Temp User")

    # Admin deletes temporary user
    success = delete_user(mock_supabase, username_to_delete="tempuser", current_admin_username="admin")
    assert success is True
    assert get_user_by_username(mock_supabase, "tempuser") is None

    # Admin cannot delete their own account
    with pytest.raises(ValueError, match="tidak dapat menghapus akun Anda sendiri"):
        delete_user(mock_supabase, username_to_delete="admin", current_admin_username="admin")

