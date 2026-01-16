import unittest
from unittest.mock import MagicMock, patch
from code_intelligence.config import Settings
from code_intelligence.providers.llm import LLMInterface
from pydantic import SecretStr
import os

class TestConfig(unittest.TestCase):
    def test_default_config(self):
        # Ensure env var is unset for this test
        with patch.dict(os.environ):
            if "LLM_PROVIDER" in os.environ:
                del os.environ["LLM_PROVIDER"]
            settings = Settings()
            self.assertEqual(settings.llm_provider, "openai")

    def test_openrouter_config(self):
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "sk-test",
            "LLM_MODEL": "anthropic/claude-3-opus"
        }):
            # Re-instantiate settings to pick up env vars
            settings = Settings()
            self.assertEqual(settings.llm_provider, "openrouter")
            self.assertEqual(settings.get_llm_api_key().get_secret_value(), "sk-test")
            self.assertEqual(settings.llm_model, "anthropic/claude-3-opus")

class TestProvider(unittest.TestCase):
    @patch("code_intelligence.providers.llm.OpenAI")
    @patch("code_intelligence.providers.llm.settings")
    def test_llm_generation(self, mock_settings, mock_openai):
        # Mock settings
        mock_settings.get_llm_api_key.return_value = SecretStr("sk-test")
        mock_settings.get_llm_base_url.return_value = "https://api.openai.com/v1"
        mock_settings.llm_provider = "openai"
        mock_settings.llm_model = "gpt-4o-mini"
        mock_settings.llm_temperature = 0.0
        mock_settings.llm_max_tokens = 100
        mock_settings.llm_prefer_json = True
        mock_settings.rag_redact_secrets = False

        # Mock client
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"foo": "bar"}'))]
        mock_client.chat.completions.create.return_value = mock_response

        # Init interface
        llm = LLMInterface()
        response = llm.generate_response("hello", json_mode=True)
        self.assertEqual(response, '{"foo": "bar"}')

    @patch("code_intelligence.providers.llm.OpenAI")
    @patch("code_intelligence.providers.llm.settings")
    def test_json_fallback(self, mock_settings, mock_openai):
        mock_settings.get_llm_api_key.return_value = SecretStr("sk-test")
        mock_settings.get_llm_base_url.return_value = "https://api.openai.com/v1"
        mock_settings.llm_provider = "openai"
        mock_settings.llm_model = "gpt-4o-mini"
        mock_settings.llm_temperature = 0.0
        mock_settings.llm_max_tokens = 100
        mock_settings.llm_prefer_json = True
        mock_settings.rag_redact_secrets = False

        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        # Simulate failure on json_object
        from openai import APIError

        def side_effect(*args, **kwargs):
            if kwargs.get("response_format"):
                raise APIError("JSON mode not supported", request=None, body=None)
            return MagicMock(choices=[MagicMock(message=MagicMock(content='{"fallback": true}'))])

        mock_client.chat.completions.create.side_effect = side_effect

        llm = LLMInterface()
        response = llm.generate_response("hello", json_mode=True)
        self.assertEqual(response, '{"fallback": true}')

if __name__ == "__main__":
    unittest.main()
