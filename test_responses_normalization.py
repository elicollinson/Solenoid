import pytest

from local_responses.schemas import ResponsesRequest


def test_normalized_messages_accepts_response_input_items() -> None:
    req = ResponsesRequest(
        model="test-model",
        input=[
            {"role": "user", "content": "Hello"},
            {
                "type": "function_call",
                "name": "transfer_to_settings_manager",
                "arguments": "{}",
                "call_id": "auto_0",
            },
            {
                "type": "function_call_output",
                "call_id": "auto_0",
                "output": {"assistant": "Settings Manager"},
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Applied."}],
            },
        ],
    )

    messages = req.normalized_messages()

    assert messages[0] == {"role": "user", "content": "Hello"}
    assert messages[1]["role"] == "assistant"
    assert "function_call" in messages[1]["content"]
    assert messages[2] == {
        "role": "tool",
        "content": '{"assistant": "Settings Manager"}',
        "tool_call_id": "auto_0",
    }
    assert messages[3] == {"role": "assistant", "content": "Applied."}


def test_normalized_messages_rejects_unreadable_inputs() -> None:
    req = ResponsesRequest(model="test-model", input=[123])

    with pytest.raises(ValueError, match="No valid messages"):
        _ = req.normalized_messages()


def test_tool_definition_accepts_legacy_shape() -> None:
    req = ResponsesRequest(
        model="test-model",
        tools=[
            {
                "type": "function",
                "name": "shell_agent",
                "description": "Run shell commands",
                "parameters": {"type": "object", "properties": {"input": {"type": "string"}}},
                "strict": True,
            }
        ],
    )

    assert req.tools is not None
    tool = req.tools[0]
    assert tool.function is not None
    payload = tool.as_openai_tool()

    assert payload["type"] == "function"
    assert payload["function"]["name"] == "shell_agent"
    assert payload["function"]["parameters"]["type"] == "object"
    assert payload["strict"] is True
