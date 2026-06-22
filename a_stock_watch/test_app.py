import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module
from app import DEFAULT_HOST, DEFAULT_PORT, get_auth_config, get_bind_host, get_bind_port, verify_basic_auth_header


class AppTest(unittest.TestCase):
    def test_default_server_bind_address(self):
        self.assertEqual(DEFAULT_HOST, "127.0.0.1")
        self.assertEqual(DEFAULT_PORT, 16666)

    def test_server_bind_can_be_configured_for_public_deploy(self):
        with patch.dict("os.environ", {"APP_HOST": "0.0.0.0", "APP_PORT": "18080"}):
            self.assertEqual(get_bind_host(), "0.0.0.0")
            self.assertEqual(get_bind_port(), 18080)

    def test_basic_auth_header_verification(self):
        self.assertTrue(verify_basic_auth_header("Basic YWRtaW46c2VjcmV0", "admin", "secret"))
        self.assertFalse(verify_basic_auth_header("Basic YWRtaW46d3Jvbmc=", "admin", "secret"))

    def test_auth_config_requires_username_and_password_pair(self):
        with patch.dict("os.environ", {"APP_USERNAME": "admin", "APP_PASSWORD": "secret"}):
            self.assertEqual(get_auth_config(), ("admin", "secret"))

    def test_monitor_control_endpoints_call_runtime(self):
        with patch("app._state_payload", return_value={"running": False}), patch("app.runtime") as runtime:
            self.assertEqual(app_module.stop_monitor(), {"running": False})
            runtime.stop.assert_called_once()
            runtime.add_event.assert_called_once_with("INFO", "已手动停止监控后台")

        with patch("app._state_payload", return_value={"running": True}), patch("app.runtime") as runtime:
            self.assertEqual(app_module.start_monitor(), {"running": True})
            runtime.start.assert_called_once()
            runtime.add_event.assert_called_once_with("INFO", "已手动启动监控后台")

    def test_static_page_contains_edit_and_monitor_controls(self):
        html = app_module.INDEX_PATH.read_text(encoding="utf-8")

        self.assertIn('id="monitorToggleButton"', html)
        self.assertIn("data-edit", html)
        self.assertIn("/api/monitor/stop", html)
        self.assertIn("/api/monitor/start", html)

    def test_static_page_uses_settings_drawer_without_top_webhook_status(self):
        html = app_module.INDEX_PATH.read_text(encoding="utf-8")

        self.assertIn('id="configButton"', html)
        self.assertIn('id="settingsDrawer"', html)
        self.assertIn('data-settings-tab="watchlist"', html)
        self.assertIn('data-settings-tab="webhook"', html)
        self.assertIn('id="webhookConfigStatus"', html)
        self.assertNotIn('id="webhookStatus"', html)

    def test_watch_item_save_preserves_existing_priority_and_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "watchlist:",
                        "  - name: 沪电股份",
                        "    code: 002463.SZ",
                        "    market: SZ",
                        "    buy_low: 142.0",
                        "    buy_high: 144.0",
                        "    shares: 100",
                        "    type: AI_PCB核心",
                        "    priority: 7",
                        "    enabled: false",
                    ]
                ),
                encoding="utf-8",
            )

            with patch("app.CONFIG_PATH", config_path):
                item = app_module._build_watch_item_for_save(
                    {
                        "name": "沪电股份",
                        "code": "002463.SZ",
                        "buy_low": "143",
                        "buy_high": "145",
                        "shares": "200",
                    }
                )

        self.assertEqual(item["priority"], 7)
        self.assertFalse(item["enabled"])
        self.assertEqual(item["buy_low"], 143.0)
        self.assertEqual(item["shares"], 200)


if __name__ == "__main__":
    unittest.main()
