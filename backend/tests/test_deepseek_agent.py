from unittest.mock import Mock, patch

from services.agent.graph import AgentGraphRunner


def test_deepseek_agent_uses_openai_compatible_endpoint_and_tools() -> None:
    model = Mock()
    with patch("services.agent.graph.ChatOpenAI", return_value=model) as chat_openai:
        runner = AgentGraphRunner(
            provider="deepseek",
            model_id="deepseek-v4-pro",
            api_key="sk-test",
        )

    assert runner.base_model is model
    kwargs = chat_openai.call_args.kwargs
    assert kwargs["model"] == "deepseek-v4-pro"
    assert kwargs["base_url"] == "https://api.deepseek.com"
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
