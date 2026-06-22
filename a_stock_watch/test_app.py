import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
