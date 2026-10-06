"""
Unit tests for supabase_client module.
Tests cover:
- Client initialization with environment variables
- Clear error handling for missing SUPABASE_URL and SUPABASE_KEY
- Supabase configuration status checker
- Fallback/mock client handling during development or testing
"""

import os
from unittest.mock import patch, MagicMock
import pytest
from services.supabase_client import (
    get_supabase_client,
    is_supabase_configured,
    reset_supabase_client,
)


class TestSupabaseClientInitialization:
    """Test suite for Supabase client creation and configuration."""

    def test_is_supabase_configured_true(self):
        """Returns True when SUPABASE_URL and SUPABASE_KEY are provided and not dummy placeholders."""
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://xyzcompany.supabase.co",
            "SUPABASE_KEY": "valid-anon-key-12345"
        }):
            assert is_supabase_configured() is True

    def test_is_supabase_configured_false_when_missing(self):
        """Returns False when either URL or KEY is missing."""
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_KEY": ""}, clear=True):
            assert is_supabase_configured() is False

        with patch.dict(os.environ, {"SUPABASE_URL": "https://xyzcompany.supabase.co"}, clear=True):
            assert is_supabase_configured() is False

    def test_get_supabase_client_missing_url_raises_error(self):
        """Raises ValueError with a clear message when SUPABASE_URL is missing."""
        reset_supabase_client()
        with patch.dict(os.environ, {"SUPABASE_KEY": "valid-key"}, clear=True):
            with pytest.raises(ValueError, match="SUPABASE_URL is not set"):
                get_supabase_client(require_real=True)

    def test_get_supabase_client_missing_key_raises_error(self):
        """Raises ValueError with a clear message when SUPABASE_KEY is missing."""
        reset_supabase_client()
        with patch.dict(os.environ, {"SUPABASE_URL": "https://xyz.supabase.co"}, clear=True):
            with pytest.raises(ValueError, match="SUPABASE_KEY is not set"):
                get_supabase_client(require_real=True)

    @patch("services.supabase_client.create_client")
    def test_get_supabase_client_success_creates_instance(self, mock_create):
        """When credentials are valid, initializes the Supabase client."""
        reset_supabase_client()
        mock_instance = MagicMock()
        mock_create.return_value = mock_instance

        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://myproj.supabase.co",
            "SUPABASE_KEY": "mysecretkey"
        }):
            client = get_supabase_client()
            mock_create.assert_called_once_with("https://myproj.supabase.co", "mysecretkey")
            assert client == mock_instance

    def test_get_supabase_client_mock_fallback_mode(self):
        """When mock fallback mode is requested or in offline testing, returns mock client."""
        client = get_supabase_client(use_mock=True)
        assert client is not None
        assert hasattr(client, "table")
