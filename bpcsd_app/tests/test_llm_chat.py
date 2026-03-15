import unittest

from modules.llm_chat import _default_model, LLMClient


class LLMChatTests(unittest.TestCase):
    def test_default_gemini_model_is_supported_fallback_friendly(self):
        self.assertEqual(_default_model("gemini"), "gemini-1.5-flash")

    def test_from_key_uses_updated_default_gemini_model(self):
        client = LLMClient.from_key("AIza" + "x" * 40)
        self.assertEqual(client.provider, "gemini")
        self.assertEqual(client.model, "gemini-1.5-flash")


if __name__ == "__main__":
    unittest.main()
