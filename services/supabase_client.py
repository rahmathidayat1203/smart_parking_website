"""
Supabase client factory and configuration helper.
Handles connection to Supabase PostgreSQL, environment variable loading,
and mock fallback for offline testing or demonstration.
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Try importing supabase create_client, handle gracefully if mock needed
try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None

load_dotenv()

_supabase_client: Optional[object] = None


def is_supabase_configured() -> bool:
    """
    Checks if SUPABASE_URL and SUPABASE_KEY are configured in the environment
    and are not empty.
    """
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    return bool(url and key)


def get_supabase_client(require_real: bool = False, use_mock: bool = False, options: Optional[object] = None):
    """
    Retrieves or initializes a singleton Supabase client instance.
    If require_real is True, raises ValueError when URL or KEY is missing.
    If use_mock is True, returns an in-memory mock client.
    """
    global _supabase_client

    if use_mock:
        from tests.conftest import MockSupabaseClient
        return MockSupabaseClient()

    if _supabase_client is not None:
        return _supabase_client

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()

    if not url:
        if require_real:
            raise ValueError("SUPABASE_URL is not set in environment")
        from tests.conftest import MockSupabaseClient
        return MockSupabaseClient()

    if not key:
        if require_real:
            raise ValueError("SUPABASE_KEY is not set in environment")
        from tests.conftest import MockSupabaseClient
        return MockSupabaseClient()

    if create_client is not None:
        if options is not None:
            _supabase_client = create_client(url, key, options=options)
        else:
            _supabase_client = create_client(url, key)
        return _supabase_client
    else:
        from tests.conftest import MockSupabaseClient
        return MockSupabaseClient()


def reset_supabase_client():
    """Resets the singleton client instance (useful for testing)."""
    global _supabase_client
    _supabase_client = None
