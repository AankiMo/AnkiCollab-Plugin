"""Tests for api_client.py — _ApiClient unified request handler."""

import gzip
import base64
import json
import pytest
from unittest.mock import MagicMock, patch, call

from api_client import _ApiClient, api_client


class TestAuthHeaders:
    def test_returns_bearer_format(self):
        client = _ApiClient()
        headers = client._auth_headers("my_token_123")
        assert headers == {"Authorization": "Bearer my_token_123"}

    def test_empty_token_still_formats(self):
        client = _ApiClient()
        headers = client._auth_headers("")
        assert headers == {"Authorization": "Bearer "}


class TestPostJson:
    @patch("api_client.requests.request")
    @patch.object(_ApiClient, "_get_token", return_value="tok_abc")
    def test_sends_json_with_bearer_auth(self, mock_token, mock_request):
        mock_resp = MagicMock(status_code=200)
        mock_request.return_value = mock_resp

        client = _ApiClient()
        resp = client.post_json("/TestEndpoint", {"key": "val"})

        assert resp == mock_resp
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        assert args[0] == "POST"
        assert "/TestEndpoint" in args[1]
        assert kwargs["json"] == {"key": "val"}
        assert kwargs["headers"]["Authorization"] == "Bearer tok_abc"
        assert kwargs["headers"]["Content-Type"] == "application/json"
        assert kwargs["verify"] is True

    @patch("api_client.requests.request")
    @patch.object(_ApiClient, "_get_token", return_value="tok_abc")
    def test_default_timeout_is_30(self, mock_token, mock_request):
        mock_request.return_value = MagicMock()
        client = _ApiClient()
        client.post_json("/Ep", {})
        _, kwargs = mock_request.call_args
        assert kwargs["timeout"] == 30

    @patch("api_client.requests.request")
    @patch.object(_ApiClient, "_get_token", return_value="tok_abc")
    def test_custom_timeout(self, mock_token, mock_request):
        mock_request.return_value = MagicMock()
        client = _ApiClient()
        client.post_json("/Ep", {}, timeout=60)
        _, kwargs = mock_request.call_args
        assert kwargs["timeout"] == 60

    @patch("api_client.requests.request")
    def test_no_auth_skips_bearer_header(self, mock_request):
        mock_request.return_value = MagicMock()
        client = _ApiClient()
        client.post_json("/PublicEndpoint", {"x": 1}, auth=False)
        _, kwargs = mock_request.call_args
        assert "Authorization" not in kwargs["headers"]

    @patch.object(_ApiClient, "_get_token", return_value="")
    def test_raises_when_no_token(self, mock_token):
        client = _ApiClient()
        with pytest.raises(RuntimeError, match="Not logged in"):
            client.post_json("/NeedAuth", {})

    @patch("api_client.requests.request")
    @patch.object(_ApiClient, "_get_token", return_value="tok")
    def test_none_payload(self, mock_token, mock_request):
        mock_request.return_value = MagicMock()
        client = _ApiClient()
        client.post_json("/Ep", None)
        _, kwargs = mock_request.call_args
        assert kwargs["json"] is None


class TestPostGzip:
    @patch("api_client.requests.request")
    @patch.object(_ApiClient, "_get_token", return_value="gz_token")
    def test_sends_compressed_data_with_auth(self, mock_token, mock_request):
        mock_request.return_value = MagicMock(status_code=200)
        client = _ApiClient()
        payload = {"deck": "test_data", "notes": [1, 2, 3]}

        client.post_gzip("/createDeck", payload)

        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        assert args[0] == "POST"
        assert "/createDeck" in args[1]
        assert kwargs["headers"]["Authorization"] == "Bearer gz_token"
        assert kwargs["verify"] is True

        # Verify the data was actually gzip-compressed and base64 encoded
        sent_data = kwargs["data"]
        decoded = base64.b64decode(sent_data)
        decompressed = gzip.decompress(decoded)
        assert json.loads(decompressed) == payload

    @patch("api_client.requests.request")
    @patch.object(_ApiClient, "_get_token", return_value="tok")
    def test_default_timeout_is_120(self, mock_token, mock_request):
        mock_request.return_value = MagicMock()
        client = _ApiClient()
        client.post_gzip("/Ep", {"k": "v"})
        _, kwargs = mock_request.call_args
        assert kwargs["timeout"] == 120

    @patch.object(_ApiClient, "_get_token", return_value="")
    def test_raises_when_no_token(self, mock_token):
        client = _ApiClient()
        with pytest.raises(RuntimeError, match="Not logged in"):
            client.post_gzip("/Ep", {"k": "v"})


class TestGet:
    @patch("api_client.requests.request")
    def test_get_no_auth(self, mock_request):
        mock_request.return_value = MagicMock(status_code=200)
        client = _ApiClient()
        resp = client.get("/public/endpoint")
        assert resp.status_code == 200
        args, kwargs = mock_request.call_args
        assert args[0] == "GET"
        assert "Authorization" not in kwargs["headers"]
        assert kwargs["verify"] is True

    @patch("api_client.requests.request")
    @patch.object(_ApiClient, "_get_token", return_value="get_tok")
    def test_get_with_auth(self, mock_token, mock_request):
        mock_request.return_value = MagicMock(status_code=200)
        client = _ApiClient()
        client.get("/private/data", auth=True)
        _, kwargs = mock_request.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer get_tok"

    @patch.object(_ApiClient, "_get_token", return_value="")
    def test_get_with_auth_raises_when_no_token(self, mock_token):
        client = _ApiClient()
        with pytest.raises(RuntimeError, match="Not logged in"):
            client.get("/private", auth=True)


class TestPostEmpty:
    @patch("api_client.requests.request")
    @patch.object(_ApiClient, "_get_token", return_value="empty_tok")
    def test_sends_post_with_auth_no_body(self, mock_token, mock_request):
        mock_request.return_value = MagicMock(status_code=200)
        client = _ApiClient()
        resp = client.post_empty("/CheckUserToken")
        assert resp.status_code == 200
        _, kwargs = mock_request.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer empty_tok"
        assert kwargs["verify"] is True
        # No json or data parameter
        assert "json" not in kwargs
        assert "data" not in kwargs

    @patch.object(_ApiClient, "_get_token", return_value="")
    def test_raises_when_no_token(self, mock_token):
        client = _ApiClient()
        with pytest.raises(RuntimeError, match="Not logged in"):
            client.post_empty("/NeedAuth")


class TestSessionWithAuth:
    @patch.object(_ApiClient, "_get_token", return_value="session_tok")
    def test_returns_session_with_auth_header(self, mock_token):
        client = _ApiClient()
        session = client.session_with_auth()
        assert session.headers.get("Authorization") == "Bearer session_tok"

    @patch.object(_ApiClient, "_get_token", return_value="")
    def test_returns_session_without_auth_when_no_token(self, mock_token):
        client = _ApiClient()
        session = client.session_with_auth()
        assert "Authorization" not in session.headers

    @patch.object(_ApiClient, "_get_token", return_value="tok")
    def test_session_has_retry_adapters(self, mock_token):
        client = _ApiClient()
        session = client.session_with_auth()
        # Should have retry adapters mounted
        assert "https://" in session.adapters
        assert "http://" in session.adapters


class TestSingleton:
    def test_api_client_is_instance(self):
        assert isinstance(api_client, _ApiClient)
