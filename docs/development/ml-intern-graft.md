# ml-intern Graft Plan

HAL should integrate `huggingface/ml-intern` as a graft, not a merge.

The rule is simple:

- HAL owns research programs, canonical storage, provenance, review, exports,
  governance, and ADAM context.
- The ml-intern-derived layer supplies agent-loop mechanics, model routing,
  context management, approvals, sandbox/Jobs execution, and Hugging Face tools.
- Imported ideas enter HAL through adapters and durable HAL records, never by
  replacing HAL's research OS.

This plan is based on `huggingface/ml-intern` commit
`021580fd867f1c231e4f46e74fa2dee70706a528` from 2026-05-13. The upstream repo
is Apache-2.0, while HAL is MIT; copied or substantially adapted code must keep
license and notice obligations explicit.

## Ownership Boundary

| Layer | HAL owner | ml-intern graft value |
| ----- | --------- | --------------------- |
| Research programs | `hal9000.research.program` | Agent prompt can execute the contract |
| Run state and budgets | `ResearchRun`, `RunBudgetTracker` | Approval and cost policy patterns |
| Tools | HAL tool specs backed by services | Tool-router mechanics and MCP/HF tools |
| Memory | Documents, chunks, claims, outputs, graph | Context compaction and subagent research |
| Events | `ResearchRunEvent`, gateway/session events | Streaming turn and tool events |
| Artifacts | HAL object store and exports | Hub artifact registration and trace upload |
| UI | HAL research/review surfaces | Chat, session sidebar, approval dialogs |

## First Graft Point

The initial code boundary is `hal9000.agent`.

It intentionally does not import ml-intern wholesale. It gives HAL a stable
surface for future ports:

- `AgentOperation` and `AgentEvent` define session queue and event contracts.
- `AgentMessage` and `AgentContextWindow` define HAL-owned persisted context.
- `AgentToolSpec` and `AgentToolRouter` expose tools in an LLM-compatible shape.
- `AgentToolRouter.call_tool` enforces `RunBudgetTracker` tool policy and writes
  durable `ResearchToolCall` and `ResearchRunEvent` rows through `ResearchStore`.
- `AgentSessionRuntime` adds the first async submission loop: user input, model
  response, HAL tool execution, tool-result replay, final response, shutdown,
  compaction request, and interrupt handling.
- `LiteLLMAgentModelClient` implements `AgentModelClient` using
  LiteLLM-compatible model ids, provider-specific reasoning effort, tool-call
  normalization, and transient retry handling.
- `AgentToolApprovalRequest` and `AgentToolApprovalDecision` let gated HAL
  tools pause the active turn until a human or policy decision arrives through
  the session operation queue.
- `AgentContextWindow.compact_to_token_budget` provides deterministic,
  token-aware compaction that preserves the system prompt, first research task,
  recent context, and provider-valid tool-call pairs.
- `hal9000.agent.service_tools` exposes HAL services as agent tools while
  preserving the policy, approval, tool-call, and run-event accounting boundary.
- `hal_hf_repo` and `hal_hf_job` add the first approval-gated HF compute lane:
  Hub repo mutations and Jobs operations stage HAL outputs and run events instead
  of becoming unmanaged side effects.
- `hal_hf_sandbox` adds the first approved remote sandbox lifecycle boundary:
  create, status, run command, read/write files, and delete are recorded as HAL
  outputs and events while real backend execution remains injectable.
- `hal_hf_job` now also covers scheduled Jobs and scheduled-job management:
  schedule/list/status/suspend/resume/delete operations keep the same approval,
  smoke-gate, request-scrubbing, output, and event semantics as one-off jobs.
- Trackio dashboard metadata is seeded as HAL output whenever approved HF Jobs
  carry `trackio_space_id` or `trackio_project`, preserving dashboard links and
  environment wiring in the run ledger.
- `hal_hf_harvest_artifacts` can now materialize HF job and repo artifacts into
  HAL object storage, recording object keys, object URIs, sizes, hashes, and
  storage errors alongside the original Hub references.

That means any future ml-intern loop, LiteLLM client, or frontend session can
call HAL tools without bypassing the research run ledger.

## Port Order

1. **HAL-native agent loop** - Done for the first slice.
   Add an async submission loop around `AgentOperation`, `AgentEvent`,
   `AgentContextWindow`, and `AgentToolRouter`. Keep the loop small at first:
   user input, model call, tool call, tool result, final answer.

2. **LiteLLM model adapter** - Done for the first slice.
   Port the model parameter resolver pattern so HAL can use Anthropic, OpenAI,
   Hugging Face Router, and local OpenAI-compatible endpoints through one
   abstraction. RLM processing should call this adapter instead of directly
   instantiating `Anthropic`.

3. **HAL service tools** - Done for the first service slice.
   Wrap existing services as agent tools:
   `hal_acquire`, `hal_process_pdf`, `hal_search_memory`, `hal_stage_outputs`,
   `hal_export_run`, `hal_build_adam_context`, `hal_review_output`, and
   `hal_graph_edge`.

4. **HF research tools** - Done for the first read-only discovery slice.
   Port ml-intern's paper, docs, dataset, repo, and GitHub-example tools behind
   HAL naming and policies. The tools may fetch from HF and Semantic Scholar,
   but stored findings must become HAL documents, chunks, claims, evidence, or
   outputs. The first graft exposes `hal_hf_papers`, `hal_hf_dataset`,
   `hal_hf_docs`, and `hal_github_examples` through the `hf_research` policy.
   Paper search/details import source records, chunks, and first-pass claims;
   linked paper resources, dataset profiles, docs captures, and GitHub examples
   stage reviewable HAL outputs. Repo writes, Hub uploads, and HF Jobs remain in
   the later approved compute lane.

5. **Approvals, cost policy, and token-aware context** - Done for the first
   agent slice.
   Adapt approval policy for sandbox creation, HF Jobs, repo uploads/deletes,
   destructive local operations, and billable runs. Store approvals, rejections,
   and auto-approval decisions as run events. Add compaction triggers so HAL can
   continue long runs without losing its durable research ledger. Broader
   sandbox/HF Jobs approval rules remain part of the HF compute lane.

6. **Gateway/session API** - Done for the first gateway slice.
   Upgrade the HAL gateway to support session creation, submit, approve,
   interrupt, compact, event replay, and message history. Preserve compatibility
   with the existing WebSocket message protocol where practical. Run-bound
   gateway sessions now mirror `AgentEvent` payloads into `ResearchRunEvent` as
   `agent.gateway.event` records so replay and history can recover after a
   gateway restart.

7. **Frontend graft**
   Reuse the ml-intern UI concepts, not the product shell: session sidebar,
   streaming chat, tool-call grouping, approval dialogs, and model picker.
   HAL-specific panels should show run timeline, source evidence, review queue,
   ADAM context preview, and exports.

8. **HF compute lane** - Done for the first approved adapter slice.
   Add sandbox and HF Jobs support only after the above ledger and approval
   controls exist. Jobs should produce HAL artifacts and Hub links attached to
   runs, not unmanaged side effects. The first slice exposes `hal_hf_repo` and
   `hal_hf_job` under the `hf_compute` policy with mandatory runtime approval.
   The handlers capture Hub repo actions, job submissions, job observations,
   logs, and cancellation requests as staged outputs plus run events.
   `hal_hf_sandbox_smoke` and `hal_hf_harvest_artifacts` add the first hardening
   layer: GPU/model-loading job submissions must cite smoke evidence or an
   explicit skip rationale, and job/repo artifacts become HAL artifact manifests.
   `hal_hf_sandbox` adds the first lifecycle adapter for approved remote sandbox
   create/status/run/read/write/delete actions, staging every action in HAL.
   `hal_hf_job` now extends that boundary to scheduled Jobs, scheduled-job
   management, secret-key scrubbing, and Trackio dashboard seed outputs.
   `hal_hf_harvest_artifacts` can download resolved job/repo artifacts into
   HAL object storage so HF outputs survive as local or S3-backed run artifacts.
   A real HF Spaces sandbox backend can plug in through `hf_sandbox_client`
   without changing the agent tool contract.

## Non-Goals

- Do not replace `ResearchStore` with ml-intern persistence.
- Do not require `HF_TOKEN` for core HAL paper ingestion, review, or exports.
- Do not make the chat UI the source of truth for research outputs.
- Do not let sandbox or HF Jobs bypass run budgets and approval events.
- Do not collapse HAL research programs into free-form chat prompts.

## Validation Bar

Every graft slice should prove:

- A HAL research run can audit every tool call and outcome.
- Tool allow-lists and budgets are enforced before side effects.
- Generated claims or outputs cite HAL source records.
- UI/session events can be replayed from durable state after a restart.
- Optional HF/Hugging Face capabilities degrade cleanly when tokens are absent.
