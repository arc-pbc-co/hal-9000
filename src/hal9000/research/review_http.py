"""Lightweight HTTP review UI over HAL review services."""

from __future__ import annotations

import json
from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.research.annotations import ReviewAnnotationService, annotation_payload
from hal9000.research.authz import AuthorizationError, ResearchAuthorizer
from hal9000.research.collaboration import CollaborationService, audit_event_payload
from hal9000.research.review import ResearchReviewService


class ReviewHTTPError(Exception):
    """HTTP-shaped error for review UI requests."""

    def __init__(self, status: HTTPStatus, message: str):
        """Initialize with status and message."""
        self.status = status
        self.message = message
        super().__init__(message)


def create_review_http_handler(settings):
    """Create a request handler bound to HAL settings."""

    class ReviewHTTPRequestHandler(BaseHTTPRequestHandler):
        """HTTP handler for the lightweight review UI."""

        server_version = "HALReviewUI/0.1"

        def do_GET(self) -> None:
            """Handle review UI and read API requests."""
            try:
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    self._send_html(_review_ui_html())
                    return
                if parsed.path == "/health":
                    self._send_json({"status": "ok"})
                    return
                if parsed.path == "/api/review-queue":
                    params = parse_qs(parsed.query)
                    reviewer = _required_param(params, "reviewer")
                    project_slug = _optional_param(params, "project_slug")
                    limit = int(_optional_param(params, "limit") or "20")
                    self._with_store(
                        lambda store: self._send_json(
                            _review_queue_payload(store, reviewer, project_slug, limit)
                        )
                    )
                    return
                if parsed.path == "/api/review-detail":
                    params = parse_qs(parsed.query)
                    run_id = _required_param(params, "run_id")
                    reviewer = _required_param(params, "reviewer")
                    self._with_store(
                        lambda store: self._send_json(
                            _review_detail_payload(store, run_id, reviewer)
                        )
                    )
                    return
                if parsed.path == "/api/review-comments":
                    params = parse_qs(parsed.query)
                    target_type = _required_param(params, "target_type")
                    target_id = _required_param(params, "target_id")
                    viewer = _required_param(params, "viewer")
                    include_resolved = _bool_param(params, "include_resolved")
                    self._with_store(
                        lambda store: self._send_json(
                            _review_comments_payload(
                                store,
                                target_type,
                                target_id,
                                viewer,
                                include_resolved,
                            )
                        )
                    )
                    return
                if parsed.path == "/api/audit-events":
                    params = parse_qs(parsed.query)
                    reviewer = _required_param(params, "reviewer")
                    project_slug = _optional_param(params, "project_slug")
                    run_id = _optional_param(params, "run_id")
                    action = _optional_param(params, "action")
                    target_type = _optional_param(params, "target_type")
                    limit = int(_optional_param(params, "limit") or "30")
                    self._with_store(
                        lambda store: self._send_json(
                            _audit_events_payload(
                                store,
                                reviewer=reviewer,
                                project_slug=project_slug,
                                run_id=run_id,
                                action=action,
                                target_type=target_type,
                                limit=limit,
                            )
                        )
                    )
                    return
                if parsed.path == "/api/audit-dashboard":
                    params = parse_qs(parsed.query)
                    reviewer = _required_param(params, "reviewer")
                    project_slug = _optional_param(params, "project_slug")
                    run_id = _optional_param(params, "run_id")
                    action = _optional_param(params, "action")
                    target_type = _optional_param(params, "target_type")
                    limit = int(_optional_param(params, "limit") or "100")
                    self._with_store(
                        lambda store: self._send_json(
                            _audit_dashboard_payload(
                                store,
                                reviewer=reviewer,
                                project_slug=project_slug,
                                run_id=run_id,
                                action=action,
                                target_type=target_type,
                                limit=limit,
                            )
                        )
                    )
                    return
                raise ReviewHTTPError(HTTPStatus.NOT_FOUND, f"Unknown path: {parsed.path}")
            except Exception as exc:
                self._send_error(exc)

        def do_POST(self) -> None:
            """Handle review write API requests."""
            try:
                parsed = urlparse(self.path)
                payload = self._read_json_body()
                if parsed.path == "/api/review-run":
                    self._with_store(
                        lambda store: self._send_json(
                            _review_run_payload(store, payload),
                            status=HTTPStatus.CREATED,
                        )
                    )
                    return
                if parsed.path == "/api/review-comment":
                    self._with_store(
                        lambda store: self._send_json(
                            _add_review_comment_payload(store, payload),
                            status=HTTPStatus.CREATED,
                        )
                    )
                    return
                if parsed.path == "/api/review-comment/resolve":
                    self._with_store(
                        lambda store: self._send_json(
                            _resolve_review_comment_payload(store, payload),
                        )
                    )
                    return
                raise ReviewHTTPError(HTTPStatus.NOT_FOUND, f"Unknown path: {parsed.path}")
            except Exception as exc:
                self._send_error(exc)

        def log_message(self, format: str, *args) -> None:
            """Keep the default server quiet for CLI use."""
            return

        def _with_store(self, callback):
            _, session_local = init_db(settings.database.url)
            session = session_local()
            try:
                store = ResearchStore(session)
                result = callback(store)
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                raise ReviewHTTPError(HTTPStatus.BAD_REQUEST, "Request body is required")
            raw = self.rfile.read(length).decode("utf-8")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ReviewHTTPError(HTTPStatus.BAD_REQUEST, f"Invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ReviewHTTPError(HTTPStatus.BAD_REQUEST, "Request body must be a JSON object")
            return payload

        def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = html.encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _send_json(
            self,
            payload: dict[str, Any] | list[dict[str, Any]],
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _send_error(self, exc: Exception) -> None:
            if isinstance(exc, ReviewHTTPError):
                status = exc.status
                message = exc.message
            else:
                status = (
                    HTTPStatus.FORBIDDEN
                    if isinstance(exc, (AuthorizationError, PermissionError))
                    else HTTPStatus.BAD_REQUEST
                )
                message = str(exc)
            self._send_json(
                {"error": message, "status": status.value},
                status=status,
            )

    return ReviewHTTPRequestHandler


def run_review_http_server(settings, host: str, port: int) -> None:
    """Run the lightweight review UI HTTP server forever."""
    server = create_review_http_server(settings, host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def create_review_http_server(settings, host: str, port: int) -> ThreadingHTTPServer:
    """Create a review UI server bound to settings."""
    return ThreadingHTTPServer((host, port), create_review_http_handler(settings))


def _review_queue_payload(
    store: ResearchStore,
    reviewer: str,
    project_slug: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    project = None
    if project_slug:
        project = store.get_project_by_slug(project_slug)
        if project is None:
            raise ReviewHTTPError(HTTPStatus.NOT_FOUND, f"Research project not found: {project_slug}")
    return [
        item.__dict__
        for item in ResearchReviewService(store).list_review_queue(
            reviewer_email=reviewer,
            project=project,
            limit=limit,
        )
    ]


def _review_detail_payload(
    store: ResearchStore,
    run_id: str,
    reviewer: str,
) -> dict[str, Any]:
    run = store.get_run(run_id)
    if run is None:
        raise ReviewHTTPError(HTTPStatus.NOT_FOUND, f"Research run not found: {run_id}")
    return ResearchReviewService(store).get_review_detail(run, reviewer_email=reviewer).to_dict()


def _review_run_payload(store: ResearchStore, payload: dict[str, Any]) -> dict[str, Any]:
    run_id = _required_body(payload, "run_id")
    reviewer = _required_body(payload, "reviewer")
    decision = _required_body(payload, "decision")
    run = store.get_run(run_id)
    if run is None:
        raise ReviewHTTPError(HTTPStatus.NOT_FOUND, f"Research run not found: {run_id}")
    result = ResearchReviewService(store).review_run(
        run,
        decision=decision,
        reviewer_email=reviewer,
        rationale=payload.get("rationale"),
    )
    return {
        "run_id": result.run.id,
        "status": result.run.status,
        "decision_count": len(result.decisions),
        "event_type": result.event.event_type,
        "event_sequence": result.event.sequence,
    }


def _add_review_comment_payload(store: ResearchStore, payload: dict[str, Any]) -> dict[str, Any]:
    annotation = ReviewAnnotationService(store).add_annotation(
        target_type=_required_body(payload, "target_type"),
        target_id=_required_body(payload, "target_id"),
        body=_required_body(payload, "body"),
        author_email=_required_body(payload, "author"),
        annotation_type=payload.get("annotation_type") or "comment",
    )
    return annotation_payload(annotation).to_dict()


def _review_comments_payload(
    store: ResearchStore,
    target_type: str,
    target_id: str,
    viewer: str,
    include_resolved: bool,
) -> list[dict[str, Any]]:
    return [
        annotation_payload(annotation).to_dict()
        for annotation in ReviewAnnotationService(store).list_annotations(
            target_type=target_type,
            target_id=target_id,
            viewer_email=viewer,
            include_resolved=include_resolved,
        )
    ]


def _audit_events_payload(
    store: ResearchStore,
    reviewer: str,
    project_slug: str | None,
    run_id: str | None,
    limit: int,
    action: str | None = None,
    target_type: str | None = None,
) -> list[dict[str, Any]]:
    project, run = _authorized_audit_scope(store, reviewer, project_slug, run_id)
    return [
        audit_event_payload(event)
        for event in CollaborationService(store).list_audit_events(
            project=project,
            run=run,
            action=action,
            target_type=target_type,
            limit=limit,
        )
    ]


def _audit_dashboard_payload(
    store: ResearchStore,
    reviewer: str,
    project_slug: str | None,
    run_id: str | None,
    action: str | None,
    target_type: str | None,
    limit: int,
) -> dict[str, Any]:
    project, run = _authorized_audit_scope(store, reviewer, project_slug, run_id)
    events = CollaborationService(store).list_audit_events(
        project=project,
        run=run,
        action=action,
        target_type=target_type,
        limit=limit,
    )
    payloads = [audit_event_payload(event) for event in events]
    return {
        "scope": {
            "project_slug": project.slug if project else None,
            "run_id": run.id if run else None,
            "action": action,
            "target_type": target_type,
        },
        "summary": {
            "total": len(payloads),
            "by_action": dict(Counter(payload["action"] for payload in payloads)),
            "by_target_type": dict(Counter(payload["target_type"] for payload in payloads)),
            "by_actor": dict(Counter(payload["actor_email"] or "-" for payload in payloads)),
        },
        "events": payloads,
    }


def _authorized_audit_scope(
    store: ResearchStore,
    reviewer: str,
    project_slug: str | None,
    run_id: str | None,
):
    project = None
    run = None
    authorizer = ResearchAuthorizer(store)
    if run_id:
        run = store.get_run(run_id)
        if run is None:
            raise ReviewHTTPError(HTTPStatus.NOT_FOUND, f"Research run not found: {run_id}")
        project = run.project
        authorizer.require_run_role(run, reviewer, "viewer")
    elif project_slug:
        project = store.get_project_by_slug(project_slug)
        if project is None:
            raise ReviewHTTPError(HTTPStatus.NOT_FOUND, f"Research project not found: {project_slug}")
        authorizer.require_project_role(project, reviewer, "viewer")
    else:
        authorizer.require_project_role(None, reviewer, "admin")
    return project, run


def _resolve_review_comment_payload(store: ResearchStore, payload: dict[str, Any]) -> dict[str, Any]:
    annotation = ReviewAnnotationService(store).resolve_annotation(
        _required_body(payload, "annotation_id"),
        resolver_email=_required_body(payload, "resolver"),
    )
    return annotation_payload(annotation).to_dict()


def _required_param(params: dict[str, list[str]], name: str) -> str:
    value = _optional_param(params, name)
    if not value:
        raise ReviewHTTPError(HTTPStatus.BAD_REQUEST, f"Missing required query parameter: {name}")
    return value


def _optional_param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name) or []
    return values[0] if values else None


def _bool_param(params: dict[str, list[str]], name: str) -> bool:
    value = (_optional_param(params, name) or "").lower()
    return value in {"1", "true", "yes", "on"}


def _required_body(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ReviewHTTPError(HTTPStatus.BAD_REQUEST, f"Missing required field: {name}")
    return value.strip()


def _review_ui_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HAL 9000 Review</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f5f6f4; color: #1f2933; }
    header { background: #18202a; color: white; padding: 18px 28px; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    h1, h2, h3 { margin: 0; letter-spacing: 0; }
    h1 { font-size: 22px; }
    h2 { font-size: 17px; }
    h3 { font-size: 14px; }
    main { max-width: 1240px; margin: 0 auto; padding: 20px; display: grid; gap: 16px; }
    section { background: white; border: 1px solid #d8ddd6; border-radius: 8px; padding: 16px; }
    label { display: grid; gap: 6px; font-size: 13px; color: #394956; }
    input, textarea, select, button { font: inherit; border: 1px solid #cbd5dc; border-radius: 6px; padding: 9px 10px; min-width: 0; }
    textarea { min-height: 88px; resize: vertical; }
    button { background: #235789; color: white; border: 0; cursor: pointer; min-height: 38px; }
    button.secondary { background: #64748b; }
    button.warn { background: #9a3412; }
    button.danger { background: #991b1b; }
    button.ghost { background: #eef2f7; color: #253242; border: 1px solid #cbd5dc; }
    .status { color: #d9e8f5; font-size: 13px; text-align: right; overflow-wrap: anywhere; }
    .controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; align-items: end; }
    .grid { display: grid; grid-template-columns: minmax(280px, 380px) 1fr; gap: 16px; }
    .stack { display: grid; gap: 12px; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .inline-filter { min-width: 180px; max-width: 240px; }
    .run { width: 100%; text-align: left; background: #fbfcfd; color: #1f2933; border: 1px solid #d8ddd6; border-radius: 6px; padding: 12px; margin-top: 10px; }
    .run:hover, .output:hover, .output.selected { border-color: #235789; }
    .muted { color: #667382; font-size: 13px; }
    pre { white-space: pre-wrap; background: #101820; color: #e6edf3; padding: 14px; border-radius: 6px; max-height: 280px; overflow: auto; }
    .outputs, .comments { display: grid; gap: 10px; }
    .output, .comment, .audit-event { border: 1px solid #d8ddd6; border-left: 4px solid #235789; background: #f8fafc; padding: 10px 12px; border-radius: 4px; cursor: pointer; }
    .comment, .audit-event { cursor: default; border-left-color: #64748b; }
    .audit-event { border-left-color: #4f6f52; }
    .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }
    .metric { border: 1px solid #d8ddd6; border-radius: 6px; padding: 10px; background: #fbfcfd; }
    .metric strong { display: block; font-size: 20px; color: #1f2933; }
    .pill { display: inline-flex; padding: 2px 7px; border-radius: 999px; background: #e7eef6; color: #235789; font-size: 12px; }
    @media (max-width: 820px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>HAL 9000 Review</h1>
    <div id="status" class="status">Ready</div>
  </header>
  <main>
    <section class="controls">
      <label>Reviewer email <input id="reviewer" value="bryanwisk@arc-pbc.com"></label>
      <label>Project slug <input id="project" placeholder="firm-research"></label>
      <button onclick="loadQueue()">Load Review Queue</button>
    </section>
    <section class="grid">
      <div class="stack">
        <h2>Queue</h2>
        <div id="queue"></div>
      </div>
      <div class="stack">
        <div class="row">
          <h2>Detail</h2>
          <button class="ghost" onclick="refreshDetail()">Refresh</button>
        </div>
        <div id="detail" class="stack"></div>
        <div class="row">
          <button onclick="reviewRun('promote')">Promote</button>
          <button class="warn" onclick="reviewRun('request-changes')">Request Changes</button>
          <button class="danger" onclick="reviewRun('reject')">Reject</button>
        </div>
        <label>Review rationale <textarea id="rationale" placeholder="Decision notes"></textarea></label>
        <h3>Selected Output</h3>
        <pre id="outputContent">Select an output to inspect its content.</pre>
        <h3>Comments</h3>
        <div class="row">
          <select id="annotationType">
            <option value="comment">Comment</option>
            <option value="change_request">Change request</option>
            <option value="question">Question</option>
            <option value="note">Note</option>
          </select>
          <button class="ghost" onclick="loadComments()">Refresh Comments</button>
        </div>
        <label>Comment <textarea id="commentBody" placeholder="Add a note on the selected output"></textarea></label>
        <button onclick="addComment()">Add Comment</button>
        <div id="comments" class="comments"></div>
      </div>
    </section>
    <section class="stack">
      <div class="row">
        <h2>Audit</h2>
        <input id="auditAction" class="inline-filter" placeholder="Filter action">
        <input id="auditTarget" class="inline-filter" placeholder="Filter target type">
        <button class="ghost" onclick="loadAudit()">Refresh Audit</button>
      </div>
      <div id="auditSummary" class="metric-grid"></div>
      <div id="audit" class="stack"></div>
    </section>
  </main>
  <script>
    let currentRunId = null;
    let currentDetail = null;
    let selectedOutputId = null;

    const reviewer = () => document.getElementById('reviewer').value.trim();
    const status = (text) => { document.getElementById('status').textContent = text; };
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));

    async function api(path, options) {
      const res = await fetch(path, options);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Request failed');
      return json;
    }

    async function loadQueue() {
      try {
        status('Loading queue');
        const project = document.getElementById('project').value.trim();
        const query = new URLSearchParams({ reviewer: reviewer() });
        if (project) query.set('project_slug', project);
        const rows = await api('/api/review-queue?' + query.toString());
        document.getElementById('queue').innerHTML = rows.map(row => `
          <button class="run" data-run="${esc(row.run_id)}">
            <strong>${esc(row.project_slug || '-')}</strong><br>
            ${esc(row.objective)}<br>
            <span class="muted">${esc(row.output_count)} outputs - ${esc(row.run_id)}</span>
          </button>
        `).join('') || '<p class="muted">No review-ready runs.</p>';
        document.querySelectorAll('.run').forEach(node => {
          node.addEventListener('click', () => loadDetail(node.dataset.run));
        });
        status(`Loaded ${rows.length} run(s)`);
      } catch (err) {
        status(err.message);
      }
    }

    async function loadDetail(runId) {
      try {
        status('Loading detail');
        const query = new URLSearchParams({ run_id: runId, reviewer: reviewer() });
        currentDetail = await api('/api/review-detail?' + query.toString());
        currentRunId = currentDetail.run_id;
        selectedOutputId = currentDetail.outputs[0]?.id || null;
        renderDetail();
        await loadComments();
        await loadAudit();
        status(`Loaded ${currentRunId}`);
      } catch (err) {
        status(err.message);
      }
    }

    async function refreshDetail() {
      if (currentRunId) await loadDetail(currentRunId);
    }

    function renderDetail() {
      const outputs = currentDetail.outputs.map(out => `
        <button class="output ${out.id === selectedOutputId ? 'selected' : ''}" data-output="${esc(out.id)}">
          <strong>${esc(out.title)}</strong><br>
          <span class="pill">${esc(out.output_type)}</span>
          <span class="muted">${esc(out.status)} - ${esc(out.format)}</span>
        </button>
      `).join('');
      document.getElementById('detail').innerHTML = `
        <div><span class="pill">${esc(currentDetail.status)}</span> <span class="muted">${esc(currentDetail.project_slug || '-')}</span></div>
        <div>${esc(currentDetail.objective)}</div>
        <div class="outputs">${outputs}</div>
      `;
      document.querySelectorAll('.output').forEach(node => {
        node.addEventListener('click', () => selectOutput(node.dataset.output));
      });
      selectOutput(selectedOutputId);
    }

    function selectOutput(outputId) {
      selectedOutputId = outputId;
      const output = currentDetail?.outputs.find(candidate => candidate.id === outputId);
      document.querySelectorAll('.output').forEach(node => {
        node.classList.toggle('selected', node.dataset.output === outputId);
      });
      document.getElementById('outputContent').textContent = output?.content || 'No inline content.';
      loadComments();
    }

    async function loadComments() {
      if (!selectedOutputId) {
        document.getElementById('comments').innerHTML = '<p class="muted">No output selected.</p>';
        return;
      }
      try {
        const query = new URLSearchParams({
          target_type: 'output',
          target_id: selectedOutputId,
          viewer: reviewer(),
          include_resolved: 'true'
        });
        const rows = await api('/api/review-comments?' + query.toString());
        document.getElementById('comments').innerHTML = rows.map(row => `
          <div class="comment">
            <div class="row">
              <span class="pill">${esc(row.annotation_type)}</span>
              <span class="muted">${esc(row.status)} - ${esc(row.author_email || '-')}</span>
              ${row.status === 'open' ? `<button class="ghost" data-resolve="${esc(row.id)}">Resolve</button>` : ''}
            </div>
            <div>${esc(row.body)}</div>
          </div>
        `).join('') || '<p class="muted">No comments yet.</p>';
        document.querySelectorAll('[data-resolve]').forEach(node => {
          node.addEventListener('click', () => resolveComment(node.dataset.resolve));
        });
      } catch (err) {
        status(err.message);
      }
    }

    async function addComment() {
      if (!selectedOutputId) return status('Select an output first');
      const body = document.getElementById('commentBody').value.trim();
      if (!body) return status('Comment body is required');
      try {
        await api('/api/review-comment', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_type: 'output',
            target_id: selectedOutputId,
            author: reviewer(),
            body,
            annotation_type: document.getElementById('annotationType').value
          })
        });
        document.getElementById('commentBody').value = '';
        await loadComments();
        status('Comment added');
      } catch (err) {
        status(err.message);
      }
    }

    async function resolveComment(annotationId) {
      try {
        await api('/api/review-comment/resolve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ annotation_id: annotationId, resolver: reviewer() })
        });
        await loadComments();
        status('Comment resolved');
      } catch (err) {
        status(err.message);
      }
    }

    async function reviewRun(decision) {
      if (!currentRunId) return status('Select a run first');
      try {
        const result = await api('/api/review-run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            run_id: currentRunId,
            decision,
            reviewer: reviewer(),
            rationale: document.getElementById('rationale').value.trim()
          })
        });
        status(`Run ${result.status}`);
        await loadQueue();
        await loadDetail(currentRunId);
        await loadAudit();
      } catch (err) {
        status(err.message);
      }
    }

    async function loadAudit() {
      try {
        const query = new URLSearchParams({ reviewer: reviewer(), limit: '30' });
        const project = document.getElementById('project').value.trim();
        if (currentRunId) {
          query.set('run_id', currentRunId);
        } else if (project) {
          query.set('project_slug', project);
        } else {
          document.getElementById('auditSummary').innerHTML = '';
          document.getElementById('audit').innerHTML =
            '<p class="muted">Select a run or project to view audit events.</p>';
          return;
        }
        const action = document.getElementById('auditAction').value.trim();
        const targetType = document.getElementById('auditTarget').value.trim();
        if (action) query.set('action', action);
        if (targetType) query.set('target_type', targetType);
        const dashboard = await api('/api/audit-dashboard?' + query.toString());
        const summary = dashboard.summary || {};
        document.getElementById('auditSummary').innerHTML = `
          <div class="metric"><span class="muted">Events</span><strong>${esc(summary.total || 0)}</strong></div>
          <div class="metric"><span class="muted">Actions</span><strong>${esc(Object.keys(summary.by_action || {}).length)}</strong></div>
          <div class="metric"><span class="muted">Actors</span><strong>${esc(Object.keys(summary.by_actor || {}).length)}</strong></div>
          <div class="metric"><span class="muted">Targets</span><strong>${esc(Object.keys(summary.by_target_type || {}).length)}</strong></div>
        `;
        const rows = dashboard.events || [];
        document.getElementById('audit').innerHTML = rows.map(row => `
          <div class="audit-event">
            <div class="row">
              <span class="pill">${esc(row.action)}</span>
              <span class="muted">${esc(row.created_at || '-')} - ${esc(row.actor_email || '-')}</span>
            </div>
            <div class="muted">${esc(row.target_type)}:${esc(row.target_id)}</div>
          </div>
        `).join('') || '<p class="muted">No audit events yet.</p>';
      } catch (err) {
        status(err.message);
      }
    }
  </script>
</body>
</html>"""
