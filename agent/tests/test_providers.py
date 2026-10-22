import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import providers


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.payload


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
    def tearDown(self):
        self.env.stop()

    def test_default_provider_is_local_ollama(self):
        status = providers.provider_status()
        self.assertEqual(status["provider"], "ollama")
        self.assertEqual(status["status"], "CONFIGURED_LOCAL")

    def test_deepseek_without_key_requires_auth(self):
        status = providers.provider_status("deepseek")
        self.assertEqual(status["status"], "AUTH_REQUIRED")
        self.assertFalse(status["credential_present"])

    def test_deepseek_request_uses_compatible_endpoint_and_auth(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-secret"
        os.environ["HF_AGENT_MODEL"] = "deepseek-chat"
        def fake_open(req, timeout=0):
            self.assertEqual(req.full_url, "https://api.deepseek.com/chat/completions")
            self.assertEqual(req.get_header("Authorization"), "Bearer test-secret")
            body = json.loads(req.data.decode("utf-8"))
            self.assertEqual(body["model"], "deepseek-chat")
            self.assertFalse(body["stream"])
            return FakeResponse({"choices": [{"message": {"content": "verified mock"}}]})
        with patch.object(providers.urllib.request, "urlopen", fake_open):
            answer = providers.provider_chat([{"role": "user", "content": "test"}],
                                             provider="deepseek")
        self.assertEqual(answer, "verified mock")

    def test_missing_key_fails_before_network(self):
        with patch.object(providers.urllib.request, "urlopen") as open_mock:
            with self.assertRaises(providers.ProviderError):
                providers.provider_chat([], provider="deepseek")
            open_mock.assert_not_called()

    def test_http_error_does_not_expose_response_body(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-secret"
        import urllib.error
        def fake_open(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 401, "unauthorized",
                                         {}, None)
        with patch.object(providers.urllib.request, "urlopen", fake_open):
            with self.assertRaisesRegex(providers.ProviderError, "HTTP 401"):
                providers.provider_chat([], provider="deepseek")


if __name__ == "__main__":
    unittest.main()
