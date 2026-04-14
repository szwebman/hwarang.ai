"""Tests for chat completions endpoint."""

import pytest


def test_chat_completions_no_model_loaded(client):
    """Should return 404 when model is not loaded."""
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "nonexistent-model",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    assert response.status_code == 404


def test_chat_completions_invalid_request(client):
    """Should return 422 for invalid request body."""
    response = client.post(
        "/v1/chat/completions",
        json={"model": "test", "messages": "not a list"},
    )
    assert response.status_code == 422


def test_models_list_empty(client):
    """Should return empty model list when no models loaded."""
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert data["data"] == []
