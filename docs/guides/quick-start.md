# Quick Start (10 Minutes)

This guide is for new users who want HAL 9000 running quickly with minimal setup.

## 1. Install

```bash
git clone https://github.com/arc-pbc-co/hal-9000.git
cd hal-9000
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 2. Configure API Key

```bash
cp .env.example .env
```

Edit `.env` and set one of these:

```dotenv
ANTHROPIC_API_KEY=your-key-here
# or
HAL9000_ANTHROPIC_API_KEY=your-key-here
```

## 3. Confirm CLI Works

```bash
hal --help
hal status
```

## 4. First Document Run

If you already have papers:

```bash
hal scan ~/Documents/Research
hal process /absolute/path/to/paper.pdf
```

If you do not have papers yet:

```bash
hal acquire "nickel superalloys creep resistance" --dry-run
hal acquire "nickel superalloys creep resistance" --max-papers 5
```

## 5. Initialize Obsidian Vault (Optional but Recommended)

```bash
hal init-vault
```

HAL 9000 will create:

- `Papers/`
- `Concepts/`
- `Topics/`
- `Canvas/`
- `Templates/`

## 6. Batch Processing Example

```bash
hal batch ~/Documents/Research --limit 10 --context-name "first_context"
```

This generates an ADAM context JSON file in `./adam_contexts` by default.

## 7. Common Next Commands

```bash
# custom config file
hal --config ./config/default.yaml status

# list acquisition history
hal acquisitions --limit 20

# run gateway server
hal gateway start --port 9000
```

## Quick Troubleshooting

- `Missing API key`:
  - Ensure `.env` exists and includes `ANTHROPIC_API_KEY` or `HAL9000_ANTHROPIC_API_KEY`.
- `No PDFs found`:
  - Verify path and file extension: `ls /your/path/*.pdf`.
- `Dependency issues`:
  - Recreate env and reinstall: `pip install -e ".[dev]"`.
