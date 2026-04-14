"""Tests for shared schemas."""

import json

from hwarang_shared.schemas.chat import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    ChunkChoice,
    DeltaContent,
    Role,
    Usage,
)
from hwarang_shared.schemas.models import ModelInfo, ModelList


class TestChatMessage:
    def test_user_message(self):
        msg = ChatMessage(role=Role.USER, content="Hello")
        assert msg.role == Role.USER
        assert msg.content == "Hello"

    def test_assistant_message_with_no_content(self):
        msg = ChatMessage(role=Role.ASSISTANT)
        assert msg.content is None

    def test_serialization_roundtrip(self):
        msg = ChatMessage(role=Role.USER, content="test")
        data = msg.model_dump()
        restored = ChatMessage(**data)
        assert restored.role == msg.role
        assert restored.content == msg.content


class TestChatCompletionRequest:
    def test_minimal_request(self):
        req = ChatCompletionRequest(
            model="hwarang-small",
            messages=[ChatMessage(role=Role.USER, content="Hi")],
        )
        assert req.model == "hwarang-small"
        assert req.temperature == 0.7
        assert req.stream is False

    def test_streaming_request(self):
        req = ChatCompletionRequest(
            model="hwarang-small",
            messages=[ChatMessage(role=Role.USER, content="Hi")],
            stream=True,
            temperature=0.0,
            max_tokens=100,
        )
        assert req.stream is True
        assert req.temperature == 0.0
        assert req.max_tokens == 100

    def test_json_serialization(self):
        req = ChatCompletionRequest(
            model="hwarang-small",
            messages=[ChatMessage(role=Role.USER, content="Hello")],
        )
        json_str = req.model_dump_json()
        data = json.loads(json_str)
        assert data["model"] == "hwarang-small"
        assert len(data["messages"]) == 1


class TestChatCompletionResponse:
    def test_basic_response(self):
        resp = ChatCompletionResponse(
            model="hwarang-small",
            choices=[
                Choice(
                    index=0,
                    message=ChatMessage(role=Role.ASSISTANT, content="Hello!"),
                    finish_reason="stop",
                )
            ],
            usage=Usage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
        )
        assert resp.object == "chat.completion"
        assert resp.choices[0].message.content == "Hello!"
        assert resp.usage.total_tokens == 8
        assert resp.id.startswith("chatcmpl-")

    def test_openai_compatible_format(self):
        resp = ChatCompletionResponse(
            model="hwarang-small",
            choices=[
                Choice(
                    index=0,
                    message=ChatMessage(role=Role.ASSISTANT, content="test"),
                    finish_reason="stop",
                )
            ],
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
        data = resp.model_dump()
        # Verify OpenAI-compatible fields
        assert "id" in data
        assert "object" in data
        assert "created" in data
        assert "model" in data
        assert "choices" in data
        assert "usage" in data


class TestChatCompletionChunk:
    def test_streaming_chunk(self):
        chunk = ChatCompletionChunk(
            model="hwarang-small",
            choices=[
                ChunkChoice(
                    index=0,
                    delta=DeltaContent(content="Hello"),
                )
            ],
        )
        assert chunk.object == "chat.completion.chunk"
        assert chunk.choices[0].delta.content == "Hello"
        assert chunk.choices[0].finish_reason is None

    def test_finish_chunk(self):
        chunk = ChatCompletionChunk(
            model="hwarang-small",
            choices=[
                ChunkChoice(
                    index=0,
                    delta=DeltaContent(),
                    finish_reason="stop",
                )
            ],
        )
        assert chunk.choices[0].finish_reason == "stop"

    def test_sse_format(self):
        chunk = ChatCompletionChunk(
            model="hwarang-small",
            choices=[
                ChunkChoice(
                    index=0,
                    delta=DeltaContent(content="Hi"),
                )
            ],
        )
        sse_data = f"data: {chunk.model_dump_json()}\n\n"
        assert sse_data.startswith("data: {")
        assert sse_data.endswith("}\n\n")


class TestModelInfo:
    def test_model_info(self):
        info = ModelInfo(id="hwarang-small")
        assert info.id == "hwarang-small"
        assert info.object == "model"
        assert info.owned_by == "hwarang"

    def test_model_list(self):
        models = ModelList(data=[
            ModelInfo(id="hwarang-small"),
            ModelInfo(id="hwarang-medium"),
        ])
        assert models.object == "list"
        assert len(models.data) == 2
