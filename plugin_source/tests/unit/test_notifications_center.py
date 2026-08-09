"""Tests for notifications_center.py — polling, badge text, mark-read,
dialog payload rendering, and URL-scheme navigation interception.
"""

import json
import pytest
from unittest.mock import MagicMock, patch, call

from notifications_center import (
    NotificationCenterManager,
    NotificationCenterDialog,
    _UnreadFetchThread,
    _CenterFetchThread,
    _NotificationPage,
    _POLL_INTERVAL_MS,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _make_unread_payload(count=3, groups=None):
    """Build a minimal unread payload dict."""
    if groups is None:
        groups = [
            {
                "deck": "TestDeck",
                "notifications": [
                    {"id": i, "commit_id": 100 + i, "event_type": "field_updated"}
                    for i in range(1, count + 1)
                ],
            }
        ]
    return {"ok": True, "unread_count": count, "groups": groups}


def _make_history_payload(items=None):
    """Build a minimal history payload dict."""
    if items is None:
        items = []
    return {"total": len(items), "offset": 0, "limit": 200, "items": items}


# ──────────────────────────────────────────────────────────────────────
# Badge text (_set_unread_count)
# ──────────────────────────────────────────────────────────────────────

class TestUnreadBadge:
    @pytest.fixture
    def manager(self):
        mgr = NotificationCenterManager()
        mgr._action = MagicMock()
        return mgr

    @pytest.mark.parametrize(
        "count, expected_label",
        [
            (0, "Notifications"),
            (1, "Notifications (1)"),
            (5, "Notifications (5)"),
            (10, "Notifications (10)"),
            (11, "Notifications (10+)"),
            (50, "Notifications (10+)"),
            (99, "Notifications (10+)"),
            (100, "Notifications (^_^)"),
            (999, "Notifications (^_^)"),
        ],
    )
    def test_badge_label(self, manager, count, expected_label):
        manager._set_unread_count(count)
        manager._action.setText.assert_called_with(expected_label)

    def test_negative_count_clamps_to_zero(self, manager):
        manager._set_unread_count(-5)
        manager._action.setText.assert_called_with("Notifications")

    def test_no_action_does_not_raise(self):
        mgr = NotificationCenterManager()
        mgr._action = None
        mgr._set_unread_count(5)  # should be a no-op


# ──────────────────────────────────────────────────────────────────────
# schedule_refresh — guards and thread spawning
# ──────────────────────────────────────────────────────────────────────

class TestScheduleRefresh:
    @pytest.fixture
    def manager(self):
        mgr = NotificationCenterManager()
        mgr._action = MagicMock()
        return mgr

    @patch("notifications_center.auth_manager")
    def test_skips_when_not_logged_in(self, mock_auth, manager):
        mock_auth.is_logged_in.return_value = False
        manager.schedule_refresh()
        assert manager._fetch_thread is None
        manager._action.setText.assert_called_with("Notifications")

    @patch("notifications_center._UnreadFetchThread")
    @patch("notifications_center.auth_manager")
    def test_spawns_thread_when_logged_in(self, mock_auth, MockThread, manager):
        mock_auth.is_logged_in.return_value = True
        thread_instance = MagicMock()
        MockThread.return_value = thread_instance

        manager.schedule_refresh()

        MockThread.assert_called_once()
        thread_instance.fetched.connect.assert_called_once_with(manager._on_unread_fetched)
        thread_instance.start.assert_called_once()

    @patch("notifications_center.auth_manager")
    def test_does_not_spawn_second_thread_while_running(self, mock_auth, manager):
        mock_auth.is_logged_in.return_value = True
        running_thread = MagicMock()
        running_thread.isRunning.return_value = True
        manager._fetch_thread = running_thread

        manager.schedule_refresh()
        # The existing thread should not be replaced
        assert manager._fetch_thread is running_thread


# ──────────────────────────────────────────────────────────────────────
# _on_unread_fetched callback
# ──────────────────────────────────────────────────────────────────────

class TestOnUnreadFetched:
    def test_stores_payload_and_updates_badge(self):
        mgr = NotificationCenterManager()
        mgr._action = MagicMock()
        payload = _make_unread_payload(count=7)

        mgr._on_unread_fetched(payload)

        assert mgr._unread_payload is payload
        mgr._action.setText.assert_called_with("Notifications (7)")


# ──────────────────────────────────────────────────────────────────────
# attach — menu integration and poll timer
# ──────────────────────────────────────────────────────────────────────

class TestAttach:
    def test_creates_action_and_timer(self, mw_mock):
        mgr = NotificationCenterManager()
        parent_menu = MagicMock()

        mgr.attach(parent_menu)

        parent_menu.addAction.assert_called_once()
        action = mgr._action
        assert action is not None
        assert mgr._poll_timer is not None
        assert mgr._menu_attached is True

    def test_attach_is_idempotent(self, mw_mock):
        mgr = NotificationCenterManager()
        parent_menu = MagicMock()

        mgr.attach(parent_menu)
        mgr.attach(parent_menu)

        parent_menu.addAction.assert_called_once()


# ──────────────────────────────────────────────────────────────────────
# set_visible
# ──────────────────────────────────────────────────────────────────────

class TestSetVisible:
    def test_delegates_to_action(self):
        mgr = NotificationCenterManager()
        mgr._action = MagicMock()
        mgr.set_visible(False)
        mgr._action.setVisible.assert_called_with(False)

    def test_no_action_does_not_raise(self):
        mgr = NotificationCenterManager()
        mgr._action = None
        mgr.set_visible(True)  # no-op


# ──────────────────────────────────────────────────────────────────────
# _mark_as_read — collects IDs and POSTs
# ──────────────────────────────────────────────────────────────────────

class TestMarkAsRead:
    @patch("notifications_center.api_client")
    def test_posts_all_notification_ids(self, mock_api):
        mgr = NotificationCenterManager()
        payload = {
            "unread": {
                "groups": [
                    {"notifications": [{"id": 10}, {"id": 20}]},
                    {"notifications": [{"id": 30}]},
                ]
            }
        }

        mgr._mark_as_read(payload)

        mock_api.post_json.assert_called_once_with(
            "/MarkNotificationsRead",
            {"ids": [10, 20, 30]},
            timeout=10,
            auth=True,
        )

    @patch("notifications_center.api_client")
    def test_skips_post_when_no_ids(self, mock_api):
        mgr = NotificationCenterManager()
        mgr._mark_as_read({"unread": {"groups": []}})
        mock_api.post_json.assert_not_called()

    @patch("notifications_center.api_client")
    def test_skips_non_int_ids(self, mock_api):
        mgr = NotificationCenterManager()
        payload = {
            "unread": {
                "groups": [
                    {"notifications": [{"id": "bad"}, {"id": None}, {"id": 42}]},
                ]
            }
        }
        mgr._mark_as_read(payload)
        mock_api.post_json.assert_called_once_with(
            "/MarkNotificationsRead",
            {"ids": [42]},
            timeout=10,
            auth=True,
        )

    @patch("notifications_center.api_client")
    def test_handles_non_dict_payload_gracefully(self, mock_api):
        mgr = NotificationCenterManager()
        mgr._mark_as_read(None)
        mock_api.post_json.assert_not_called()

    @patch("notifications_center.api_client")
    def test_swallows_api_exception(self, mock_api):
        mock_api.post_json.side_effect = ConnectionError("offline")
        mgr = NotificationCenterManager()
        payload = {"unread": {"groups": [{"notifications": [{"id": 1}]}]}}
        mgr._mark_as_read(payload)  # should not raise


# ──────────────────────────────────────────────────────────────────────
# open_center — login gate and re-use
# ──────────────────────────────────────────────────────────────────────

class TestOpenCenter:
    @patch("notifications_center.showInfo")
    @patch("notifications_center.auth_manager")
    def test_shows_info_when_not_logged_in(self, mock_auth, mock_show):
        mock_auth.is_logged_in.return_value = False
        mgr = NotificationCenterManager()
        mgr.open_center()
        mock_show.assert_called_once()

    @patch("notifications_center.auth_manager")
    def test_raises_existing_dialog(self, mock_auth):
        mock_auth.is_logged_in.return_value = True
        mgr = NotificationCenterManager()
        dialog = MagicMock()
        mgr._center_dialog = dialog

        mgr.open_center()

        dialog.raise_.assert_called_once()
        dialog.activateWindow.assert_called_once()


# ──────────────────────────────────────────────────────────────────────
# _refresh_center_payload — thread guard
# ──────────────────────────────────────────────────────────────────────

class TestRefreshCenterPayload:
    @patch("notifications_center._CenterFetchThread")
    def test_spawns_center_thread(self, MockThread):
        mgr = NotificationCenterManager()
        mgr._center_dialog = MagicMock()
        thread_instance = MagicMock()
        MockThread.return_value = thread_instance

        mgr._refresh_center_payload()

        MockThread.assert_called_once()
        thread_instance.start.assert_called_once()
        mgr._center_dialog.set_loading.assert_called_with(True)

    @patch("notifications_center._CenterFetchThread")
    def test_does_not_spawn_while_running(self, MockThread):
        mgr = NotificationCenterManager()
        running = MagicMock()
        running.isRunning.return_value = True
        mgr._center_fetch_thread = running

        mgr._refresh_center_payload()

        MockThread.assert_not_called()


# ──────────────────────────────────────────────────────────────────────
# _on_center_payload callback
# ──────────────────────────────────────────────────────────────────────

class TestOnCenterPayload:
    def test_forwards_to_dialog(self):
        mgr = NotificationCenterManager()
        dialog = MagicMock()
        mgr._center_dialog = dialog
        payload = {"unread": {}, "history": {}, "commit_snapshots": {}}

        mgr._on_center_payload(payload)

        dialog.update_payload.assert_called_once_with(payload, loading=False)

    def test_no_dialog_does_not_raise(self):
        mgr = NotificationCenterManager()
        mgr._center_dialog = None
        mgr._on_center_payload({})  # should be a no-op


# ──────────────────────────────────────────────────────────────────────
# NotificationCenterDialog — payload rendering
# ──────────────────────────────────────────────────────────────────────

class TestDialogPayload:
    @pytest.fixture
    def dialog(self, mw_mock):
        """Create a dialog with a mock web view, simulating load completion."""
        d = NotificationCenterDialog(
            unread_payload={"unread_count": 0, "groups": []},
            history_payload=_make_history_payload(),
            commit_snapshots={},
            parent=None,
            loading=False,
        )
        # Simulate web load completion
        d._web = MagicMock()
        d._web.page.return_value = MagicMock()
        d._web_loaded = True
        return d

    def test_render_calls_javascript(self, dialog):
        dialog._render_payload()

        page = dialog._web.page()
        page.runJavaScript.assert_called_once()
        script = page.runJavaScript.call_args[0][0]
        assert "window.AnkiCollabNotifications.render(" in script

    def test_render_escapes_line_separators(self, dialog, mw_mock):
        dialog._payload["unread"] = {"text": "a\u2028b\u2029c"}
        dialog._render_payload()

        page = dialog._web.page()
        script = page.runJavaScript.call_args[0][0]
        assert "\u2028" not in script
        assert "\u2029" not in script
        assert "\\u2028" in script
        assert "\\u2029" in script

    def test_render_skipped_when_not_loaded(self, mw_mock):
        d = NotificationCenterDialog(
            unread_payload={}, history_payload={}, commit_snapshots={},
        )
        d._web = MagicMock()
        d._web_loaded = False  # not loaded yet

        d._render_payload()
        d._web.page.assert_not_called()

    def test_render_skipped_when_no_web(self, mw_mock):
        d = NotificationCenterDialog(
            unread_payload={}, history_payload={}, commit_snapshots={},
        )
        d._web = None
        d._render_payload()  # should not raise

    def test_update_payload_merges_and_renders(self, dialog, mw_mock):
        new_data = {
            "unread": {"unread_count": 5, "groups": []},
            "history": {"total": 1, "offset": 0, "limit": 200, "items": [{"id": 1}]},
            "commit_snapshots": {"999": {"events": []}},
        }
        dialog.update_payload(new_data, loading=False)

        assert dialog._payload["unread"]["unread_count"] == 5
        assert dialog._payload["history"]["items"] == [{"id": 1}]
        assert "999" in dialog._payload["commit_snapshots"]
        assert dialog._payload["loading"] is False

    def test_last_payload_returns_current_state(self, dialog):
        assert isinstance(dialog.last_payload(), dict)
        assert "unread" in dialog.last_payload()

    def test_set_loading_updates_and_renders(self, dialog):
        dialog.set_loading(True)
        assert dialog._payload["loading"] is True
        dialog._web.page().runJavaScript.assert_called()


# ──────────────────────────────────────────────────────────────────────
# NotificationCenterDialog — _handle_refresh
# ──────────────────────────────────────────────────────────────────────

class TestDialogRefresh:
    def test_calls_on_refresh_callback(self, mw_mock):
        callback = MagicMock()
        d = NotificationCenterDialog(
            unread_payload={}, history_payload={}, commit_snapshots={},
            on_refresh=callback,
        )
        d._handle_refresh()
        callback.assert_called_once()

    def test_no_callback_does_not_raise(self, mw_mock):
        d = NotificationCenterDialog(
            unread_payload={}, history_payload={}, commit_snapshots={},
            on_refresh=None,
        )
        d._handle_refresh()  # no-op


# ──────────────────────────────────────────────────────────────────────
# NotificationCenterDialog — _handle_open_guid
# ──────────────────────────────────────────────────────────────────────

class TestDialogOpenGuid:
    @pytest.fixture
    def dialog(self, mw_mock):
        d = NotificationCenterDialog(
            unread_payload={}, history_payload={}, commit_snapshots={},
        )
        d.accept = MagicMock()
        return d

    def test_resolves_guid_and_opens_browser(self, dialog, mw_mock):
        mw_mock.col.db.scalar.return_value = 42

        url = MagicMock()
        url.query.return_value = "guid=abc123"

        dialog._handle_open_guid(url)

        mw_mock.col.db.scalar.assert_called_once_with(
            "SELECT id FROM notes WHERE guid = ?", "abc123"
        )
        dialog.accept.assert_called_once()

    def test_returns_early_when_no_collection(self, dialog, mw_no_col):
        url = MagicMock()
        url.query.return_value = "guid=abc123"

        dialog._handle_open_guid(url)
        # Should bail out early — accept never called
        dialog.accept.assert_not_called()

    def test_returns_early_when_guid_empty(self, dialog, mw_mock):
        url = MagicMock()
        url.query.return_value = "guid="

        dialog._handle_open_guid(url)
        mw_mock.col.db.scalar.assert_not_called()

    def test_returns_early_when_nid_not_found(self, dialog, mw_mock):
        mw_mock.col.db.scalar.return_value = None
        url = MagicMock()
        url.query.return_value = "guid=nonexistent"

        dialog._handle_open_guid(url)
        dialog.accept.assert_not_called()

    def test_swallows_db_exception(self, dialog, mw_mock):
        mw_mock.col.db.scalar.side_effect = Exception("db locked")
        url = MagicMock()
        url.query.return_value = "guid=abc123"

        dialog._handle_open_guid(url)  # should not raise
        dialog.accept.assert_not_called()


# ──────────────────────────────────────────────────────────────────────
# _NotificationPage — URL interception
# ──────────────────────────────────────────────────────────────────────

class TestNotificationPage:
    @pytest.fixture
    def page(self):
        if _NotificationPage is None:
            pytest.skip("QWebEnginePage not available")
        dialog = MagicMock()
        return _NotificationPage(dialog), dialog

    def test_intercepts_refresh_scheme(self, page):
        p, dialog = page
        url = MagicMock()
        url.scheme.return_value = "ankicollab-refresh"

        result = p.acceptNavigationRequest(url, None, True)

        assert result is False
        dialog._handle_refresh.assert_called_once()

    def test_intercepts_open_guid_scheme(self, page):
        p, dialog = page
        url = MagicMock()
        url.scheme.return_value = "ankicollab-open-guid"

        result = p.acceptNavigationRequest(url, None, True)

        assert result is False
        dialog._handle_open_guid.assert_called_once_with(url)

    def test_allows_normal_navigation(self, page):
        p, dialog = page
        url = MagicMock()
        url.scheme.return_value = "https"

        # MagicMock parent's acceptNavigationRequest returns a MagicMock,
        # just verify it doesn't call our handlers
        p.acceptNavigationRequest(url, None, True)
        dialog._handle_refresh.assert_not_called()
        dialog._handle_open_guid.assert_not_called()


# ──────────────────────────────────────────────────────────────────────
# _UnreadFetchThread.run
# ──────────────────────────────────────────────────────────────────────

class TestUnreadFetchThread:
    @patch("notifications_center.api_client")
    def test_successful_fetch(self, mock_api):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "unread_count": 3,
            "groups": [{"deck": "A", "notifications": []}],
        }
        mock_api.get.return_value = mock_resp

        thread = _UnreadFetchThread()
        thread.fetched = MagicMock()
        thread.run()

        mock_api.get.assert_called_once_with("/GetNotifications", auth=True, timeout=12)
        payload = thread.fetched.emit.call_args[0][0]
        assert payload["ok"] is True
        assert payload["unread_count"] == 3
        assert len(payload["groups"]) == 1

    @patch("notifications_center.api_client")
    def test_non_200_sets_ok_false(self, mock_api):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_api.get.return_value = mock_resp

        thread = _UnreadFetchThread()
        thread.fetched = MagicMock()
        thread.run()

        payload = thread.fetched.emit.call_args[0][0]
        assert payload["ok"] is False
        assert payload["unread_count"] == 0

    @patch("notifications_center.api_client")
    def test_exception_emits_default_payload(self, mock_api):
        mock_api.get.side_effect = ConnectionError("offline")

        thread = _UnreadFetchThread()
        thread.fetched = MagicMock()
        thread.run()

        payload = thread.fetched.emit.call_args[0][0]
        assert payload["ok"] is False
        assert payload["unread_count"] == 0
        assert payload["groups"] == []


# ──────────────────────────────────────────────────────────────────────
# _CenterFetchThread.run
# ──────────────────────────────────────────────────────────────────────

class TestCenterFetchThread:
    @patch("notifications_center.api_client")
    def test_fetches_all_endpoints(self, mock_api):
        unread_resp = MagicMock(status_code=200)
        unread_resp.json.return_value = {"unread_count": 1, "groups": []}

        history_resp = MagicMock(status_code=200)
        history_resp.json.return_value = {
            "total": 2, "offset": 0, "limit": 200,
            "items": [
                {"commit_id": 10, "event": "x"},
                {"commit_id": 20, "event": "y"},
            ],
        }

        snap_10 = MagicMock(status_code=200)
        snap_10.json.return_value = {"events": ["a"]}
        snap_20 = MagicMock(status_code=200)
        snap_20.json.return_value = {"events": ["b"]}

        def get_side_effect(path, **kw):
            if path == "/GetNotifications":
                return unread_resp
            if path.startswith("/GetNotificationsHistory"):
                return history_resp
            if path == "/GetCommitSnapshot/10":
                return snap_10
            if path == "/GetCommitSnapshot/20":
                return snap_20
            return MagicMock(status_code=404)

        mock_api.get.side_effect = get_side_effect

        thread = _CenterFetchThread()
        thread.fetched = MagicMock()
        thread.run()

        payload = thread.fetched.emit.call_args[0][0]
        assert payload["unread"]["unread_count"] == 1
        assert len(payload["history"]["items"]) == 2
        assert "10" in payload["commit_snapshots"]
        assert "20" in payload["commit_snapshots"]

    @patch("notifications_center.api_client")
    def test_deduplicates_commit_ids(self, mock_api):
        history_resp = MagicMock(status_code=200)
        history_resp.json.return_value = {
            "total": 3, "offset": 0, "limit": 200,
            "items": [
                {"commit_id": 10},
                {"commit_id": 10},
                {"commit_id": 10},
            ],
        }

        snapshot_resp = MagicMock(status_code=200)
        snapshot_resp.json.return_value = {"events": []}

        def get_side_effect(path, **kw):
            if path.startswith("/GetNotificationsHistory"):
                return history_resp
            if path.startswith("/GetCommitSnapshot"):
                return snapshot_resp
            return MagicMock(status_code=500)

        mock_api.get.side_effect = get_side_effect

        thread = _CenterFetchThread()
        thread.fetched = MagicMock()
        thread.run()

        # Should only fetch commit 10 once
        snapshot_calls = [
            c for c in mock_api.get.call_args_list
            if c[0][0].startswith("/GetCommitSnapshot")
        ]
        assert len(snapshot_calls) == 1

    @patch("notifications_center.api_client")
    def test_uses_unread_cache_when_provided(self, mock_api):
        cached = {"unread_count": 5, "groups": [{"deck": "cached"}]}

        # Make the fresh unread fetch fail
        def get_side_effect(path, **kw):
            if path == "/GetNotifications":
                return MagicMock(status_code=500)
            if path.startswith("/GetNotificationsHistory"):
                return MagicMock(status_code=200, json=MagicMock(
                    return_value={"total": 0, "items": []}
                ))
            return MagicMock(status_code=404)

        mock_api.get.side_effect = get_side_effect

        thread = _CenterFetchThread(unread_cache=cached)
        thread.fetched = MagicMock()
        thread.run()

        # Despite the 500, unread data should be from the fresh fetch attempt
        # (which failed), but the initial cache is used as the starting value
        # and only overwritten on success.  Since the 500 does NOT overwrite,
        # the cache should still be present.
        payload = thread.fetched.emit.call_args[0][0]
        assert payload["unread"]["unread_count"] == 5


# ──────────────────────────────────────────────────────────────────────
# Public convenience functions
# ──────────────────────────────────────────────────────────────────────

class TestPublicFunctions:
    @patch("notifications_center.notification_center")
    def test_init_calls_attach(self, mock_nc):
        from notifications_center import init_notification_center
        menu = MagicMock()
        init_notification_center(menu)
        mock_nc.attach.assert_called_once_with(menu)

    @patch("notifications_center.notification_center")
    def test_refresh_calls_schedule(self, mock_nc):
        from notifications_center import refresh_notifications
        refresh_notifications()
        mock_nc.schedule_refresh.assert_called_once()

    @patch("notifications_center.notification_center")
    def test_set_visibility_calls_set_visible(self, mock_nc):
        from notifications_center import set_notification_visibility
        set_notification_visibility(True)
        mock_nc.set_visible.assert_called_once_with(True)


# ──────────────────────────────────────────────────────────────────────
# register_sync_refresh_hook
# ──────────────────────────────────────────────────────────────────────

class TestSyncRefreshHook:
    @patch("notifications_center.notification_center")
    @patch("notifications_center.gui_hooks")
    def test_registers_hook(self, mock_hooks, mock_nc):
        from notifications_center import register_sync_refresh_hook
        register_sync_refresh_hook()
        mock_hooks.sync_did_finish.append.assert_called_once()

        # Invoke the registered callback and verify it calls schedule_refresh
        callback = mock_hooks.sync_did_finish.append.call_args[0][0]
        callback()
        mock_nc.schedule_refresh.assert_called_once()


# ──────────────────────────────────────────────────────────────────────
# Poll interval constant
# ──────────────────────────────────────────────────────────────────────

class TestConstants:
    def test_poll_interval_is_five_minutes(self):
        assert _POLL_INTERVAL_MS == 5 * 60 * 1000
