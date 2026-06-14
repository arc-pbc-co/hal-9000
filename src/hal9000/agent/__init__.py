"""HAL-native agent graft points.

This package is the boundary where agent-loop ideas from ml-intern can plug into
HAL without taking ownership of HAL's research programs, store, review workflow,
or ADAM exports.
"""

from hal9000.agent.approvals import (
    AgentToolApprovalDecision,
    AgentToolApprovalRequest,
)
from hal9000.agent.context import AgentCompactionResult, AgentContextWindow, AgentMessage
from hal9000.agent.events import AgentEvent, AgentEventType, AgentOperation, AgentOperationType
from hal9000.agent.hf_tools import (
    HFResearchClient,
    build_hal_hf_compute_tools,
    build_hal_hf_research_tools,
    create_hal_hf_compute_tool_router,
    create_hal_hf_research_tool_router,
)
from hal9000.agent.litellm_client import (
    LiteLLMAgentModelClient,
    LiteLLMModelConfig,
    UnsupportedReasoningEffortError,
    parse_litellm_response,
    resolve_litellm_params,
)
from hal9000.agent.model import AgentModelClient, AgentModelResponse, AgentToolCall
from hal9000.agent.runtime import AgentLoopConfig, AgentSessionRuntime, AgentTurnResult
from hal9000.agent.service_tools import build_hal_service_tools, create_hal_service_tool_router
from hal9000.agent.tools import (
    AgentToolContext,
    AgentToolResult,
    AgentToolRouter,
    AgentToolSpec,
)

__all__ = [
    "AgentContextWindow",
    "AgentCompactionResult",
    "AgentEvent",
    "AgentEventType",
    "AgentLoopConfig",
    "AgentMessage",
    "AgentModelClient",
    "AgentModelResponse",
    "AgentOperation",
    "AgentOperationType",
    "AgentSessionRuntime",
    "AgentToolApprovalDecision",
    "AgentToolApprovalRequest",
    "AgentToolCall",
    "AgentToolContext",
    "AgentToolResult",
    "AgentToolRouter",
    "AgentToolSpec",
    "AgentTurnResult",
    "HFResearchClient",
    "LiteLLMAgentModelClient",
    "LiteLLMModelConfig",
    "UnsupportedReasoningEffortError",
    "build_hal_hf_compute_tools",
    "build_hal_hf_research_tools",
    "build_hal_service_tools",
    "create_hal_hf_compute_tool_router",
    "create_hal_hf_research_tool_router",
    "create_hal_service_tool_router",
    "parse_litellm_response",
    "resolve_litellm_params",
]
