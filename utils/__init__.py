"""
UI Helper utilities and components for Streamlit Smart Parking Application.
"""

from utils.ui_helpers import (
    get_app_supabase,
    render_status_badge,
    render_sidebar_branding,
    setup_auto_refresh,
    format_timestamp,
    get_relative_time,
    is_client_mock,
)

__all__ = [
    "get_app_supabase",
    "render_status_badge",
    "render_sidebar_branding",
    "setup_auto_refresh",
    "format_timestamp",
    "get_relative_time",
    "is_client_mock",
]
