# Getting Started

This guide covers a complete first-time setup with recommended defaults.

If you want the fastest path, use [Quick Start](quick-start.md).

## Prerequisites

- Python 3.9+
- Anthropic API key
- Optional: Obsidian installed for note browsing

## Installation

```bash
git clone https://github.com/arc-pbc-co/hal-9000.git
cd hal-9000
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Optional extras:

```bash
pip install -e ".[ocr]"      # OCR support for scanned PDFs
pip install -e ".[gdrive]"   # Google Drive integration
pip install -e ".[vector]"   # vector-db tooling
pip install -e ".[all]"      # all optional extras
```

## Configuration

Create `.env`:

```bash
cp .env.example .env
```

Set API key in `.env`:

```dotenv
ANTHROPIC_API_KEY=your-key-here
# or HAL9000_ANTHROPIC_API_KEY=your-key-here
```

Optional settings live in `config/default.yaml` and can be overridden with env vars or CLI:

```bash
hal --config ./config/default.yaml status
```

## Verify Setup

```bash
hal --help
hal status
```

You should see database and vault/output configuration values.

## Run Your First Workflow

### Option A: Start with local PDFs

```bash
hal scan ~/Documents/Research
hal process /absolute/path/to/paper.pdf
```

### Option B: Acquire papers first

```bash
hal acquire "solid state batteries" --dry-run
hal acquire "solid state batteries" --max-papers 5
```

### Option C: Batch processing + context generation

```bash
hal batch ~/Documents/Research --limit 10 --context-name "first_context"
```

## Initialize Obsidian Vault

```bash
hal init-vault
```

Default vault structure:

- `Papers/`
- `Concepts/`
- `Topics/`
- `Canvas/`
- `Templates/`

## Common Tasks

```bash
# check acquisition history
hal acquisitions --limit 20

# start WebSocket gateway
hal gateway start --host 127.0.0.1 --port 9000
```

## Troubleshooting

### API key not detected

- Confirm `.env` exists at repository root.
- Confirm variable name is `ANTHROPIC_API_KEY` or `HAL9000_ANTHROPIC_API_KEY`.

### No PDFs found

- Verify the target directory and file extension.
- Use an explicit path first (`hal scan /path/to/pdfs`).

### Custom config not applied

- Pass it before the command:
  - `hal --config ./config/default.yaml status`
