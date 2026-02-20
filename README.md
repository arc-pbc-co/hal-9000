# HAL 9000

An AI-powered research assistant built on Claude Code that processes PDFs, organizes knowledge, and generates research contexts for the ADAM Platform.

## Features

- **PDF Ingestion**: Scan local directories and cloud storage for research papers
- **Paper Acquisition**: Search and download papers from Semantic Scholar, arXiv, and Unpaywall
  - Claude-powered query expansion for better search results
  - Intelligent relevance scoring and filtering
  - Concurrent downloads with rate limiting and automatic retry
  - Deduplication by file hash and title matching
- **RLM Processing**: Intelligent document analysis using Recursive Language Model patterns
- **Topic Classification**: Automatic categorization using a Materials Science taxonomy
- **Obsidian Integration**: Generate linked notes and mind maps
- **ADAM Context Generation**: Create research context libraries for experimental design
- **Real-time Monitoring**: Watch directories for new PDFs with automatic processing
- **WebSocket Gateway**: Real-time API server for client integrations
  - Session management with research context tracking
  - Message routing with custom handler support
  - Event streaming for real-time updates
  - Database persistence for session continuity

## Installation

```bash
# Clone the repository
git clone https://github.com/arc-pbc-co/hal-9000.git
cd hal-9000

# Install with pip
pip install -e .

# Or with optional dependencies
pip install -e ".[ocr,gdrive,vector]"

# All optional dependencies
pip install -e ".[all]"

# Development dependencies
pip install -e ".[dev]"
```

### Optional Dependencies

- `[ocr]` - OCR capability via pytesseract for scanned PDFs
- `[gdrive]` - Google Drive integration for cloud storage scanning
- `[vector]` - Vector database support via ChromaDB for semantic search
- `[dev]` - Development tools (pytest, ruff, mypy)
- `[all]` - All optional dependencies

## Configuration

**Step 1:** Copy the example environment file:

```bash
cp .env.example .env
```

**Step 2:** Add your API keys:

```bash
# Required
ANTHROPIC_API_KEY=your-api-key-here

# Optional - for higher Semantic Scholar rate limits
HAL9000_ACQUISITION__SEMANTIC_SCHOLAR_API_KEY=your-key

# Required for Unpaywall open access lookups
HAL9000_ACQUISITION__UNPAYWALL_EMAIL=your-email@example.com
```

**Step 3:** Optionally customize settings in `config/default.yaml`

### Environment Variables

All settings can be configured via environment variables with the `HAL9000_` prefix. Use double underscores for nested settings:

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `ANTHROPIC_API_KEY` | Claude API key (required) | - |
| `HAL9000_ACQUISITION__DOWNLOAD_DIR` | Directory for downloaded papers | `~/hal9000/papers` |
| `HAL9000_ACQUISITION__MAX_CONCURRENT_DOWNLOADS` | Max parallel downloads | `3` |
| `HAL9000_ACQUISITION__RATE_LIMIT_SECONDS` | Seconds between API requests | `1.0` |
| `HAL9000_ACQUISITION__RELEVANCE_THRESHOLD` | Minimum relevance score (0-1) | `0.5` |
| `HAL9000_PROCESSING__CHUNK_SIZE` | Characters per RLM chunk | `50000` |
| `HAL9000_OBSIDIAN__VAULT_PATH` | Path to Obsidian vault | `~/hal9000/vault` |
| `HAL9000_ADAM__OUTPUT_PATH` | ADAM context output directory | `~/hal9000/contexts` |
| `HAL9000_DATABASE__URL` | Database connection string | `sqlite:///~/.hal9000/hal9000.db` |
| `HAL9000_GATEWAY__HOST` | Gateway server host | `127.0.0.1` |
| `HAL9000_GATEWAY__PORT` | Gateway server port | `9000` |
| `HAL9000_GATEWAY__MAX_CONNECTIONS` | Max concurrent WebSocket connections | `100` |
| `HAL9000_GATEWAY__SESSION_TIMEOUT_MINUTES` | Session timeout in minutes | `60` |

## Quick Start

```bash
# Initialize an Obsidian vault
hal init-vault

# Scan directories for PDFs
hal scan ~/Documents/Research

# Acquire papers on a research topic
hal acquire "nickel superalloys creep resistance" --max-papers 20

# Process a single PDF
hal process paper.pdf

# Process multiple PDFs and generate ADAM context
hal batch ~/Downloads/Papers --limit 10 --context-name "my_research"

# Check status
hal status
```

## CLI Commands

### `hal acquire <TOPIC>`
Search and download papers on a research topic.

```bash
hal acquire "battery cathode materials" --max-papers 50
hal acquire "machine learning" --sources arxiv --dry-run
hal acquire "nickel superalloys" --threshold 0.7  # Higher relevance threshold
hal acquire "perovskites" --no-process  # Download only, skip processing
hal acquire "catalysis" --no-notes --output-dir ./papers  # Custom output
```

**Options:**

- `--max-papers`: Maximum papers to download (default: 10)
- `--sources`: Comma-separated list of sources (semantic_scholar, arxiv)
- `--threshold`: Minimum relevance score 0-1 (default: 0.5)
- `--dry-run`: Preview results without downloading
- `--no-process`: Skip RLM processing after download
- `--no-notes`: Skip Obsidian note generation
- `--output-dir`: Custom download directory

### `hal scan [PATHS]`
Scan directories for PDF files.

```bash
hal scan ~/Documents/Research ~/Downloads/Papers
hal scan --recursive  # Scan subdirectories (default)
hal scan --no-recursive  # Only scan top level
```

### `hal process <PDF_PATH>`
Process a single PDF document.

```bash
hal process paper.pdf
hal process paper.pdf --output results.json
hal process paper.pdf --no-obsidian  # Skip note creation
```

### `hal batch [PATHS]`
Process multiple PDFs and generate ADAM context.

```bash
hal batch ~/Papers --limit 20
hal batch --context-name "battery_research"
hal batch --output-dir ./contexts
```

### `hal init-vault`
Initialize a new Obsidian vault for research.

```bash
hal init-vault
hal init-vault --vault-path ~/MyVault
```

### `hal acquisitions`
List paper acquisition records from the database.

```bash
hal acquisitions
hal acquisitions --topic "battery" --limit 20
hal acquisitions --status completed
```

**Options:**

- `--topic`: Filter by acquisition topic
- `--status`: Filter by status (pending, completed, failed)
- `--limit`: Maximum records to show

### `hal gateway start`

Start the WebSocket gateway server for real-time client connections.

```bash
hal gateway start
hal gateway start --host 0.0.0.0 --port 8080
hal gateway start --verbose
```

**Options:**

- `--host, -h`: Host address to bind to (default: 127.0.0.1)
- `--port, -p`: Port number to listen on (default: 9000)
- `--verbose, -v`: Enable verbose logging

**WebSocket Protocol:**

Connect to `ws://<host>:<port>` and send JSON messages:

```json
{"type": "query", "session_id": "any", "payload": {"query_type": "health"}}
```

For full API documentation, see [docs/api/gateway.md](docs/api/gateway.md).

### `hal status`
Show HAL 9000 status and statistics.

### `hal version`
Show version information.

### Global Options

All commands support these options:

- `-v, --verbose`: Enable verbose output
- `--config`: Path to custom config file

## Architecture

HAL 9000 implements patterns from the Recursive Language Models (RLM) paper:

1. **Context as Environment**: Documents are treated as external environment variables, not direct prompt content
2. **Recursive Decomposition**: Large documents are chunked and processed with sub-LM calls
3. **Aggregation**: Results from chunks are intelligently merged

```
                        ┌──────────────────┐
                        │  Paper Acquire   │
                        │ (Search & Download)
                        └────────┬─────────┘
                                 ↓
PDF Input → Chunking → RLM Processing → Classification → Obsidian Notes
                                    ↓
                            ADAM Context Generation
```

## Project Structure

```
hal-9000/
├── src/hal9000/
│   ├── cli.py              # Command-line interface
│   ├── config.py           # Configuration management
│   ├── gateway/            # WebSocket gateway server
│   ├── acquisition/        # Paper search and download
│   ├── ingest/             # PDF processing and scanning
│   ├── rlm/                # RLM processing engine
│   ├── categorize/         # Topic classification
│   ├── obsidian/           # Obsidian integration
│   ├── adam/               # ADAM context generation
│   └── db/                 # Database models
├── config/
│   ├── default.yaml        # Default configuration
│   └── materials_science_taxonomy.yaml
├── templates/
│   └── obsidian/           # Note templates
├── docs/
│   ├── api/                # API reference documentation
│   ├── guides/             # User and architecture guides
│   ├── development/        # Development history
│   └── wiki/               # Knowledge base
└── tests/
```

## Materials Science Taxonomy

The default taxonomy includes:
- Magnetic Materials (rare-earth, rare-earth-free, soft magnets, spintronics)
- Energy Storage (solid-state batteries, Li-ion, supercapacitors)
- Catalysis (electrocatalysis, photocatalysis)
- Thin Films & Coatings
- Nanomaterials (nanoparticles, 2D materials)
- Characterization Methods
- Computational Materials
- Synthesis & Processing

Customize the taxonomy in `config/materials_science_taxonomy.yaml`.

## ADAM Platform Integration

HAL 9000 generates research contexts compatible with the [ADAM Platform](https://github.com/arc-pbc-co/adam-platform) for autonomous experimental design.

Output format:
```json
{
  "context_id": "uuid",
  "research_domain": "materials_science",
  "topic_focus": "rare-earth-free-magnets",
  "literature_summary": {
    "papers_analyzed": 50,
    "key_findings": [...],
    "gaps_identified": [...]
  },
  "experiment_suggestions": [...],
  "knowledge_graph": {
    "nodes": [...],
    "edges": [...]
  }
}
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with verbose output
hal -v scan ~/Papers
```

## License

MIT License

## Acknowledgments

- Built with [Claude Code](https://claude.ai/claude-code)
- Inspired by the Recursive Language Models paper
- Designed for integration with the ADAM Platform
