"""Tests for the HAL LiteLLM model adapter."""

import pytest

from hal9000.agent import (
    LiteLLMAgentModelClient,
    LiteLLMModelConfig,
    UnsupportedReasoningEffortError,
    parse_litellm_response,
    resolve_litellm_params,
)
from hal9000.security import MappingSecretManager


def test_resolve_litellm_params_for_anthropic_with_effort():
    """Anthropic models should keep native ids and adaptive effort params."""
    params = resolve_litellm_params(
        "anthropic/claude-opus-4-8",
        reasoning_effort="high",
    )

    assert params["model"] == "anthropic/claude-opus-4-8"
    assert params["thinking"] == {"type": "adaptive"}
    assert params["output_config"] == {"effort": "high"}


def test_resolve_litellm_params_for_openai_with_effort():
    """OpenAI models should forward reasoning_effort top-level."""
    params = resolve_litellm_params("openai/gpt-5.5", reasoning_effort="xhigh")

    assert params == {"model": "openai/gpt-5.5", "reasoning_effort": "xhigh"}


def test_resolve_litellm_params_for_gemini_with_effort(monkeypatch):
    """Gemini routes should use LiteLLM's Gemini provider and shared secret lookup."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    manager = MappingSecretManager({"HAL9000_GEMINI_API_KEY": "managed-gemini-key"})

    params = resolve_litellm_params(
        "gemini/gemini-3.5-flash",
        reasoning_effort="minimal",
        secret_manager=manager,
    )

    assert params == {
        "model": "gemini/gemini-3.5-flash",
        "api_key": "managed-gemini-key",
        "reasoning_effort": "minimal",
    }


def test_resolve_litellm_params_for_local_model(monkeypatch):
    """Local model prefixes should resolve to OpenAI-compatible endpoints."""
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("LOCAL_LLM_API_KEY", "local-key")

    params = resolve_litellm_params("ollama/llama3.1:8b")

    assert params == {
        "model": "openai/llama3.1:8b",
        "api_base": "http://localhost:9999/v1",
        "api_key": "local-key",
    }


def test_resolve_litellm_params_for_hf_router(monkeypatch):
    """Bare model ids should route through the Hugging Face Router."""
    monkeypatch.delenv("INFERENCE_TOKEN", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("HF_BILL_TO", "arc-pbc")

    params = resolve_litellm_params(
        "MiniMaxAI/MiniMax-M2.7",
        hf_token="hf_user_token",
        reasoning_effort="minimal",
    )

    assert params["model"] == "openai/MiniMaxAI/MiniMax-M2.7"
    assert params["api_base"] == "https://router.huggingface.co/v1"
    assert params["api_key"] == "hf_user_token"
    assert params["extra_body"] == {"reasoning_effort": "low"}
    assert params["extra_headers"] == {"X-HF-Bill-To": "arc-pbc"}


def test_resolve_litellm_params_uses_secret_manager(monkeypatch):
    """Provider secrets should resolve through the injected manager."""
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("INFERENCE_TOKEN", raising=False)
    manager = MappingSecretManager({"HF_TOKEN": "managed-hf-token"})

    params = resolve_litellm_params("huggingface/Qwen/Qwen3", secret_manager=manager)

    assert params["api_key"] == "managed-hf-token"


def test_hf_router_explicit_token_precedes_hf_token_env(monkeypatch):
    """Explicit per-session HF tokens should keep existing precedence."""
    monkeypatch.delenv("INFERENCE_TOKEN", raising=False)
    monkeypatch.setenv("HF_TOKEN", "env-hf-token")

    params = resolve_litellm_params("huggingface/Qwen/Qwen3", hf_token="session-hf-token")

    assert params["api_key"] == "session-hf-token"


def test_resolve_litellm_params_rejects_invalid_effort():
    """Unsupported provider effort values should fail before network calls."""
    with pytest.raises(UnsupportedReasoningEffortError):
        resolve_litellm_params("MiniMaxAI/MiniMax-M2.7", reasoning_effort="xhigh")


def test_resolve_litellm_params_rejects_invalid_gemini_effort():
    """Gemini supports minimal through high, but not OpenAI's xhigh effort."""
    with pytest.raises(UnsupportedReasoningEffortError):
        resolve_litellm_params("gemini/gemini-3.5-flash", reasoning_effort="xhigh")


def test_parse_litellm_response_with_tool_call():
    """LiteLLM tool calls should normalize into HAL tool calls."""
    response = {
        "id": "response-1",
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {
                                "name": "hal_search_memory",
                                "arguments": '{"query": "creep resistance"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"total_tokens": 123},
    }

    parsed = parse_litellm_response(response)

    assert parsed.content is None
    assert parsed.finish_reason == "tool_calls"
    assert parsed.token_count == 123
    assert parsed.metadata["provider_response_id"] == "response-1"
    assert parsed.tool_calls[0].id == "call-1"
    assert parsed.tool_calls[0].name == "hal_search_memory"
    assert parsed.tool_calls[0].arguments == {"query": "creep resistance"}


@pytest.mark.asyncio
async def test_litellm_client_retries_transient_errors():
    """Transient provider errors should retry before succeeding."""
    attempts = []
    sleeps = []

    async def completion_func(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise RuntimeError("rate limit 429")
        return {
            "choices": [{"message": {"content": "done"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 12},
        }

    async def sleep_func(delay):
        sleeps.append(delay)

    client = LiteLLMAgentModelClient(
        LiteLLMModelConfig(
            model_name="openai/gpt-5.5",
            max_retries=2,
            reasoning_effort="high",
        ),
        completion_func=completion_func,
        sleep_func=sleep_func,
    )

    result = await client.complete([{"role": "user", "content": "hi"}], [])

    assert result.content == "done"
    assert len(attempts) == 2
    assert sleeps == [30.0]
    assert attempts[0]["model"] == "openai/gpt-5.5"
    assert attempts[0]["reasoning_effort"] == "high"
    assert attempts[0]["tools"] is None


@pytest.mark.asyncio
async def test_litellm_client_does_not_retry_context_overflow():
    """Context overflow should fail immediately instead of burning retries."""
    attempts = []

    async def completion_func(**kwargs):
        attempts.append(kwargs)
        raise RuntimeError("maximum context length exceeded")

    client = LiteLLMAgentModelClient(
        LiteLLMModelConfig(model_name="openai/gpt-5.5", max_retries=3),
        completion_func=completion_func,
    )

    with pytest.raises(RuntimeError, match="maximum context length exceeded"):
        await client.complete([{"role": "user", "content": "hi"}], [])

    assert len(attempts) == 1
