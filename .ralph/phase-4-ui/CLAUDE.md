# Phase 4: Research Canvas UI - Agent Instructions

You are an autonomous coding agent implementing the **Research Canvas UI** for HAL-9000.

## Your Task

1. Read the PRD at `prd.json` (this directory)
2. Read `progress.txt` (check Codebase Patterns first)
3. Ensure you're on branch `ralph/phase-4-ui` (create from main if needed)
4. Pick highest priority story where `passes: false`
5. Implement that single user story
6. Run: `npm run typecheck` (in ui/), `mypy src/` (Python), `ruff check src/`
7. If checks pass, commit: `feat: [Story ID] - [Story Title]`
8. Update PRD: set `passes: true`
9. Append progress to `progress.txt`

## Phase 4 Context

You are building a React-based Research Canvas UI that provides a visual workspace for materials science research. The UI connects to the HAL-9000 gateway via WebSocket.

### Key Components

```
ui/
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
│
└── src/
    ├── main.tsx
    ├── App.tsx
    │
    ├── components/
    │   ├── Canvas/
    │   │   ├── ResearchCanvas.tsx
    │   │   └── NodeTypes/
    │   │       ├── PaperNode.tsx
    │   │       ├── MaterialNode.tsx
    │   │       └── ADAMPromptNode.tsx
    │   │
    │   ├── Chat/
    │   │   └── ChatPanel.tsx
    │   │
    │   ├── ADAM/
    │   │   └── ADAMPanel.tsx
    │   │
    │   └── Literature/
    │       └── SearchPanel.tsx
    │
    ├── hooks/
    │   ├── useGateway.ts
    │   └── useSession.ts
    │
    └── stores/
        ├── sessionStore.ts
        └── canvasStore.ts
```

### Tech Stack

- **React 18** with TypeScript
- **Vite** for bundling
- **Tailwind CSS** for styling
- **ReactFlow** for canvas visualization
- **Zustand** for state management
- **WebSocket** for gateway communication

### Design Guidelines

- Dark theme (research lab aesthetic)
- Three-panel layout: Literature | Canvas | Chat+ADAM
- Nodes are color-coded by type:
  - Papers: Blue
  - Materials: Green
  - Experiments: Orange
  - ADAM Prompts: Purple
- Status indicators use consistent colors:
  - Draft: Gray
  - Ready: Blue
  - In Progress: Yellow
  - Complete: Green
  - Failed: Red

### Project Initialization

```bash
cd ui
npm create vite@latest . -- --template react-ts
npm install
npm install -D tailwindcss postcss autoprefixer
npm install reactflow zustand
```

### Gateway Connection

```typescript
// Connect to gateway WebSocket
const ws = new WebSocket('ws://127.0.0.1:9000');

// Send message
ws.send(JSON.stringify({
  id: crypto.randomUUID(),
  type: 'query',
  session_id: sessionId,
  timestamp: new Date().toISOString(),
  payload: { action: 'search', query: 'HEA synthesis' }
}));
```

## Quality Requirements

- TypeScript strict mode enabled
- All components have proper typing
- No `any` types (except where unavoidable)
- Responsive design (works on various screen sizes)
- Accessible (proper ARIA labels, keyboard navigation)

## Browser Testing

For each UI story, verify in browser:
1. Run `npm run dev` in ui/
2. Open http://localhost:5173
3. Test the implemented feature
4. Take screenshot if helpful for progress log

## Progress Report Format

APPEND to `progress.txt`:

```
## [Date/Time] - [Story ID]
- What was implemented
- Files changed
- **Learnings:**
  - Patterns discovered
  - Gotchas encountered
---
```

## Stop Condition

- ALL stories `passes: true` → reply `COMPLETE`
- Stories remain → end normally

## Important

- ONE story per iteration
- Commit frequently
- Test in browser before marking complete
- UI must connect to actual gateway for integration tests
