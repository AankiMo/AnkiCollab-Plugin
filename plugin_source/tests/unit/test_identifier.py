"""Tests for identifier.py — get_user_hash, subscribe, unsubscribe."""

import json
import pytest
from unittest.mock import MagicMock, patch


class TestGetUserHash:
    @patch("identifier.api_client")
    @patch("identifier.auth_manager")
    def test_returns_hash_on_success(self, mock_am, mock_api):
        mock_am.get_token.return_value = "valid_token"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = "user_hash_abc"
        mock_api.post_empty.return_value = mock_resp

        from identifier import get_user_hash
        result = get_user_hash()
        assert result == "user_hash_abc"
        mock_api.post_empty.assert_called_once_with("/GetUserHashFromToken")

    @patch("identifier.auth_manager")
    def test_returns_none_without_token(self, mock_am):
        mock_am.get_token.return_value = ""
        from identifier import get_user_hash
        assert get_user_hash() is None

    @patch("identifier.api_client")
    @patch("identifier.auth_manager")
    def test_returns_none_on_exception(self, mock_am, mock_api):
        mock_am.get_token.return_value = "tok"
        mock_api.post_empty.side_effect = Exception("network")
        from identifier import get_user_hash
        assert get_user_hash() is None

    @patch("identifier.api_client")
    @patch("identifier.auth_manager")
    def test_returns_none_on_non_200(self, mock_am, mock_api):
        mock_am.get_token.return_value = "tok"
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_api.post_empty.return_value = mock_resp
        from identifier import get_user_hash
        assert get_user_hash() is None


class TestSubscribeToDeck:
    @patch("identifier.api_client")
    @patch("identifier.auth_manager")
    def test_subscribe_success(self, mock_am, mock_api):
        mock_am.get_token.return_value = "valid_token"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_api.post_json.return_value = mock_resp

        from identifier import subscribe_to_deck
        assert subscribe_to_deck("deck_hash_123") is True
        mock_api.post_json.assert_called_once_with("/AddSubscription", {"deck_hash": "deck_hash_123"}, timeout=5)

    @patch("identifier.auth_manager")
    def test_subscribe_no_user_hash(self, mock_am):
        mock_am.get_token.return_value = ""
        from identifier import subscribe_to_deck
        assert subscribe_to_deck("deck") is False

    @patch("identifier.api_client")
    @patch("identifier.auth_manager")
    def test_subscribe_server_error(self, mock_am, mock_api):
        mock_am.get_token.return_value = "valid_token"
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_api.post_json.return_value = mock_resp
        from identifier import subscribe_to_deck
        assert subscribe_to_deck("deck") is False


class TestUnsubscribeFromDeck:
    @patch("identifier.api_client")
    @patch("identifier.auth_manager")
    def test_unsubscribe_success(self, mock_am, mock_api):
        mock_am.get_token.return_value = "valid_token"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_api.post_json.return_value = mock_resp

        from identifier import unsubscribe_from_deck
        assert unsubscribe_from_deck("deck_hash_123") is True
        mock_api.post_json.assert_called_once_with("/RemoveSubscription", {"deck_hash": "deck_hash_123"}, timeout=5)

    @patch("identifier.auth_manager")
    def test_unsubscribe_no_user_hash(self, mock_am):
        mock_am.get_token.return_value = ""
        from identifier import unsubscribe_from_deck
        assert unsubscribe_from_deck("deck") is False


class TestGetUserHashEdgeCases:
    @patch("identifier.api_client")
    @patch("identifier.auth_manager")
    def test_returns_none_on_json_decode_error(self, mock_am, mock_api):
        """get_user_hash returns None when response isn't valid JSON."""
        mock_am.get_token.return_value = "tok"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = json.JSONDecodeError("fail", "", 0)
        mock_api.post_empty.return_value = mock_resp
        from identifier import get_user_hash
        assert get_user_hash() is None

    @patch("identifier.api_client")
    @patch("identifier.auth_manager")
    def test_returns_none_on_empty_string_response(self, mock_am, mock_api):
        """get_user_hash returns None for whitespace-only response."""
        mock_am.get_token.return_value = "tok"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = "   "
        mock_api.post_empty.return_value = mock_resp
        from identifier import get_user_hash
        assert get_user_hash() is None

    @patch("identifier.api_client")
    @patch("identifier.auth_manager")
    def test_returns_none_on_non_string_response(self, mock_am, mock_api):
        """get_user_hash returns None when server returns a dict instead of string."""
        mock_am.get_token.return_value = "tok"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "unexpected"}
        mock_api.post_empty.return_value = mock_resp
        from identifier import get_user_hash
        assert get_user_hash() is None

    @patch("identifier.auth_manager")
    def test_returns_none_with_none_token(self, mock_am):
        """get_user_hash returns None when token is None (not just empty)."""
        mock_am.get_token.return_value = None
        from identifier import get_user_hash
        assert get_user_hash() is None


class TestSubscribeEdgeCases:
    @patch("identifier.api_client")
    @patch("identifier.auth_manager")
    def test_subscribe_with_none_token(self, mock_am, mock_api):
        mock_am.get_token.return_value = None
        from identifier import subscribe_to_deck
        assert subscribe_to_deck("deck") is False
        mock_api.post_json.assert_not_called()

    @patch("identifier.api_client")
    @patch("identifier.auth_manager")
    def test_unsubscribe_with_none_token(self, mock_am, mock_api):
        mock_am.get_token.return_value = None
        from identifier import unsubscribe_from_deck
        assert unsubscribe_from_deck("deck") is False
        mock_api.post_json.assert_not_called()
