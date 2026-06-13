"""Browser cockpit payloads for the HAL app gateway."""

from __future__ import annotations

import json
from typing import Any

from hal9000.db.models import ResearchRun
from hal9000.db.store import ResearchStore
from hal9000.research.authz import ResearchAuthorizer
from hal9000.research.graph import ResearchGraphService
from hal9000.research.review import ResearchReviewService

DEFAULT_AGENT_MODEL = "anthropic/claude-opus-4-8"
COCKPIT_MODEL_CHOICES = [
    # Anthropic: Fable is intentionally excluded for now; keep Opus as HAL's Claude default.
    "anthropic/claude-opus-4-8",
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-haiku-4-5",
    # OpenAI frontier text/agent models.
    "openai/gpt-5.5",
    "openai/gpt-5.4",
    "openai/gpt-5.4-mini",
    # Google Gemini API via LiteLLM's gemini/ provider route.
    "gemini/gemini-3.5-flash",
    "gemini/gemini-3.1-pro-preview",
    "gemini/gemini-3.1-flash-lite",
    # Useful non-frontier routes for HAL development and offline demos.
    "huggingface/Qwen/Qwen3-235B-A22B-Instruct-2507",
    "local/llama3.1:8b",
]


def frontend_config_payload(settings) -> dict[str, Any]:
    """Return the browser cockpit's model and route configuration."""
    agent = getattr(settings, "agent", None)
    default_model = getattr(agent, "model_name", DEFAULT_AGENT_MODEL)
    models = _unique([default_model, *COCKPIT_MODEL_CHOICES])
    return {
        "service": "hal-cockpit",
        "default_model": default_model,
        "reasoning_effort": getattr(agent, "reasoning_effort", None),
        "max_context_tokens": getattr(agent, "max_context_tokens", None),
        "models": models,
        "reasoning_efforts": ["", "minimal", "low", "medium", "high", "xhigh"],
        "routes": {
            "sessions": "/api/agent/session",
            "submit": "/api/agent/submit",
            "approve": "/api/agent/approve",
            "interrupt": "/api/agent/interrupt",
            "compact": "/api/agent/compact",
            "replay": "/api/agent/replay",
            "history": "/api/agent/history",
            "review": "/api/frontend/review",
            "evidence": "/api/frontend/evidence",
            "graph": "/api/frontend/graph",
        },
    }


def frontend_review_payload(
    store: ResearchStore,
    *,
    reviewer: str,
    project_slug: str | None = None,
    run_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return review queue and optional run detail for the cockpit."""
    project = None
    if project_slug:
        project = store.get_project_by_slug(project_slug)
        if project is None:
            raise ValueError(f"Research project not found: {project_slug}")
    service = ResearchReviewService(store)
    queue = [
        item.__dict__
        for item in service.list_review_queue(
            reviewer_email=reviewer,
            project=project,
            limit=limit,
        )
    ]
    detail = None
    if run_id:
        run = _require_run(store, run_id)
        detail = service.get_review_detail(run, reviewer_email=reviewer).to_dict()
    return {
        "reviewer": reviewer,
        "project_slug": project.slug if project else project_slug,
        "run_id": run_id,
        "queue": queue,
        "detail": detail,
    }


def frontend_evidence_payload(
    store: ResearchStore,
    *,
    viewer: str,
    run_id: str,
) -> dict[str, Any]:
    """Return source-backed evidence rows for a run."""
    run = _require_run(store, run_id)
    ResearchAuthorizer(store).require_run_role(run, viewer, "viewer")
    return {
        "run": _run_payload(run),
        "outputs": [_output_payload(output) for output in run.outputs],
        "claims": [_claim_payload(claim) for claim in run.claims],
        "chunks": [_chunk_payload(chunk) for chunk in run.chunks],
    }


def frontend_graph_payload(
    store: ResearchStore,
    *,
    viewer: str,
    project_slug: str | None = None,
    run_id: str | None = None,
    limit: int = 250,
) -> dict[str, Any]:
    """Return graph payloads for project or run panels."""
    graph = ResearchGraphService(store)
    if run_id:
        run = _require_run(store, run_id)
        ResearchAuthorizer(store).require_run_role(run, viewer, "viewer")
        return graph.run_graph(run, limit=limit).to_dict()
    if not project_slug:
        raise ValueError("project_slug or run_id is required for graph payloads")
    project = store.get_project_by_slug(project_slug)
    if project is None:
        raise ValueError(f"Research project not found: {project_slug}")
    ResearchAuthorizer(store).require_project_role(project, viewer, "viewer")
    return graph.project_graph(project, limit=limit).to_dict()


def frontend_html() -> str:
    """Return the HAL cockpit single-page app."""
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HAL-9000 Research Console</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@300;400;500;600&family=Newsreader:opsz,wght@6..72,300..800&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; }
    :root {
      --bg: #070809;
      --bg-2: #0b0d0f;
      --panel: #11161b;
      --panel-2: #151d24;
      --panel-3: #1a232b;
      --ink: #f4f1e8;
      --muted: #9aa4ad;
      --line: #2a343d;
      --line-hot: #6e2226;
      --red: #cf2029;
      --red-2: #7c1519;
      --amber: #e5a93c;
      --blue: #65a9c4;
      --green: #68a978;
      --white: #fffaf0;
      --shadow: 0 22px 70px rgba(0, 0, 0, .42);
    }
    html { background: var(--bg); }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        repeating-linear-gradient(90deg, rgba(255,255,255,.035) 0 1px, transparent 1px 96px),
        repeating-linear-gradient(0deg, rgba(255,255,255,.025) 0 1px, transparent 1px 96px),
        linear-gradient(180deg, #121212 0%, #070809 46%, #0e1012 100%);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      min-height: 86px;
      padding: 18px 26px;
      background:
        linear-gradient(90deg, rgba(207,32,41,.2), transparent 28%),
        linear-gradient(180deg, #151515, #080909);
      color: var(--white);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      border-bottom: 1px solid var(--line-hot);
      box-shadow: 0 16px 45px rgba(0,0,0,.38);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    h1, h2, h3 { margin: 0; letter-spacing: 0; }
    h1 { font-size: clamp(24px, 3vw, 34px); font-weight: 760; line-height: 1; }
    h2 { font-size: 14px; font-weight: 760; color: var(--white); }
    h3 { font-size: 13px; font-weight: 740; color: var(--white); }
    main {
      width: min(1540px, 100%);
      margin: 0 auto;
      padding: 18px;
      display: grid;
      grid-template-columns: minmax(330px, 430px) minmax(0, 1fr);
      gap: 16px;
    }
    aside { display: grid; gap: 16px; align-content: start; }
    section {
      background:
        linear-gradient(180deg, rgba(255,255,255,.035), transparent 44%),
        var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      box-shadow: var(--shadow);
      position: relative;
      overflow: hidden;
    }
    section::before {
      content: "";
      position: absolute;
      inset: 0;
      border-top: 2px solid rgba(207,32,41,.58);
      pointer-events: none;
    }
    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }
    input, select, textarea, button {
      font: inherit;
      border-radius: 6px;
      border: 1px solid #35414b;
      padding: 9px 10px;
      min-width: 0;
    }
    input, select, textarea {
      color: var(--ink);
      background: #090c0f;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.025);
      outline: 0;
    }
    input:focus, select:focus, textarea:focus {
      border-color: var(--red);
      box-shadow: 0 0 0 2px rgba(207,32,41,.22);
    }
    textarea { min-height: 112px; resize: vertical; line-height: 1.45; }
    button {
      min-height: 36px;
      background: linear-gradient(180deg, #d5353d, #9b1c22);
      color: var(--white);
      border: 1px solid rgba(255,255,255,.1);
      cursor: pointer;
      font-weight: 760;
      transition: transform .14s ease, border-color .14s ease, background .14s ease;
    }
    button:hover { transform: translateY(-1px); border-color: rgba(255,255,255,.28); }
    button.secondary { background: linear-gradient(180deg, #35424d, #202932); }
    button.ghost { background: #0b0e11; color: var(--ink); border: 1px solid #35414b; }
    button.danger { background: linear-gradient(180deg, #c41f27, #691216); }
    button.warn { background: linear-gradient(180deg, #d6a13a, #8a5a16); color: #100f0b; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .brand { display: flex; align-items: center; gap: 16px; min-width: 0; }
    .mark {
      width: 62px;
      height: 62px;
      border: 1px solid #403437;
      background: #070707;
      border-radius: 8px;
      display: grid;
      place-items: center;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.04), 0 12px 30px rgba(0,0,0,.42);
      flex: 0 0 auto;
    }
    .lens {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background:
        radial-gradient(circle at 48% 48%, #fff5ec 0 8%, #ff6464 9% 18%, #cf2029 19% 45%, #650d12 46% 100%);
      border: 2px solid #22080a;
      box-shadow: 0 0 24px rgba(207,32,41,.42);
    }
    .kicker { color: var(--amber); font-size: 12px; font-weight: 760; }
    .status {
      color: #f4ead8;
      font-size: 12px;
      overflow-wrap: anywhere;
      text-align: right;
      display: flex;
      align-items: center;
      gap: 9px;
      max-width: 46vw;
      justify-content: flex-end;
    }
    .status::before {
      content: "";
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: var(--green);
      box-shadow: 0 0 16px rgba(104,169,120,.7);
      flex: 0 0 auto;
    }
    .stack { display: grid; gap: 10px; }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .controls { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .wide { grid-column: 1 / -1; }
    .module-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 2px;
    }
    .chip {
      min-height: 25px;
      display: inline-flex;
      align-items: center;
      border: 1px solid #3a4650;
      border-radius: 999px;
      padding: 3px 9px;
      color: var(--muted);
      background: rgba(255,255,255,.035);
      font-size: 12px;
      font-weight: 700;
    }
    .tabs {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      background: #080a0c;
      border: 1px solid #242c34;
      border-radius: 8px;
      padding: 6px;
    }
    .tabs button { background: transparent; color: var(--muted); border: 1px solid transparent; }
    .tabs button.active {
      background: linear-gradient(180deg, #202832, #11161b);
      color: var(--white);
      border-color: #48545f;
      box-shadow: inset 0 2px 0 var(--red);
    }
    .panel { display: none; }
    .panel.active { display: grid; gap: 10px; }
    .feed {
      min-height: 410px;
      max-height: 60vh;
      overflow: auto;
      background:
        linear-gradient(180deg, rgba(207,32,41,.08), transparent 22%),
        #07090b;
      color: #ece7dc;
      border: 1px solid #20282f;
      border-radius: 8px;
      padding: 12px;
      display: grid;
      align-content: start;
      gap: 8px;
    }
    .message, .event, .item {
      border: 1px solid #2a343d;
      border-left: 4px solid var(--blue);
      background: linear-gradient(180deg, rgba(255,255,255,.035), transparent), var(--panel-2);
      border-radius: 6px;
      padding: 9px;
      overflow-wrap: anywhere;
      color: var(--ink);
    }
    .feed .message, .feed .event {
      background: #0f1418;
      border-color: #27313a;
      color: #ece7dc;
    }
    .message.user { border-left-color: var(--green); }
    .message.assistant { border-left-color: var(--red); }
    .event.approval_required { border-left-color: var(--amber); }
    .event.turn_complete { border-left-color: var(--green); }
    .event.turn_started { border-left-color: var(--blue); }
    .meta { color: var(--muted); font-size: 12px; }
    .feed .meta { color: #aeb7bd; }
    .empty {
      min-height: 82px;
      display: grid;
      place-items: center;
      color: var(--muted);
      border: 1px dashed #38434c;
      border-radius: 8px;
      background: rgba(255,255,255,.025);
      padding: 16px;
      text-align: center;
    }
    .composer {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: end;
    }
    .composer label { min-width: 0; }
    .item.selectable {
      width: 100%;
      text-align: left;
      color: var(--ink);
      background: linear-gradient(180deg, rgba(255,255,255,.04), transparent), var(--panel-2);
    }
    .split { display: grid; grid-template-columns: minmax(260px, 380px) minmax(0, 1fr); gap: 12px; }
    .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; }
    .metric {
      border: 1px solid #303a43;
      border-radius: 6px;
      padding: 10px;
      background: #0c1014;
      color: var(--muted);
    }
    .metric strong {
      display: block;
      font-size: 22px;
      color: var(--white);
      line-height: 1.1;
      overflow-wrap: anywhere;
    }
    .graph-box {
      min-height: 390px;
      border: 1px solid #28323a;
      border-radius: 8px;
      overflow: hidden;
      background:
        repeating-linear-gradient(90deg, rgba(255,255,255,.035) 0 1px, transparent 1px 48px),
        repeating-linear-gradient(0deg, rgba(255,255,255,.025) 0 1px, transparent 1px 48px),
        #090c0f;
    }
    svg { width: 100%; height: 360px; display: block; }
    pre { margin: 0; white-space: pre-wrap; font-size: 12px; line-height: 1.45; color: inherit; }
    @media (max-width: 980px) {
      main, .split { grid-template-columns: 1fr; }
      header { align-items: flex-start; flex-direction: column; }
      .status { max-width: 100%; text-align: left; justify-content: flex-start; }
      .feed { max-height: none; }
      .composer { grid-template-columns: 1fr; }
      .tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }

    /* ARC brand graft: architect-paper surface, technical mono controls, restrained data accents. */
    :root {
      --arc-bg: #E8E6E1;
      --arc-paper: #D5D3CE;
      --arc-paper-soft: #eeece7;
      --arc-text: #111111;
      --arc-stone: #666666;
      --arc-border: #C5C3BE;
      --arc-violet: #5E5CE6;
      --arc-violet-soft: #A5B4FC;
      --arc-black: #050505;
      --arc-black-soft: #101010;
      --arc-cyan: #00D4FF;
      --arc-green: #44FF88;
      --arc-amber: #FFAA00;
      --arc-red: #FF4444;
      --bg: var(--arc-bg);
      --panel: var(--arc-paper);
      --panel-2: var(--arc-paper-soft);
      --ink: var(--arc-text);
      --muted: var(--arc-stone);
      --line: var(--arc-border);
      --red: var(--arc-red);
      --amber: var(--arc-amber);
      --blue: var(--arc-cyan);
      --green: var(--arc-green);
      --white: #ffffff;
      --shadow: 0 24px 70px rgba(17, 17, 17, .16);
    }
    html { background: var(--arc-bg); }
    body {
      color: var(--arc-text);
      background:
        linear-gradient(to right, rgba(94,92,230,.08) 0 1px, transparent 1px 20px),
        linear-gradient(to bottom, rgba(94,92,230,.08) 0 1px, transparent 1px 20px),
        linear-gradient(to right, rgba(94,92,230,.12) 0 1px, transparent 1px 100px),
        linear-gradient(to bottom, rgba(94,92,230,.12) 0 1px, transparent 1px 100px),
        var(--arc-bg);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      position: relative;
    }
    body::after {
      content: "";
      position: fixed;
      inset: 0;
      z-index: 0;
      opacity: .18;
      mix-blend-mode: multiply;
      pointer-events: none;
      background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.35'/%3E%3C/svg%3E");
    }
    header {
      min-height: 92px;
      padding: 20px 28px;
      color: #f5f5f5;
      background:
        linear-gradient(90deg, rgba(94,92,230,.18), transparent 34%),
        linear-gradient(to right, rgba(255,255,255,.08) 0 1px, transparent 1px 60px),
        linear-gradient(to bottom, rgba(255,255,255,.08) 0 1px, transparent 1px 60px),
        var(--arc-black);
      border-bottom: 1px solid rgba(94,92,230,.48);
      box-shadow: 0 18px 55px rgba(0,0,0,.28);
    }
    h1 {
      font-family: Newsreader, Georgia, serif;
      font-size: 34px;
      font-weight: 660;
      line-height: 1;
      color: #f7f7f7;
    }
    h2 {
      font-family: Newsreader, Georgia, serif;
      font-size: 24px;
      font-weight: 620;
      color: var(--arc-text);
    }
    h3 {
      font-size: 14px;
      font-weight: 650;
      color: var(--arc-text);
    }
    main {
      padding: 22px;
      gap: 18px;
      position: relative;
      z-index: 1;
    }
    section {
      padding: 16px;
      background:
        linear-gradient(180deg, rgba(255,255,255,.38), rgba(255,255,255,.05)),
        var(--arc-paper);
      border-color: var(--arc-border);
      box-shadow: var(--shadow);
    }
    section::before {
      border-top-color: rgba(94,92,230,.64);
      background:
        linear-gradient(to right, rgba(94,92,230,.08) 0 1px, transparent 1px 20px),
        linear-gradient(to bottom, rgba(94,92,230,.06) 0 1px, transparent 1px 20px);
    }
    label {
      color: var(--arc-stone);
      font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      font-weight: 500;
      text-transform: uppercase;
    }
    input, select, textarea, button {
      border-radius: 4px;
      border-color: var(--arc-border);
    }
    input, select, textarea {
      color: var(--arc-text);
      background: rgba(255,255,255,.42);
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.22);
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
    }
    input:focus, select:focus, textarea:focus {
      border-color: var(--arc-violet);
      box-shadow: 0 0 0 2px rgba(94,92,230,.18);
    }
    button {
      background: var(--arc-violet);
      color: #fff;
      border-color: var(--arc-violet);
      font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      transition: transform .16s ease, border-color .16s ease, background .16s ease, color .16s ease;
    }
    button:hover {
      background: var(--arc-text);
      color: #fff;
      border-color: var(--arc-text);
    }
    button.secondary { background: var(--arc-text); border-color: var(--arc-text); color: #fff; }
    button.ghost { background: transparent; color: var(--arc-text); border-color: rgba(17,17,17,.26); }
    button.ghost:hover { background: var(--arc-text); color: #fff; }
    button.danger { background: transparent; color: var(--arc-red); border-color: rgba(255,68,68,.52); }
    button.danger:hover { background: var(--arc-red); color: #fff; border-color: var(--arc-red); }
    button.warn { background: transparent; color: #7a5200; border-color: rgba(255,170,0,.58); }
    button.warn:hover { background: var(--arc-amber); color: #111; border-color: var(--arc-amber); }
    .mark {
      width: 82px;
      height: 52px;
      border-color: rgba(255,255,255,.18);
      background: rgba(255,255,255,.04);
      border-radius: 4px;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.04), 0 12px 30px rgba(0,0,0,.32);
    }
    .mark span {
      font-family: Newsreader, Georgia, serif;
      font-size: 28px;
      line-height: 1;
      color: #fff;
      font-weight: 760;
    }
    .mark img {
      width: 54px;
      height: 48px;
      object-fit: contain;
      display: block;
      filter: drop-shadow(0 10px 24px rgba(255,255,255,.08));
    }
    .lens { display: none; }
    .kicker {
      color: var(--arc-violet-soft);
      font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
    }
    .status {
      color: #f5f5f5;
      font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      text-transform: uppercase;
      border: 1px solid rgba(255,255,255,.18);
      border-radius: 999px;
      padding: 8px 12px;
      background: rgba(0,0,0,.44);
    }
    .status::before {
      width: 7px;
      height: 7px;
      background: var(--arc-green);
      box-shadow: 0 0 16px rgba(68,255,136,.7);
    }
    .module-head {
      margin-bottom: 4px;
      position: relative;
      z-index: 1;
    }
    .chip {
      border-color: rgba(94,92,230,.42);
      color: var(--arc-violet);
      background: rgba(94,92,230,.08);
      font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
    }
    .tabs {
      background: rgba(255,255,255,.36);
      border-color: var(--arc-border);
    }
    .tabs button { color: var(--arc-stone); }
    .tabs button.active {
      background: var(--arc-text);
      color: #fff;
      border-color: var(--arc-text);
      box-shadow: inset 0 2px 0 var(--arc-violet);
    }
    .feed {
      background:
        linear-gradient(to right, rgba(255,255,255,.07) 0 1px, transparent 1px 60px),
        linear-gradient(to bottom, rgba(255,255,255,.06) 0 1px, transparent 1px 60px),
        var(--arc-black);
      color: #f5f5f5;
      border-color: rgba(17,17,17,.38);
    }
    .message, .event, .item {
      border-color: rgba(17,17,17,.16);
      border-left-color: var(--arc-cyan);
      background:
        linear-gradient(180deg, rgba(255,255,255,.42), transparent),
        var(--arc-paper-soft);
      color: var(--arc-text);
    }
    .feed .message, .feed .event {
      background: rgba(255,255,255,.05);
      border-color: rgba(255,255,255,.12);
      color: #f5f5f5;
    }
    .message.assistant { border-left-color: var(--arc-violet-soft); }
    .event.turn_started { border-left-color: var(--arc-cyan); }
    .meta {
      color: var(--arc-stone);
      font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
    }
    .empty {
      color: var(--arc-stone);
      border-color: rgba(17,17,17,.24);
      background: rgba(255,255,255,.24);
    }
    .item.selectable {
      color: var(--arc-text);
      background:
        linear-gradient(180deg, rgba(255,255,255,.42), transparent),
        var(--arc-paper-soft);
    }
    .metric {
      border-color: rgba(17,17,17,.14);
      background: rgba(255,255,255,.36);
      color: var(--arc-stone);
      font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
    }
    .metric strong {
      color: var(--arc-text);
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
    }
    .graph-box {
      border-color: rgba(17,17,17,.2);
      background:
        linear-gradient(to right, rgba(94,92,230,.1) 0 1px, transparent 1px 48px),
        linear-gradient(to bottom, rgba(94,92,230,.08) 0 1px, transparent 1px 48px),
        rgba(255,255,255,.32);
    }
    pre {
      font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    ::selection { background: var(--arc-violet); color: #fff; }
    @media (max-width: 980px) {
      h1 { font-size: 30px; }
    }

    /* ARC style-guide refinement: Inter product UI, Newsreader only for the mark, Mono for data/code. */
    :root {
      --arc-black: #0A0A0A;
      --arc-black-soft: #111111;
      --arc-paper-soft: #E8E6E1;
      --arc-green: #22C55E;
    }
    body {
      background:
        linear-gradient(to right, rgba(94,92,230,.08) 0 1px, transparent 1px 20px),
        linear-gradient(to bottom, rgba(94,92,230,.08) 0 1px, transparent 1px 20px),
        linear-gradient(to right, rgba(94,92,230,.10) 0 1px, transparent 1px 100px),
        linear-gradient(to bottom, rgba(94,92,230,.10) 0 1px, transparent 1px 100px),
        var(--arc-bg);
    }
    header {
      background:
        linear-gradient(90deg, rgba(94,92,230,.18), transparent 34%),
        linear-gradient(to right, rgba(255,255,255,.08) 0 1px, transparent 1px 60px),
        linear-gradient(to bottom, rgba(255,255,255,.08) 0 1px, transparent 1px 60px),
        var(--arc-black);
    }
    h1 {
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      font-size: 32px;
      font-weight: 600;
      line-height: 1.02;
    }
    h2 {
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      font-size: 22px;
      font-weight: 600;
      color: var(--arc-text);
    }
    h3,
    .tile h3 {
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      font-weight: 600;
    }
    .kicker,
    label,
    button,
    .chip {
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      font-weight: 600;
      letter-spacing: 0;
    }
    .status,
    .meta,
    .metric,
    .metric strong,
    pre {
      font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
      font-variant-numeric: tabular-nums;
    }
    .mark span {
      font-family: Newsreader, Georgia, serif;
      font-weight: 400;
    }
    .feed {
      background:
        linear-gradient(to right, rgba(255,255,255,.07) 0 1px, transparent 1px 60px),
        linear-gradient(to bottom, rgba(255,255,255,.06) 0 1px, transparent 1px 60px),
        var(--arc-black);
    }
    @media (max-width: 980px) {
      h1 { font-size: 30px; }
      h2 { font-size: 22px; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="mark" aria-hidden="true"><img src="/assets/arc-logo-metal.png" alt=""></div>
      <div>
        <div class="kicker">Autonomous Resource Corporation</div>
        <h1>HAL-9000 Research Console</h1>
      </div>
    </div>
    <div id="status" class="status">Ready</div>
  </header>
  <main>
    <aside>
      <section class="stack">
        <div class="module-head">
          <h2>Session</h2>
          <span class="chip">Agent Runtime</span>
        </div>
        <div class="controls">
          <label>User email <input id="userEmail" value="reviewer@example.com"></label>
          <label>Run id <input id="runId" placeholder="optional"></label>
          <label class="wide">Session id <input id="agentSessionId" placeholder="auto"></label>
          <label class="wide">Model <select id="modelName"></select></label>
          <label>Reasoning <select id="reasoningEffort"></select></label>
          <label>Project slug <input id="projectSlug" placeholder="firm-research"></label>
        </div>
        <div class="row">
          <button id="createSessionButton" onclick="createSession()">Create Session</button>
          <button class="secondary" onclick="refreshAgent()">Refresh</button>
          <button class="warn" onclick="compactSession()">Compact</button>
          <button class="danger" onclick="interruptSession()">Interrupt</button>
        </div>
      </section>
      <section class="stack">
        <div class="module-head">
          <h2>Approval Queue</h2>
          <span class="chip">Human Gate</span>
        </div>
        <div id="approvals" class="stack"></div>
      </section>
    </aside>
    <section class="stack">
      <div class="tabs">
        <button id="tabChat" class="active" onclick="showPanel('chat')">Chat</button>
        <button id="tabReview" onclick="showPanel('review')">Review</button>
        <button id="tabEvidence" onclick="showPanel('evidence')">Evidence</button>
        <button id="tabGraph" onclick="showPanel('graph')">Graph</button>
      </div>
      <div id="panelChat" class="panel active">
        <div id="feed" class="feed"></div>
        <div class="composer">
          <label>Command <textarea id="messageText" placeholder="Enter command"></textarea></label>
          <button onclick="submitMessage()">Transmit</button>
        </div>
        <div class="row">
          <button class="ghost" onclick="refreshAgent()">Replay</button>
        </div>
      </div>
      <div id="panelReview" class="panel">
        <div class="module-head">
          <h2>Review</h2>
          <span class="chip">Evidence Queue</span>
        </div>
        <div class="row">
          <button onclick="loadReview()">Load Review</button>
          <button class="ghost" onclick="loadReview(true)">Run Detail</button>
        </div>
        <div class="split">
          <div id="reviewQueue" class="stack"></div>
          <div id="reviewDetail" class="stack"></div>
        </div>
      </div>
      <div id="panelEvidence" class="panel">
        <div class="module-head">
          <h2>Evidence</h2>
          <span class="chip">Source Backing</span>
        </div>
        <div class="row"><button onclick="loadEvidence()">Load Evidence</button></div>
        <div id="evidencePanel" class="stack"></div>
      </div>
      <div id="panelGraph" class="panel">
        <div class="module-head">
          <h2>Graph</h2>
          <span class="chip">Entity Field</span>
        </div>
        <div class="row"><button onclick="loadGraph()">Load Graph</button></div>
        <div class="graph-box"><svg id="graphSvg" viewBox="0 0 900 360"></svg></div>
        <div id="graphSummary" class="stack"></div>
      </div>
    </section>
  </main>
<script>
const state = { session: null, lastSequence: 0, events: [], history: [] };
const $ = (id) => document.getElementById(id);
function setStatus(text) { $('status').textContent = text; }
function value(id) { return $(id).value.trim(); }
function esc(text) {
  return String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {'Content-Type': 'application/json'},
    ...options
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}
async function boot() {
  const config = await api('/api/frontend/config');
  $('modelName').innerHTML = config.models.map(m => `<option value="${esc(m)}">${esc(m)}</option>`).join('');
  $('reasoningEffort').innerHTML = config.reasoning_efforts.map(e => `<option value="${esc(e)}">${esc(e || 'default')}</option>`).join('');
  $('modelName').value = config.default_model;
  if (config.reasoning_effort) $('reasoningEffort').value = config.reasoning_effort;
  renderFeed();
}
function showPanel(name) {
  for (const panel of ['chat','review','evidence','graph']) {
    $('panel' + cap(panel)).classList.toggle('active', panel === name);
    $('tab' + cap(panel)).classList.toggle('active', panel === name);
  }
}
function cap(text) { return text.charAt(0).toUpperCase() + text.slice(1); }
async function createSession() {
  setStatus('Creating session...');
  const button = $('createSessionButton');
  if (button) {
    button.disabled = true;
    button.textContent = 'Creating...';
  }
  try {
    const body = {
      agent_session_id: value('agentSessionId') || undefined,
      user_id: value('userEmail') || undefined,
      run_id: value('runId') || undefined,
      metadata: {
        model_name: value('modelName') || undefined,
        reasoning_effort: value('reasoningEffort') || undefined
      }
    };
    const payload = await api('/api/agent/session', {method: 'POST', body: JSON.stringify(body)});
    state.session = payload.agent_session;
    $('agentSessionId').value = state.session.id;
    applyEvents(payload.events || []);
    setStatus(`Session ready · ${state.session.id.slice(0, 8)}`);
    return payload;
  } catch (error) {
    setStatus(`Session error: ${error.message || error}`);
    renderFeed();
    throw error;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = 'Create Session';
    }
  }
}
async function submitMessage() {
  if (!value('agentSessionId')) await createSession();
  const text = value('messageText');
  if (!text) return;
  $('messageText').value = '';
  await api('/api/agent/submit', {method: 'POST', body: JSON.stringify({agent_session_id: value('agentSessionId'), text})});
  setStatus('Submitted');
  setTimeout(refreshAgent, 400);
}
async function refreshAgent() {
  const id = value('agentSessionId');
  if (!id) return;
  const replay = await api(`/api/agent/replay?agent_session_id=${encodeURIComponent(id)}&after_sequence=${state.lastSequence}`);
  state.session = replay.agent_session;
  applyEvents(replay.events || []);
  const history = await api(`/api/agent/history?agent_session_id=${encodeURIComponent(id)}&include_system=false`);
  state.history = history.messages || [];
  renderFeed();
  setStatus(`Events ${state.events.length}`);
}
function applyEvents(events) {
  for (const event of events) {
    state.events.push(event);
    if (event.sequence && event.sequence > state.lastSequence) state.lastSequence = event.sequence;
  }
  renderApprovals();
  renderFeed();
}
async function approve(id, approved) {
  await api('/api/agent/approve', {method: 'POST', body: JSON.stringify({
    agent_session_id: value('agentSessionId'),
    approval_id: id,
    approved,
    actor: value('userEmail') || 'human'
  })});
  setTimeout(refreshAgent, 400);
}
async function interruptSession() {
  await api('/api/agent/interrupt', {method: 'POST', body: JSON.stringify({agent_session_id: value('agentSessionId'), actor: value('userEmail')})});
  setTimeout(refreshAgent, 250);
}
async function compactSession() {
  await api('/api/agent/compact', {method: 'POST', body: JSON.stringify({agent_session_id: value('agentSessionId')})});
  setTimeout(refreshAgent, 250);
}
function renderApprovals() {
  const approvals = state.session?.pending_approvals || [];
  $('approvals').innerHTML = approvals.length ? approvals.map(a => `
    <div class="item">
      <h3>${esc(a.tool_name || a.tool_call?.name || 'Tool approval')}</h3>
      <div class="meta">${esc(a.approval_id || a.id)}</div>
      <pre>${esc(JSON.stringify(a.arguments || a.tool_call?.arguments || {}, null, 2))}</pre>
      <div class="row">
        <button onclick="approve('${esc(a.approval_id || a.id)}', true)">Approve</button>
        <button class="danger" onclick="approve('${esc(a.approval_id || a.id)}', false)">Reject</button>
      </div>
    </div>`).join('') : '<div class="empty">No pending approvals.</div>';
}
function renderFeed() {
  const messages = state.history.map(m => `<div class="message ${esc(m.role)}"><div class="meta">${esc(m.role)}</div><pre>${esc(m.content || JSON.stringify(m))}</pre></div>`);
  const events = state.events.slice(-20).map(e => `<div class="event ${esc(e.type)}"><div class="meta">#${esc(e.sequence)} ${esc(e.type)}</div><pre>${esc(JSON.stringify(e.data || {}, null, 2))}</pre></div>`);
  const session = state.session ? `<div class="message assistant"><div class="meta">session ready</div><pre>${esc(JSON.stringify({
    id: state.session.id,
    user_id: state.session.user_id,
    run_id: state.session.run_id,
    events: state.session.event_count,
    pending_approvals: state.session.pending_approvals?.length || 0
  }, null, 2))}</pre></div>` : '';
  $('feed').innerHTML = [session].concat(messages, events).filter(Boolean).join('') || '<div class="empty">Create a session to begin.</div>';
}
async function loadReview(detailOnly = false) {
  const params = new URLSearchParams({reviewer: value('userEmail') || 'reviewer@example.com'});
  if (value('projectSlug')) params.set('project_slug', value('projectSlug'));
  if (detailOnly && value('runId')) params.set('run_id', value('runId'));
  const payload = await api('/api/frontend/review?' + params.toString());
  $('reviewQueue').innerHTML = (payload.queue || []).map(item => `
    <button class="item selectable" onclick="$('runId').value='${esc(item.run_id)}'; loadReview(true);">
      <h3>${esc(item.project_slug || '-')}</h3>
      <div>${esc(item.objective)}</div>
      <div class="meta">${esc(item.run_id)} · outputs ${esc(item.output_count)}</div>
    </button>`).join('') || '<div class="empty">No review items.</div>';
  const detail = payload.detail;
  $('reviewDetail').innerHTML = detail ? `
    <div class="metric-grid">
      <div class="metric"><span>Status</span><strong>${esc(detail.status)}</strong></div>
      <div class="metric"><span>Outputs</span><strong>${esc(detail.outputs.length)}</strong></div>
    </div>
    <div class="item"><h3>${esc(detail.objective)}</h3><div class="meta">${esc(detail.run_id)}</div></div>
    ${(detail.outputs || []).map(o => `<div class="item"><h3>${esc(o.title)}</h3><div class="meta">${esc(o.status)} · ${esc(o.output_type)}</div><pre>${esc((o.content || '').slice(0, 1000))}</pre></div>`).join('')}` : '<div class="empty">Select a run for detail.</div>';
}
async function loadEvidence() {
  const runId = value('runId');
  if (!runId) return setStatus('Run id is required for evidence.');
  const params = new URLSearchParams({run_id: runId, viewer: value('userEmail') || 'reviewer@example.com'});
  const payload = await api('/api/frontend/evidence?' + params.toString());
  $('evidencePanel').innerHTML = `
    <div class="metric-grid">
      <div class="metric"><span>Claims</span><strong>${payload.claims.length}</strong></div>
      <div class="metric"><span>Chunks</span><strong>${payload.chunks.length}</strong></div>
      <div class="metric"><span>Outputs</span><strong>${payload.outputs.length}</strong></div>
    </div>
    ${(payload.claims || []).map(c => `<div class="item"><h3>${esc(c.claim_type)} · ${esc(c.confidence)}</h3><div>${esc(c.claim_text)}</div><div class="meta">${esc(c.evidence_text || '')}</div></div>`).join('') || '<div class="empty">No claims for this run.</div>'}`;
}
async function loadGraph() {
  const params = new URLSearchParams({viewer: value('userEmail') || 'reviewer@example.com'});
  if (value('runId')) params.set('run_id', value('runId'));
  else if (value('projectSlug')) params.set('project_slug', value('projectSlug'));
  else return setStatus('Project slug or run id is required for graph.');
  const graph = await api('/api/frontend/graph?' + params.toString());
  drawGraph(graph);
  $('graphSummary').innerHTML = `<div class="metric-grid">
    <div class="metric"><span>Nodes</span><strong>${graph.nodes.length}</strong></div>
    <div class="metric"><span>Edges</span><strong>${graph.edges.length}</strong></div>
    <div class="metric"><span>Scope</span><strong>${esc(graph.scope)}</strong></div>
  </div>`;
}
function drawGraph(graph) {
  const svg = $('graphSvg');
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  const radius = 130;
  const cx = 450, cy = 180;
  const positions = new Map(nodes.map((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(nodes.length, 1);
    return [node.key, {x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius, node}];
  }));
  const lines = edges.map(edge => {
    const a = positions.get(edge.source_key), b = positions.get(edge.target_key);
    if (!a || !b) return '';
    return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#5E5CE6" stroke-opacity="0.46" stroke-width="1.5"><title>${esc(edge.relationship_type)}</title></line>`;
  }).join('');
  const circles = [...positions.values()].map(p => `
    <g>
      <circle cx="${p.x}" cy="${p.y}" r="20" fill="#050505" stroke="#5E5CE6" stroke-width="3"></circle>
      <circle cx="${p.x}" cy="${p.y}" r="6" fill="#00D4FF"></circle>
      <text x="${p.x}" y="${p.y + 38}" text-anchor="middle" font-size="11" fill="#111111">${esc(String(p.node.label || p.node.entity_type).slice(0, 18))}</text>
    </g>`).join('');
  svg.innerHTML = lines + circles;
}
window.addEventListener('unhandledrejection', event => setStatus(`Error: ${event.reason?.message || event.reason}`));
window.addEventListener('error', event => setStatus(`Error: ${event.message}`));
boot().catch(error => setStatus(error.message));
</script>
</body>
</html>"""


def _run_payload(run: ResearchRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "objective": run.objective,
        "project_slug": run.project.slug if run.project else None,
        "program": run.program.name if run.program else None,
        "created_at": _iso(run.created_at),
        "updated_at": _iso(run.updated_at),
    }


def _output_payload(output) -> dict[str, Any]:
    return {
        "id": output.id,
        "output_type": output.output_type,
        "title": output.title,
        "status": output.status,
        "format": output.format,
        "artifact_uri": output.artifact_uri,
        "content": output.content,
        "source": _json_or_none(output.source_json),
        "created_at": _iso(output.created_at),
    }


def _claim_payload(claim) -> dict[str, Any]:
    return {
        "id": claim.id,
        "claim_text": claim.claim_text,
        "claim_type": claim.claim_type,
        "confidence": claim.confidence,
        "evidence_text": claim.evidence_text,
        "status": claim.status,
        "document_id": claim.document_id,
        "chunk_id": claim.chunk_id,
        "provenance": _json_or_none(claim.provenance_json),
        "evidence_links": [
            {
                "id": evidence.id,
                "source_url": evidence.source_url,
                "quote": evidence.quote,
                "locator": evidence.locator,
                "evidence_type": evidence.evidence_type,
                "confidence": evidence.confidence,
            }
            for evidence in claim.evidence_links
        ],
    }


def _chunk_payload(chunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "document_id": chunk.document_id,
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "token_count": chunk.token_count,
        "document_title": chunk.document.title if chunk.document else None,
    }


def _require_run(store: ResearchStore, run_id: str) -> ResearchRun:
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Research run not found: {run_id}")
    return run


def _json_or_none(raw_value: str | None) -> Any:
    if not raw_value:
        return None
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return None


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _unique(values: list[str]) -> list[str]:
    seen = set()
    unique_values = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values
