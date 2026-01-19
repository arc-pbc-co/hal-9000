# HAL 9000

An AI-powered research assistant built on Claude Code that processes PDFs, organizes knowledge, and generates research contexts for the ADAM Platform.

## Features

- **PDF Ingestion**: Scan local directories and cloud storage for research papers
- **RLM Processing**: Intelligent document analysis using Recursive Language Model patterns
- **Topic Classification**: Automatic categorization using a Materials Science taxonomy
- **Obsidian Integration**: Generate linked notes and mind maps
- **ADAM Context Generation**: Create research context libraries for experimental design

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/hal-9000.git
cd hal-9000

# Install with pip
pip install -e .

# Or with optional dependencies
pip install -e ".[ocr,gdrive,vector]"
```

## Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Add your Anthropic API key:
```
ANTHROPIC_API_KEY=your-api-key-here
```

3. Optionally customize settings in `config/default.yaml`

## Quick Start

```bash
# Initialize an Obsidian vault
hal init-vault

# Scan directories for PDFs
hal scan ~/Documents/Research

# Process a single PDF
hal process paper.pdf

# Process multiple PDFs and generate ADAM context
hal batch ~/Downloads/Papers --limit 10 --context-name "my_research"

# Check status
hal status
```

## CLI Commands

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

### `hal status`
Show HAL 9000 status and statistics.

### `hal version`
Show version information.

## Architecture

HAL 9000 implements patterns from the Recursive Language Models (RLM) paper:

1. **Context as Environment**: Documents are treated as external environment variables, not direct prompt content
2. **Recursive Decomposition**: Large documents are chunked and processed with sub-LM calls
3. **Aggregation**: Results from chunks are intelligently merged

```
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
