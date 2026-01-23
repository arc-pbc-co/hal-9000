# HAL 9000 Documentation

Welcome to the HAL 9000 documentation. HAL 9000 is an AI-powered research assistant that processes academic PDFs, organizes knowledge using topic taxonomies, integrates with Obsidian for mind mapping, and generates research contexts for the ADAM Platform.

## Quick Links

- [Getting Started](guides/getting-started.md) - Installation and first steps
- [CLI Reference](guides/cli-reference.md) - Command-line interface documentation
- [Configuration](guides/configuration.md) - Configuration options and customization
- [Architecture](guides/architecture.md) - System design and data flow

## Guides

| Guide | Description |
|-------|-------------|
| [Getting Started](guides/getting-started.md) | Install HAL 9000 and process your first PDF |
| [Configuration](guides/configuration.md) | Configure sources, processing, and integrations |
| [CLI Reference](guides/cli-reference.md) | Complete command-line reference |
| [Obsidian Integration](guides/obsidian-integration.md) | Set up and use Obsidian knowledge base |
| [ADAM Integration](guides/adam-integration.md) | Generate research contexts for ADAM Platform |
| [Taxonomy Guide](guides/taxonomy.md) | Understand and customize topic classification |
| [Development](guides/development.md) | Contributing and extending HAL 9000 |

## API Reference

| Module | Description |
|--------|-------------|
| [acquisition](api/acquisition.md) | Paper search, download, and validation |
| [config](api/config.md) | Configuration management |
| [ingest](api/ingest.md) | PDF scanning and processing |
| [rlm](api/rlm.md) | Recursive Language Model processing |
| [categorize](api/categorize.md) | Topic taxonomy and classification |
| [obsidian](api/obsidian.md) | Obsidian vault and note generation |
| [adam](api/adam.md) | ADAM context generation |
| [db](api/db.md) | Database models |

## Wiki

| Topic | Description |
|-------|-------------|
| [RLM Patterns](wiki/rlm-patterns.md) | Recursive Language Model implementation |
| [Materials Science Taxonomy](wiki/materials-taxonomy.md) | Complete taxonomy reference |
| [Knowledge Graph](wiki/knowledge-graph.md) | Graph structure and relationships |
| [Data Flow](wiki/data-flow.md) | End-to-end processing pipeline |
| [FAQ](wiki/faq.md) | Frequently asked questions |

## Overview

HAL 9000 implements patterns from the Recursive Language Models (RLM) paper to intelligently process large documents:

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

### Key Features

- **Paper Acquisition**: Search and download papers from Semantic Scholar, arXiv, and Unpaywall with Claude-powered query expansion
- **Intelligent PDF Processing**: Extract text, metadata, and structure from research papers
- **RLM Analysis**: Use Claude to analyze documents with recursive chunking and aggregation
- **Topic Classification**: Automatically categorize papers using a Materials Science taxonomy
- **Obsidian Integration**: Generate interconnected markdown notes with wikilinks
- **ADAM Context Export**: Create research contexts for autonomous experimental design

### Requirements

- Python 3.11+
- Anthropic API key (for Claude)
- ~100MB disk space for dependencies

## Support

- [GitHub Issues](https://github.com/yourusername/hal-9000/issues) - Report bugs and request features
- [Discussions](https://github.com/yourusername/hal-9000/discussions) - Ask questions and share ideas

---

*HAL 9000 v0.1.0 - Built with Claude Code*
