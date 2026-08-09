"""Tests for auth_manager.py — token storage, refresh, expiration."""

import time
import pytest
from unittest.mock import MagicMock, patch

from auth_manager import AuthManager

@pytest.fixture(autouse=True)
def mock_keyring():
    fake_keyring = {}
    
    def mock_set(service, username, password):
        if service not in fake_keyring:
            fake_keyring[service] = {}
        fake_keyring[service][username] = password
        
    def mock_get(service, username):
        return fake_keyring.get(service, {}).get(username, None)
        
    def mock_delete(service, username):
        if service in fake_keyring and username in fake_keyring[service]:
            del fake_keyring[service][username]
            
    with patch("auth_manager.keyring.set_password", side_effect=mock_set), \
         patch("auth_manager.keyring.get_password", side_effect=mock_get), \
         patch("auth_manager.keyring.delete_password", side_effect=mock_delete):
        yield fake_keyring

class TestAuthManagerInit:
    def test_loads_empty_auth_data_when_no_config(self, mw_mock):
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: {}
        am = AuthManager()
        assert am.auth_data == {}

    def test_loads_existing_auth_data(self, mw_mock):
        auth_cfg = {"auth": {"token": "abc", "refresh_token": "ref"}}
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: dict(auth_cfg)
        am = AuthManager()
        am._load_auth_data()
        assert am.auth_data["token"] == "abc"


class TestStoreLoginResult:
    @pytest.fixture
    def am(self, mw_mock):
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: {}
        return AuthManager()

    def test_stores_token_and_refresh(self, am):
        result = am.store_login_result({
            "token": "tok_123",
            "refresh_token": "ref_456",
        })
        assert result is True
        assert am.auth_data["token"] == "tok_123"
        assert am.auth_data["refresh_token"] == "ref_456"

    def test_returns_false_on_none(self, am):
        assert am.store_login_result(None) is False

    def test_returns_false_on_empty_dict(self, am):
        # empty dict is falsy — should return False
        assert am.store_login_result({}) is False

    def test_stores_numeric_expires_at(self, am):
        future_ts = time.time() + 86400
        am.store_login_result({
            "token": "t",
            "refresh_token": "r",
            "expires_at": future_ts,
        })
        assert am.auth_data["expires_timestamp"] == pytest.approx(future_ts)

    def test_stores_iso_string_expires_at(self, am):
        am.store_login_result({
            "token": "t",
            "refresh_token": "r",
            "expires_at": "2099-01-01T00:00:00Z",
        })
        assert am.auth_data["expires_timestamp"] > time.time()

    def test_fallback_on_bad_expires(self, am):
        am.store_login_result({
            "token": "t",
            "refresh_token": "r",
            "expires_at": object(),  # invalid type
        })
        # Should fall back to 30-day window
        expected_min = time.time() + 29 * 86400
        assert am.auth_data["expires_timestamp"] >= expected_min


class TestShouldRefreshToken:
    @pytest.fixture
    def am(self, mw_mock):
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: {}
        return AuthManager()

    def test_no_expiry_returns_false(self, am):
        am.auth_data = {"token": "t"}
        assert am._should_refresh_token() is False

    def test_far_future_returns_false(self, am):
        am.auth_data = {"expires_timestamp": time.time() + 7 * 86400}
        assert am._should_refresh_token() is False

    def test_near_expiry_returns_true(self, am):
        am.auth_data = {"expires_timestamp": time.time() + 3600}  # 1 hour left
        assert am._should_refresh_token() is True

    def test_past_expiry_returns_true(self, am):
        am.auth_data = {"expires_timestamp": time.time() - 100}
        assert am._should_refresh_token() is True


class TestGetToken:
    @pytest.fixture
    def am(self, mw_mock):
        cfg = {"auth": {"token": "valid", "refresh_token": "r", "expires_timestamp": time.time() + 7 * 86400}}
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: dict(cfg)
        return AuthManager()

    def test_returns_token_when_valid(self, am):
        assert am.get_token() == "valid"

    def test_returns_empty_when_no_auth(self, mw_mock):
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: {}
        am = AuthManager()
        assert am.get_token() == ""

    @patch("auth_manager.requests.post")
    def test_auto_refreshes_near_expiry(self, mock_post, mw_mock):
        """get_token refreshes transparently when token is near expiry."""
        cfg = {"auth": {
            "token": "old_tok",
            "refresh_token": "ref",
            "expires_timestamp": time.time() + 100,  # < 1 day → triggers refresh
        }}
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: dict(cfg)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "token": "new_tok",
            "refresh_token": "new_ref",
            "expires_at": time.time() + 7 * 86400,
        }
        mock_post.return_value = mock_resp
        am = AuthManager()
        token = am.get_token()
        assert token == "new_tok"
        mock_post.assert_called_once()


class TestRefreshToken:
    @pytest.fixture
    def am(self, mw_mock):
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: {}
        am = AuthManager()
        am.auth_data = {"token": "old", "refresh_token": "ref_old"}
        return am

    @patch("auth_manager.requests.post")
    def test_refresh_success(self, mock_post, am):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "token": "new_tok",
            "refresh_token": "new_ref",
        }
        mock_post.return_value = mock_resp
        assert am.refresh_token() is True
        assert am.auth_data["token"] == "new_tok"

    @patch("auth_manager.requests.post")
    def test_refresh_failure(self, mock_post, am):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp
        assert am.refresh_token() is False

    @patch("auth_manager.requests.post", side_effect=Exception("network error"))
    def test_refresh_exception(self, mock_post, am):
        assert am.refresh_token() is False

    def test_refresh_no_refresh_token(self, am):
        am.auth_data = {}
        assert am.refresh_token() is False


class TestIsLoggedIn:
    def test_logged_in_with_valid_token(self, mw_mock):
        cfg = {"auth": {"token": "abc", "expires_timestamp": time.time() + 7 * 86400}}
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: dict(cfg)
        am = AuthManager()
        assert am.is_logged_in() is True

    def test_not_logged_in_without_token(self, mw_mock):
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: {}
        am = AuthManager()
        assert am.is_logged_in() is False


class TestAutoApprove:
    @pytest.fixture
    def am(self, mw_mock):
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: {"auth": {}}
        return AuthManager()

    def test_default_false(self, am):
        assert am.get_auto_approve() is False

    def test_set_and_get(self, am, mw_mock):
        am.set_auto_approve(True)
        assert am.auth_data["auto_approve"] is True


class TestLogout:
    @patch("auth_manager.requests.post")
    def test_logout_clears_data(self, mock_post, mw_mock):
        cfg = {"auth": {"token": "t", "refresh_token": "r"}}
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: dict(cfg)
        mock_post.return_value = MagicMock(status_code=200)
        am = AuthManager()
        am.logout()
        assert am.auth_data == {}

    @patch("auth_manager.requests.post")
    def test_logout_sends_bearer_header(self, mock_post, mw_mock):
        cfg = {"auth": {"token": "my_secret_token"}}
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: dict(cfg)
        mock_post.return_value = MagicMock(status_code=200)
        am = AuthManager()
        am._load_auth_data()
        am.logout()
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["headers"]["Authorization"] == "Bearer my_secret_token"
        assert "/removeToken" in call_kwargs[0][0]

    @patch("auth_manager.requests.post", side_effect=Exception("network"))
    def test_logout_succeeds_even_on_network_error(self, mock_post, mw_mock):
        cfg = {"auth": {"token": "t"}}
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: dict(cfg)
        am = AuthManager()
        am.logout()
        assert am.auth_data == {}

class TestKeyringStorage:
    @patch('auth_manager.keyring.set_password')
    @patch('auth_manager.keyring.get_password')
    def test_keyring_storage(self, mock_get_pw, mock_set_pw, mw_mock):
        """Test that tokens are stored and retrieved via keyring and not plain text."""
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: {"auth": {"expires_timestamp": time.time() + 7 * 86400}}
        am = AuthManager()
        am.store_login_result({
            "token": "secret_token",
            "refresh_token": "secret_refresh",
            "expires_at": time.time() + 86400
        })
        
        # Should be called
        mock_set_pw.assert_any_call("AnkiCollab", "token", "secret_token")
        mock_set_pw.assert_any_call("AnkiCollab", "refresh_token", "secret_refresh")
        
        # But NOT saved in config
        write_call = mw_mock.addonManager.writeConfig.call_args
        if write_call:
            saved_auth = write_call.args[1]["auth"]
            assert "token" not in saved_auth
            assert "refresh_token" not in saved_auth
        
        am.auth_data = getattr(am, 'auth_data', {})
        if "token" in am.auth_data:
            del am.auth_data["token"]
        
        mock_get_pw.side_effect = lambda s, u: "secret_token" if u == "token" else "secret_refresh"
        assert am.get_token() == "secret_token"
        
    @patch('auth_manager.keyring.set_password', side_effect=Exception("keyring locked"))
    @patch('auth_manager.aqt.utils.showInfo')
    def test_keyring_fails_aborts(self, mock_showInfo, mock_set_pw, mw_mock):
        mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: {"auth": {}}
        am = AuthManager()
        with pytest.raises(Exception, match="keyring locked"):
            am.store_login_result({
                "token": "secret",
                "refresh_token": "secret"
            })
            
        assert mock_showInfo.called
        assert "storage" in mock_showInfo.call_args.args[0].lower()