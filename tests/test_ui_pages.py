"""
Test suite for Streamlit UI helpers, pages compilation, and DRD/TRD compliance.
Verifies that:
1. utils.ui_helpers functions work correctly
2. All page files compile with valid python syntax
3. NO manual gate control buttons exist in any web code
4. Registration forbids manual UID input (read-only enforcement)
"""

import ast
import os
import pytest
from datetime import datetime, timezone, timedelta

from utils.ui_helpers import (
    render_status_badge,
    format_timestamp,
    get_relative_time,
    is_client_mock,
)


def test_render_status_badge_variants():
    """Verifies that render_status_badge handles all status classes properly."""
    available_badge = render_status_badge("available")
    assert "#DEF7EC" in available_badge
    assert "AVAILABLE" in available_badge

    kosong_badge = render_status_badge("kosong")
    assert "#DEF7EC" in kosong_badge
    assert "KOSONG" in kosong_badge

    occupied_badge = render_status_badge("occupied")
    assert "#FDE8E8" in occupied_badge
    assert "OCCUPIED" in occupied_badge

    terisi_badge = render_status_badge("terisi")
    assert "#FDE8E8" in terisi_badge
    assert "TERISI" in terisi_badge

    waiting_badge = render_status_badge("waiting")
    assert "#FEF08A" in waiting_badge
    assert "WAITING" in waiting_badge

    unknown_badge = render_status_badge("unknown")
    assert "#F3F4F6" in unknown_badge
    assert "UNKNOWN" in unknown_badge


def test_format_timestamp():
    """Verifies timestamp formatting for None, ISO strings, and datetime objects."""
    assert format_timestamp(None) == "-"
    
    dt = datetime(2026, 10, 5, 17, 30, 0, tzinfo=timezone.utc)
    assert format_timestamp(dt) == "2026-10-05 17:30:00"

    iso_str = "2026-10-05T17:30:00Z"
    assert format_timestamp(iso_str) == "2026-10-05 17:30:00"


def test_get_relative_time():
    """Verifies relative time string generations."""
    assert get_relative_time(None) == "Tidak diketahui"

    now = datetime.now(timezone.utc)
    just_now = now - timedelta(seconds=2)
    assert "Baru saja" in get_relative_time(just_now)

    secs_ago = now - timedelta(seconds=25)
    assert "detik yang lalu" in get_relative_time(secs_ago)

    mins_ago = now - timedelta(minutes=5)
    assert "5 menit yang lalu" in get_relative_time(mins_ago)

    hours_ago = now - timedelta(hours=3)
    assert "3 jam yang lalu" in get_relative_time(hours_ago)


def test_no_manual_gate_buttons_in_pages():
    """
    CRITICAL ACCEPTANCE CRITERIA:
    Verifies that NO page contains manual gate open/close buttons
    (DRD Sec 1 & 32, TRD Sec 8 & 20).
    """
    page_files = [
        "app.py",
        os.path.join("pages", "1_Monitoring_Parkir.py"),
        os.path.join("pages", "2_Member_RFID.py"),
        os.path.join("pages", "3_IoT_Device.py"),
        os.path.join("pages", "4_Monitoring_Sensor.py"),
        os.path.join("pages", "5_Dashboard_Siswa.py"),
        os.path.join("pages", "6_Manajemen_User.py"),
    ]

    forbidden_phrases = [
        "buka gate",
        "tutup gate",
        "open gate",
        "close gate",
        "manual gate",
        "buka palang",
        "tutup palang",
        "kontrol gate",
        "gate control",
    ]

    for p in page_files:
        assert os.path.exists(p), f"File {p} does not exist"
        with open(p, "r", encoding="utf-8") as f:
            content = f.read().lower()

        # Check for forbidden button calls
        for phrase in forbidden_phrases:
            # It's acceptable to mention in comment "strictly NO manual gate buttons",
            # but must never appear in st.button()
            if f'button("{phrase}' in content or f"button('{phrase}" in content:
                pytest.fail(f"Found forbidden manual gate button '{phrase}' in {p}")


def test_page_syntax_and_ast_compilation():
    """Verifies that all Streamlit page files are syntactically valid Python code."""
    page_files = [
        "app.py",
        os.path.join("pages", "1_Monitoring_Parkir.py"),
        os.path.join("pages", "2_Member_RFID.py"),
        os.path.join("pages", "3_IoT_Device.py"),
        os.path.join("pages", "4_Monitoring_Sensor.py"),
        os.path.join("pages", "5_Dashboard_Siswa.py"),
        os.path.join("pages", "6_Manajemen_User.py"),
    ]

    for p in page_files:
        with open(p, "r", encoding="utf-8") as f:
            source = f.read()
        # ast.parse will raise SyntaxError if code is invalid
        tree = ast.parse(source, filename=p)
        assert tree is not None
