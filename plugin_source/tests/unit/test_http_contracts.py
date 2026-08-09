"""
HTTP contract tests: verify the Python client sends requests that match
what the Rust backend (Axum) expects to receive.

Each test constructs the same payload the plugin code builds, fires it
through ``api_client``, and then inspects the outgoing HTTP request
(method, URL, headers, body) against the backend's struct definitions.

These are NOT end-to-end tests — they use ``requests-mock`` to intercept
all HTTP traffic so nothing leaves the machine.
"""

import base64
import gzip
import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

import requests_mock as rmock

from api_client import _ApiClient

# ── Backend struct field contracts ────────────────────────────────────
# Mirrors plugin-backend/src/structs.rs — kept in sync manually.
# If the backend adds/removes a required field, the corresponding test
# below must be updated.

SUBSCRIPTION_FIELDS = {"deck_hash"}  # SubscriptionRequest
SUBMIT_CHANGELOG_FIELDS = {"deck_hash", "changelog"}  # SubmitChangelog
CREATE_DECK_LINK_FIELDS = {"subscriber_deck_hash", "base_deck_hash"}
CREATE_NOTE_LINK_FIELDS = {"subscriber_deck_hash", "base_deck_hash", "note_guids"}
NOTE_REMOVAL_FIELDS = {"remote_deck", "note_guids", "commit_text", "force_overwrite"}
STATS_INFO_FIELDS = {"deck_hash", "review_history"}  # StatsInfo (gzip)
SUBMIT_CARD_FIELDS = {  # SubmitCardReq (gzip)
    "remote_deck", "deck_path", "new_name", "deck", "rationale",
    "commit_text", "force_overwrite",
}
CREATE_DECK_FIELDS = {"deck"}  # CreateDeckReq (gzip)
MEDIA_MANIFEST_FIELDS = {"deck_hash", "filenames"}  # MediaManifestRequest
MEDIA_BULK_CHECK_FIELDS = {"deck_hash", "files"}  # MediaBulkCheckRequest


# ── Helpers ───────────────────────────────────────────────────────────

TOKEN = "test_token_abc123"


@pytest.fixture
def client():
    """An _ApiClient whose _get_token always returns a valid token."""
    c = _ApiClient()
    with patch.object(c, "_get_token", return_value=TOKEN):
        yield c


def _decode_gzip_body(raw_body: str) -> dict:
    """Reverse the base64 → gunzip → JSON pipeline used by post_gzip."""
    return json.loads(gzip.decompress(base64.b64decode(raw_body)))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Contract tests — JSON endpoints (api_client.post_json)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestAddSubscription:
    """POST /AddSubscription — AuthenticatedUser + Json<SubscriptionRequest>"""

    def test_payload_matches_backend_struct(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok", status_code=200)
            payload = {"deck_hash": "abc123"}
            client.post_json("/AddSubscription", payload)

            sent = m.last_request.json()
            assert set(sent.keys()) == SUBSCRIPTION_FIELDS

    def test_sends_bearer_header(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            client.post_json("/AddSubscription", {"deck_hash": "x"})
            assert m.last_request.headers["Authorization"] == f"Bearer {TOKEN}"

    def test_method_is_post(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            client.post_json("/AddSubscription", {"deck_hash": "x"})
            assert m.last_request.method == "POST"

    def test_no_user_hash_in_payload(self, client):
        """Backend derives user_hash server-side; client must NOT send it."""
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            payload = {"deck_hash": "abc123"}
            client.post_json("/AddSubscription", payload)
            assert "user_hash" not in m.last_request.json()


class TestRemoveSubscription:
    """POST /RemoveSubscription — AuthenticatedUser + Json<SubscriptionRequest>"""

    def test_payload_matches_backend_struct(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            client.post_json("/RemoveSubscription", {"deck_hash": "xyz"})
            assert set(m.last_request.json().keys()) == SUBSCRIPTION_FIELDS

    def test_no_user_hash_in_payload(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            client.post_json("/RemoveSubscription", {"deck_hash": "xyz"})
            assert "user_hash" not in m.last_request.json()


class TestSubmitChangelog:
    """POST /submitChangelog — AuthenticatedUser + Json<SubmitChangelog>"""

    def test_payload_matches_backend_struct(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            payload = {"deck_hash": "h", "changelog": "Fixed typo"}
            client.post_json("/submitChangelog", payload)
            assert set(m.last_request.json().keys()) == SUBMIT_CHANGELOG_FIELDS

    def test_no_token_in_payload(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            payload = {"deck_hash": "h", "changelog": "text"}
            client.post_json("/submitChangelog", payload)
            assert "token" not in m.last_request.json()


class TestCreateDeckLink:
    """POST /CreateDeckLink — AuthenticatedUser + Json<CreateDeckLinkRequest>"""

    def test_payload_matches_backend_struct(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            payload = {"subscriber_deck_hash": "a", "base_deck_hash": "b"}
            client.post_json("/CreateDeckLink", payload)
            assert set(m.last_request.json().keys()) == CREATE_DECK_LINK_FIELDS

    def test_no_token_in_payload(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            payload = {"subscriber_deck_hash": "a", "base_deck_hash": "b"}
            client.post_json("/CreateDeckLink", payload)
            assert "token" not in m.last_request.json()


class TestCreateNewNoteLink:
    """POST /CreateNewNoteLink — AuthenticatedUser + Json<CreateNewNoteLinkRequest>"""

    def test_payload_matches_backend_struct(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            payload = {
                "subscriber_deck_hash": "s",
                "base_deck_hash": "b",
                "note_guids": ["g1", "g2"],
            }
            client.post_json("/CreateNewNoteLink", payload)
            assert set(m.last_request.json().keys()) == CREATE_NOTE_LINK_FIELDS

    def test_no_token_in_payload(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            payload = {"subscriber_deck_hash": "s", "base_deck_hash": "b", "note_guids": []}
            client.post_json("/CreateNewNoteLink", payload)
            assert "token" not in m.last_request.json()


class TestRequestRemoval:
    """POST /requestRemoval — Option<AuthenticatedUser> + Json<NoteRemovalReq>"""

    def test_payload_matches_backend_struct(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            payload = {
                "remote_deck": "hash",
                "note_guids": ["g1"],
                "commit_text": "removing",
                "force_overwrite": False,
            }
            client.post_json("/requestRemoval", payload)
            assert set(m.last_request.json().keys()) == NOTE_REMOVAL_FIELDS

    def test_no_token_in_payload(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            payload = {
                "remote_deck": "h",
                "note_guids": [],
                "commit_text": "",
                "force_overwrite": False,
            }
            client.post_json("/requestRemoval", payload)
            assert "token" not in m.last_request.json()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Contract tests — gzip endpoints (api_client.post_gzip)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestUploadDeckStats:
    """POST /UploadDeckStats — AuthenticatedUser + String (gzip body)
    
    Backend decompresses to StatsInfo { deck_hash, review_history }.
    """

    def test_decompressed_payload_matches_backend_struct(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, text="ok")
            data = {
                "deck_hash": "h123",
                "review_history": {
                    "DeckA": {
                        "guid1": {"retention": 85, "lapses": 2, "reps": 10}
                    }
                },
            }
            client.post_gzip("/UploadDeckStats", data)
            body = _decode_gzip_body(m.last_request.text)
            assert set(body.keys()) == STATS_INFO_FIELDS

    def test_no_user_hash_in_payload(self, client):
        """Backend derives user_hash from auth token — client must not send it."""
        with rmock.Mocker() as m:
            m.post(rmock.ANY, text="ok")
            data = {"deck_hash": "h", "review_history": {}}
            client.post_gzip("/UploadDeckStats", data)
            body = _decode_gzip_body(m.last_request.text)
            assert "user_hash" not in body

    def test_content_type_is_text_plain(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, text="ok")
            client.post_gzip("/UploadDeckStats", {"deck_hash": "h", "review_history": {}})
            assert m.last_request.headers["Content-Type"] == "text/plain"


class TestSubmitCard:
    """POST /submitCard — Option<AuthenticatedUser> + String (gzip body)
    
    Backend decompresses to SubmitCardReq.
    """

    def test_decompressed_payload_matches_backend_struct(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, text="ok")
            data = {
                "remote_deck": "hash",
                "deck_path": "Parent::Child",
                "new_name": "Child",
                "deck": '{"notes": []}',
                "rationale": 1,
                "commit_text": "update",
                "force_overwrite": False,
            }
            client.post_gzip("/submitCard", data)
            body = _decode_gzip_body(m.last_request.text)
            assert set(body.keys()) == SUBMIT_CARD_FIELDS

    def test_no_token_in_payload(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, text="ok")
            data = {
                "remote_deck": "h", "deck_path": "p", "new_name": "n",
                "deck": "{}", "rationale": 0, "commit_text": "", "force_overwrite": False,
            }
            client.post_gzip("/submitCard", data)
            body = _decode_gzip_body(m.last_request.text)
            assert "token" not in body


class TestCreateDeck:
    """POST /createDeck — AuthenticatedUser + String (gzip body)
    
    Backend decompresses to CreateDeckReq { deck }.
    """

    def test_decompressed_payload_matches_backend_struct(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, text="ok")
            data = {"deck": '{"notes": [], "name": "My Deck"}'}
            client.post_gzip("/createDeck", data)
            body = _decode_gzip_body(m.last_request.text)
            assert set(body.keys()) == CREATE_DECK_FIELDS

    def test_no_username_in_payload(self, client):
        """Backend now gets owner from AuthenticatedUser, not from payload."""
        with rmock.Mocker() as m:
            m.post(rmock.ANY, text="ok")
            data = {"deck": "{}"}
            client.post_gzip("/createDeck", data)
            body = _decode_gzip_body(m.last_request.text)
            assert "username" not in body


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Contract tests — empty-body endpoints (api_client.post_empty)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestCheckUserToken:
    """POST /CheckUserToken — Option<AuthenticatedUser> (no body needed)"""

    def test_sends_bearer_no_body(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json=True)
            client.post_empty("/CheckUserToken")
            assert m.last_request.headers["Authorization"] == f"Bearer {TOKEN}"
            assert m.last_request.body is None or m.last_request.body == b""

    def test_no_token_in_body(self, client):
        """Old endpoint accepted Json<TokenInfo>; new one uses header only."""
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json=True)
            client.post_empty("/CheckUserToken")
            body = m.last_request.body
            if body:
                parsed = json.loads(body) if isinstance(body, (str, bytes)) else body
                assert "token" not in parsed


class TestGetUserHashFromToken:
    """POST /GetUserHashFromToken — AuthenticatedUser (no body needed)"""

    def test_sends_bearer_no_body(self, client):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="abc123hash")
            client.post_empty("/GetUserHashFromToken")
            assert m.last_request.headers["Authorization"] == f"Bearer {TOKEN}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Contract tests — GET endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestGetMissingMedia:
    """GET /media/missing/{deck_hash} — AuthenticatedUser"""

    def test_sends_bearer_auth(self, client):
        with rmock.Mocker() as m:
            m.get(rmock.ANY, json=[])
            client.get("/media/missing/abc123", auth=True)
            assert m.last_request.headers["Authorization"] == f"Bearer {TOKEN}"

    def test_deck_hash_in_url_path(self, client):
        with rmock.Mocker() as m:
            m.get(rmock.ANY, json=[])
            client.get("/media/missing/my_deck_hash_42", auth=True)
            assert "/media/missing/my_deck_hash_42" in m.last_request.url


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Contract tests — removeToken (logout)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestRemoveToken:
    """POST /removeToken — AuthenticatedUser (header-only, no body)

    Previously GET /removeToken/{token} — now the token is in the
    Authorization header and the route is POST.
    """

    def test_uses_post_not_get(self):
        """Backend route is .route("/removeToken", post(remove_token))"""
        with rmock.Mocker() as m:
            m.post(rmock.ANY, text="ok")
            import requests
            requests.post(
                "https://example.com/removeToken",
                headers={"Authorization": f"Bearer {TOKEN}"},
                timeout=10,
            )
            assert m.last_request.method == "POST"

    def test_token_not_in_url_path(self):
        """Old route had token in path; new one must NOT."""
        with rmock.Mocker() as m:
            m.post(rmock.ANY, text="ok")
            import requests
            requests.post(
                "https://example.com/removeToken",
                headers={"Authorization": f"Bearer {TOKEN}"},
                timeout=10,
            )
            assert TOKEN not in m.last_request.path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Contract tests — login
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestLogin:
    """POST /login — Json<auth::Login>

    Backend changed from Form to Json extraction.
    """

    def test_sends_json_not_form_data(self):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json={"token": "t", "refresh_token": "r"})
            import requests
            payload = {"email": "user@test.com", "password": "pass123"}
            requests.post(
                "https://example.com/login",
                json=payload,
                timeout=10,
                verify=True,
            )
            assert m.last_request.headers["Content-Type"] == "application/json"
            body = m.last_request.json()
            assert "email" in body
            assert "password" in body


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Contract tests — fields that must NOT be sent (removed from structs.rs)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestRemovedFields:
    """Verify that payloads no longer contain fields removed from backend structs.
    
    These fields were removed in the security audit v2 migration:
    - token (from SubmitCardReq, NoteRemovalReq, SubmitChangelog, etc.)
    - user_hash (from SubscriptionRequest, StatsInfo)
    - username (from CreateDeckReq)
    - user_token (from MediaManifestRequest)
    """

    REMOVED_FIELDS = {"token", "user_hash", "username", "user_token"}

    @pytest.mark.parametrize("endpoint,payload", [
        ("/AddSubscription", {"deck_hash": "h"}),
        ("/RemoveSubscription", {"deck_hash": "h"}),
        ("/submitChangelog", {"deck_hash": "h", "changelog": "c"}),
        ("/CreateDeckLink", {"subscriber_deck_hash": "a", "base_deck_hash": "b"}),
        ("/CreateNewNoteLink", {"subscriber_deck_hash": "a", "base_deck_hash": "b", "note_guids": []}),
        ("/requestRemoval", {"remote_deck": "h", "note_guids": [], "commit_text": "", "force_overwrite": False}),
    ])
    def test_json_endpoints_no_removed_fields(self, client, endpoint, payload):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, json="ok")
            client.post_json(endpoint, payload)
            sent_keys = set(m.last_request.json().keys())
            assert sent_keys.isdisjoint(self.REMOVED_FIELDS), (
                f"{endpoint} still sends removed fields: {sent_keys & self.REMOVED_FIELDS}"
            )

    @pytest.mark.parametrize("endpoint,data", [
        ("/UploadDeckStats", {"deck_hash": "h", "review_history": {}}),
        ("/createDeck", {"deck": "{}"}),
        ("/submitCard", {
            "remote_deck": "h", "deck_path": "p", "new_name": "n",
            "deck": "{}", "rationale": 0, "commit_text": "", "force_overwrite": False,
        }),
    ])
    def test_gzip_endpoints_no_removed_fields(self, client, endpoint, data):
        with rmock.Mocker() as m:
            m.post(rmock.ANY, text="ok")
            client.post_gzip(endpoint, data)
            body = _decode_gzip_body(m.last_request.text)
            sent_keys = set(body.keys())
            assert sent_keys.isdisjoint(self.REMOVED_FIELDS), (
                f"{endpoint} still sends removed fields: {sent_keys & self.REMOVED_FIELDS}"
            )
