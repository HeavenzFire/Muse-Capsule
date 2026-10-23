import json
import os
import sys
import unittest
from unittest.mock import patch

# providers.py lives in agent/, one level above this tests/ directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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


class RawResponse:
    """A response whose body is raw bytes (for malformed-body tests)."""
    def __init__(self, raw):
        self.raw = raw
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.raw


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
        os.environ["HF_ALLOW_EXTERNAL"] = "1"
        def fake_open(req, timeout=0):
            self.assertEqual(req.full_url, "https://api.deepseek.com/chat/completions")
            self.assertEqual(req.get_header("Authorization"), "Bearer test-secret")
            body = json.loads(req.data.decode("utf-8"))
            self.assertEqual(body["model"], "deepseek-chat")
            self.assertFalse(body["stream"])
            return FakeResponse({"choices": [{"message": {"content": "verified mock"}}]})
        with patch.object(providers, "_open", fake_open):
            answer = providers.provider_chat([{"role": "user", "content": "test"}],
                                             provider="deepseek")
        self.assertEqual(answer, "verified mock")

    def test_missing_key_fails_before_network(self):
        with patch.object(providers, "_open") as open_mock:
            with self.assertRaises(providers.ProviderError):
                providers.provider_chat([], provider="deepseek")
            open_mock.assert_not_called()

    def test_http_error_does_not_expose_response_body(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-secret"
        os.environ["HF_ALLOW_EXTERNAL"] = "1"
        import urllib.error
        def fake_open(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 401, "unauthorized",
                                         {}, None)
        with patch.object(providers, "_open", fake_open):
            with self.assertRaisesRegex(providers.ProviderError, "HTTP 401"):
                providers.provider_chat([], provider="deepseek")

    def test_external_provider_refuses_without_per_run_opt_in(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-secret"
        with patch.object(providers, "_open") as open_mock:
            with self.assertRaisesRegex(providers.ProviderError,
                                        "per-run opt-in"):
                providers.provider_chat([], provider="deepseek")
            open_mock.assert_not_called()

    def _redirect(self, from_url, to_url):
        import urllib.request
        handler = providers._StripCrossHostAuth()
        req = urllib.request.Request(
            from_url, data=b"{}", method="POST",
            headers={"Authorization": "Bearer test-secret",
                     "Content-Type": "application/json"})
        return handler.redirect_request(req, None, 302, "Found", {}, to_url)

    def test_cross_host_redirect_strips_authorization(self):
        new = self._redirect("https://api.deepseek.com/chat/completions",
                             "https://other-host.example/collect")
        self.assertIsNotNone(new)
        self.assertIsNone(new.get_header("Authorization"))

    def test_same_origin_redirect_keeps_authorization(self):
        new = self._redirect("https://api.deepseek.com/chat/completions",
                             "https://api.deepseek.com/v2/chat/completions")
        self.assertIsNotNone(new)
        self.assertEqual(new.get_header("Authorization"), "Bearer test-secret")

    def test_http_base_url_rejected_for_external_provider(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-secret"
        os.environ["HF_ALLOW_EXTERNAL"] = "1"
        os.environ["HF_AGENT_BASE_URL"] = "http://api.example.com"
        with patch.object(providers, "_open") as open_mock:
            with self.assertRaisesRegex(providers.ProviderError, "https"):
                providers.provider_chat([], provider="deepseek")
            open_mock.assert_not_called()

    def test_loopback_http_base_url_allowed_without_opt_in(self):
        os.environ["HF_OPENAI_COMPATIBLE_API_KEY"] = "test-secret"
        os.environ["HF_AGENT_BASE_URL"] = "http://127.0.0.1:9000/v1"
        def fake_open(req, timeout=0):
            self.assertEqual(req.full_url,
                             "http://127.0.0.1:9000/v1/chat/completions")
            return FakeResponse({"choices": [{"message": {"content": "local ok"}}]})
        with patch.object(providers, "_open", fake_open):
            answer = providers.provider_chat([], provider="openai-compatible")
        self.assertEqual(answer, "local ok")

    def test_malformed_json_response_is_provider_error(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-secret"
        os.environ["HF_ALLOW_EXTERNAL"] = "1"
        def fake_open(req, timeout=0):
            return RawResponse(b"this is not json")
        with patch.object(providers, "_open", fake_open):
            with self.assertRaisesRegex(providers.ProviderError, "malformed"):
                providers.provider_chat([], provider="deepseek")


if __name__ == "__main__":
    unittest.main()
