import unittest
from unittest.mock import MagicMock, patch
from src.agent.compress import LLMTextCompressor, LLMMessagesCompressor

class TestCompress(unittest.TestCase):
    def setUp(self):
        self.llm_config = {
            "config_list": [
                {
                    "model": "gpt-4",
                    "api_key": "fake-key",
                    "base_url": "https://api.openai.com/v1"
                }
            ]
        }
        self.text_compressor = LLMTextCompressor(self.llm_config)

    @patch("openai.OpenAI")
    def test_llm_text_compressor(self, mock_openai):
        # Mock the OpenAI client and response
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Compressed content"))]
        mock_client.chat.completions.create.return_value = mock_response

        text = "This is a long text that needs to be compressed. " * 10
        compressed = self.text_compressor.compress(text, target_token=10)

        self.assertEqual(compressed, "Compressed content")
        mock_client.chat.completions.create.assert_called_once()

    @patch("openai.OpenAI")
    def test_llm_messages_compressor_trigger(self, mock_openai):
        # Mock OpenAI for message compressor
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Summary of history"))]
        mock_client.chat.completions.create.return_value = mock_response

        # max_tokens=20, each message (~50 chars) is ~16 tokens with //3 logic
        # 3 messages will be ~48 tokens, which is > 20
        compressor = LLMMessagesCompressor(
            self.llm_config, 
            max_tokens=20, 
            recent_rounds=1, 
            keep_first_n=1
        )
        compressor.agent_name = "TestAgent"

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Help me with a long task that requires many steps and details and history."},
            {"role": "assistant", "content": "I will help you with that. Can you provide more details about the task?"},
            {"role": "user", "content": "Here are the details: " + "detail " * 10}
        ]

        # First call - should trigger compression
        # keep_first_n=1: index 0 kept
        # recent_rounds=1: index 3 kept
        # messages to compress: index 1, 2
        transformed = compressor.apply_transform(messages)

        self.assertEqual(len(transformed), 3)
        self.assertEqual(transformed[0]["content"], messages[0]["content"])
        self.assertTrue("[历史对话摘要]: Summary of history" in transformed[1]["content"])
        self.assertEqual(transformed[2]["content"], messages[3]["content"])
        
        # Verify caching
        mock_client.chat.completions.create.reset_mock()
        
        # Add a new message
        messages.append({"role": "assistant", "content": "I see. Let's start with step 1."})
        
        # Second call - should use cache if total tokens still below threshold (it might not be if new message is large)
        # But here total_token_count = cache_tokens + uncompressed + recent
        transformed2 = compressor.apply_transform(messages)
        # Should NOT call LLM again if total < threshold, but here it might if threshold is very low
        # In our case max_tokens=20 is very low, so it will likely trigger again
        
    def test_llm_messages_compressor_no_trigger(self):
        compressor = LLMMessagesCompressor(self.llm_config, max_tokens=1000)
        messages = [{"role": "user", "content": "short message"}]
        
        transformed = compressor.apply_transform(messages)
        self.assertEqual(len(transformed), 1)
        self.assertEqual(transformed, messages)

    def test_token_estimation(self):
        compressor = LLMMessagesCompressor(self.llm_config)
        msg = {"content": "123456789"} # 9 chars
        # len // 3 = 3
        self.assertEqual(compressor._count_tokens(msg), 3)

if __name__ == "__main__":
    unittest.main()
