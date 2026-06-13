"""LiteLLM-backed model client for HAL agent sessions."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from hal9000.agent.model import AgentModelResponse, AgentToolCall
from hal9000.security import SecretManager, create_secret_manager_from_settings, secret_value

CompletionFunc = Callable[..., Awaitable[Any]]
SleepFunc = Callable[[float], Awaitable[Any]]

_ANTHROPIC_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
_OPENAI_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}
_GEMINI_EFFORTS = {"minimal", "low", "medium", "high"}
_HF_EFFORTS = {"low", "medium", "high"}
_LOCAL_PROVIDER_DEFAULTS = {
    "ollama": ("OLLAMA_BASE_URL", "OLLAMA_API_KEY", "http://localhost:11434"),
    "vllm": ("VLLM_BASE_URL", "VLLM_API_KEY", "http://localhost:8000"),
    "lm_studio": ("LM_STUDIO_BASE_URL", "LM_STUDIO_API_KEY", "http://localhost:1234"),
    "llamacpp": ("LLAMACPP_BASE_URL", "LLAMACPP_API_KEY", "http://localhost:8080"),
}
_LOCAL_SHARED_BASE_URL_ENV = "LOCAL_LLM_BASE_URL"
_LOCAL_SHARED_API_KEY_ENV = "LOCAL_LLM_API_KEY"
_LOCAL_DEFAULT_API_KEY = "EMPTY"


class UnsupportedReasoningEffortError(ValueError):
    """Raised when a reasoning effort is not valid for the selected provider."""


@dataclass(frozen=True)
class LiteLLMModelConfig:
    """Configuration for one HAL LiteLLM model client."""

    model_name: str = "anthropic/claude-opus-4-8"
    reasoning_effort: str | None = None
    max_tokens: int = 4096
    timeout_seconds: float = 600.0
    max_retries: int = 3
    hf_token: str | None = None
    hf_router_base_url: str = "https://router.huggingface.co/v1"
    secret_manager: SecretManager | None = None


class LiteLLMAgentModelClient:
    """LiteLLM implementation of AgentModelClient."""

    def __init__(
        self,
        config: LiteLLMModelConfig | None = None,
        completion_func: CompletionFunc | None = None,
        sleep_func: SleepFunc | None = None,
    ):
        """Initialize the model client.

        completion_func and sleep_func are injectable so tests can exercise
        retries and response parsing without live provider credentials.
        """
        self.config = config or LiteLLMModelConfig()
        self._completion_func = completion_func
        self._sleep_func = sleep_func or asyncio.sleep

    @classmethod
    def from_settings(
        cls,
        settings,
        *,
        hf_token: str | None = None,
        completion_func: CompletionFunc | None = None,
        sleep_func: SleepFunc | None = None,
    ) -> LiteLLMAgentModelClient:
        """Create a client from HAL Settings or any settings-like object."""
        agent = settings.agent
        return cls(
            LiteLLMModelConfig(
                model_name=agent.model_name,
                reasoning_effort=agent.reasoning_effort,
                max_tokens=agent.max_tokens,
                timeout_seconds=agent.timeout_seconds,
                max_retries=agent.max_retries,
                hf_token=hf_token,
                hf_router_base_url=agent.hf_router_base_url,
                secret_manager=create_secret_manager_from_settings(settings),
            ),
            completion_func=completion_func,
            sleep_func=sleep_func,
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AgentModelResponse:
        """Call LiteLLM and normalize the response for HAL's runtime."""
        params = resolve_litellm_params(
            self.config.model_name,
            hf_token=self.config.hf_token,
            reasoning_effort=self.config.reasoning_effort,
            hf_router_base_url=self.config.hf_router_base_url,
            secret_manager=self.config.secret_manager,
        )
        completion_func = self._completion_func or _load_litellm_acompletion()
        last_error: Exception | None = None
        max_attempts = max(1, self.config.max_retries)

        for attempt in range(max_attempts):
            try:
                response = await completion_func(
                    messages=messages,
                    tools=tools or None,
                    tool_choice="auto" if tools else None,
                    max_tokens=self.config.max_tokens,
                    timeout=self.config.timeout_seconds,
                    **params,
                )
                return parse_litellm_response(response)
            except Exception as exc:
                last_error = exc
                delay = retry_delay_for(exc, attempt)
                if delay is None or attempt >= max_attempts - 1:
                    raise
                await self._sleep_func(delay)

        assert last_error is not None
        raise last_error


def resolve_litellm_params(
    model_name: str,
    *,
    hf_token: str | None = None,
    reasoning_effort: str | None = None,
    hf_router_base_url: str = "https://router.huggingface.co/v1",
    secret_manager: SecretManager | None = None,
) -> dict[str, Any]:
    """Resolve HAL model ids to LiteLLM completion kwargs."""
    if model_name.startswith("anthropic/"):
        params: dict[str, Any] = {"model": model_name}
        effort = _normalize_effort(reasoning_effort)
        if effort:
            if effort not in _ANTHROPIC_EFFORTS:
                raise UnsupportedReasoningEffortError(
                    f"Anthropic does not accept reasoning_effort={effort!r}"
                )
            params["thinking"] = {"type": "adaptive"}
            params["output_config"] = {"effort": effort}
        return params

    if model_name.startswith("bedrock/"):
        return {"model": model_name}

    if model_name.startswith("openai/"):
        params = {"model": model_name}
        effort = _normalize_effort(reasoning_effort)
        if effort:
            if effort not in _OPENAI_EFFORTS:
                raise UnsupportedReasoningEffortError(
                    f"OpenAI does not accept reasoning_effort={effort!r}"
                )
            params["reasoning_effort"] = effort
        return params

    if model_name.startswith("gemini/"):
        params = {"model": model_name}
        api_key = secret_value("gemini", secret_manager=secret_manager)
        if api_key:
            params["api_key"] = api_key
        effort = _normalize_effort(reasoning_effort)
        if effort:
            if effort not in _GEMINI_EFFORTS:
                raise UnsupportedReasoningEffortError(
                    f"Gemini does not accept reasoning_effort={effort!r}"
                )
            params["reasoning_effort"] = effort
        return params

    local_params = _resolve_local_model_params(model_name, secret_manager=secret_manager)
    if local_params is not None:
        if reasoning_effort:
            raise UnsupportedReasoningEffortError(
                "Local OpenAI-compatible endpoints do not accept reasoning_effort"
            )
        return local_params

    hf_model = model_name.removeprefix("huggingface/")
    params = {
        "model": f"openai/{hf_model}",
        "api_base": hf_router_base_url.rstrip("/"),
        "api_key": _resolve_hf_router_token(hf_token, secret_manager=secret_manager),
    }
    effort = _normalize_effort(reasoning_effort)
    if effort:
        hf_effort = "low" if effort == "minimal" else effort
        if hf_effort not in _HF_EFFORTS:
            raise UnsupportedReasoningEffortError(
                f"Hugging Face Router does not accept reasoning_effort={hf_effort!r}"
            )
        params["extra_body"] = {"reasoning_effort": hf_effort}
    if bill_to := os.environ.get("HF_BILL_TO"):
        params["extra_headers"] = {"X-HF-Bill-To": bill_to}
    return params


def parse_litellm_response(response: Any) -> AgentModelResponse:
    """Normalize a LiteLLM response object or response-shaped dict."""
    choices = _get(response, "choices", []) or []
    first_choice = choices[0] if choices else {}
    message = _get(first_choice, "message", {}) or {}
    usage = _get(response, "usage", {}) or {}
    return AgentModelResponse(
        content=_get(message, "content"),
        tool_calls=_parse_tool_calls(_get(message, "tool_calls", []) or []),
        token_count=_get(usage, "total_tokens"),
        finish_reason=_get(first_choice, "finish_reason"),
        metadata={"provider_response_id": _get(response, "id")},
    )


def retry_delay_for(error: Exception, attempt_index: int) -> float | None:
    """Return retry delay seconds for transient provider errors."""
    if _is_context_overflow_error(error):
        return None
    if _is_rate_limit_error(error):
        return [30.0, 60.0][attempt_index] if attempt_index < 2 else None
    if _is_transient_error(error):
        return [1.0, 3.0, 8.0][attempt_index] if attempt_index < 3 else None
    return None


def _parse_tool_calls(raw_tool_calls: list[Any]) -> list[AgentToolCall]:
    tool_calls: list[AgentToolCall] = []
    for raw_tool_call in raw_tool_calls:
        function = _get(raw_tool_call, "function", {}) or {}
        name = _get(function, "name")
        if not name:
            continue
        raw_arguments = _get(function, "arguments") or "{}"
        arguments = _parse_tool_arguments(raw_arguments)
        tool_calls.append(
            AgentToolCall(
                id=_get(raw_tool_call, "id") or "",
                name=str(name),
                arguments=arguments,
            )
        )
    return tool_calls


def _parse_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if not isinstance(raw_arguments, str):
        return {"_raw_arguments": raw_arguments}
    try:
        parsed = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return {"_raw_arguments": raw_arguments}
    if isinstance(parsed, dict):
        return parsed
    return {"_raw_arguments": parsed}


def _resolve_local_model_params(
    model_name: str,
    *,
    secret_manager: SecretManager | None = None,
) -> dict[str, Any] | None:
    provider, _, local_name = model_name.partition("/")
    if provider not in _LOCAL_PROVIDER_DEFAULTS or not local_name:
        return None
    base_env, key_env, default_base = _LOCAL_PROVIDER_DEFAULTS[provider]
    raw_base_url = (
        os.environ.get(base_env) or os.environ.get(_LOCAL_SHARED_BASE_URL_ENV) or default_base
    )
    api_key = (
        secret_value(
            provider,
            secret_manager=secret_manager,
            extra_names=(key_env,),
            include_provider_names=False,
        )
        or secret_value("local_llm", secret_manager=secret_manager, extra_names=(_LOCAL_SHARED_API_KEY_ENV,))
        or _LOCAL_DEFAULT_API_KEY
    )
    return {
        "model": f"openai/{local_name}",
        "api_base": _ensure_openai_v1_base(raw_base_url),
        "api_key": api_key,
    }


def _resolve_hf_router_token(
    hf_token: str | None = None,
    *,
    secret_manager: SecretManager | None = None,
) -> str | None:
    inference_token = secret_value(
        "huggingface",
        secret_manager=secret_manager,
        extra_names=("INFERENCE_TOKEN",),
        include_provider_names=False,
    )
    if inference_token:
        return inference_token
    if hf_token:
        return hf_token
    return secret_value("huggingface", secret_manager=secret_manager)


def _ensure_openai_v1_base(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _normalize_effort(reasoning_effort: str | None) -> str | None:
    if reasoning_effort is None:
        return None
    stripped = reasoning_effort.strip().lower()
    return stripped or None


def _is_rate_limit_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(
        pattern in text
        for pattern in (
            "429",
            "rate limit",
            "rate_limit",
            "too many requests",
            "too many tokens",
            "request limit",
            "throttl",
        )
    )


def _is_context_overflow_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(
        pattern in text
        for pattern in (
            "context window exceeded",
            "maximum context length",
            "max context length",
            "prompt is too long",
            "context length exceeded",
            "too many input tokens",
            "input is too long",
        )
    )


def _is_transient_error(error: Exception) -> bool:
    text = str(error).lower()
    return _is_rate_limit_error(error) or any(
        pattern in text
        for pattern in (
            "timeout",
            "timed out",
            "503",
            "service unavailable",
            "502",
            "bad gateway",
            "500",
            "internal server error",
            "overloaded",
            "capacity",
            "connection reset",
            "connection refused",
            "connection error",
            "eof",
            "broken pipe",
        )
    )


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _load_litellm_acompletion() -> CompletionFunc:
    try:
        from litellm import acompletion
    except ImportError as exc:
        raise RuntimeError(
            "LiteLLM is required for LiteLLMAgentModelClient. "
            "Install HAL with the agent extra: pip install -e '.[agent]'."
        ) from exc
    return acompletion
