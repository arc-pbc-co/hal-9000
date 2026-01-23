# CLI Reference

HAL 9000 provides a command-line interface for all operations. This reference documents all commands and their options.

## Global Options

These options can be used with any command:

```bash
hal [OPTIONS] COMMAND [ARGS]
```

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Enable verbose output with debug logging |
| `--config PATH` | Path to a custom configuration file |
| `--help` | Show help message and exit |

## Commands

### `hal acquire`

Search for and download research papers on a topic.

```bash
hal acquire [OPTIONS] TOPIC
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `TOPIC` | Research topic to search for papers on (required) |

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `-n, --max-papers` | `20` | Maximum papers to acquire |
| `-s, --sources` | `semantic_scholar,arxiv` | Comma-separated list of sources |
| `--no-process` | - | Skip RLM processing after download |
| `--no-notes` | - | Skip Obsidian note generation |
| `-o, --output-dir PATH` | Config default | Override download directory |
| `--dry-run` | - | Search only, don't download |
| `-t, --threshold` | `0.5` | Minimum relevance score (0-1) |

**Examples:**

```bash
# Search and download papers on a topic
hal acquire "nickel superalloys creep resistance"

# Download more papers with higher relevance threshold
hal acquire "battery cathode materials" --max-papers 50 --threshold 0.7

# Search arXiv only (dry run to preview results)
hal acquire "machine learning" --sources arxiv --dry-run

# Download without processing
hal acquire "rare earth magnets" --no-process --no-notes

# Custom output directory
hal acquire "solid state batteries" -o ~/Research/SSB
```

**Dry Run Output:**

```
Dry run mode - searching but not downloading

Papers Found (15)
┏━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━┳━━━━━┳━━━━━━━┓
┃ # ┃ Title                                      ┃ Year ┃ Source       ┃ PDF ┃ Score ┃
┡━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━╇━━━━━╇━━━━━━━┩
│ 1 │ High-Temperature Creep of Ni Superalloys   │ 2024 │ semantic_sch │ Yes │ 0.92  │
│ 2 │ Microstructure Evolution in MAR-M 247...   │ 2023 │ arxiv        │ Yes │ 0.87  │
│ 3 │ Single Crystal Growth of Ni-Based...       │ 2024 │ semantic_sch │ Yes │ 0.85  │
└───┴────────────────────────────────────────────┴──────┴──────────────┴─────┴───────┘

Use without --dry-run to download these papers
```

**Full Acquisition Output:**

```
Acquiring papers on: nickel superalloys creep resistance

⠋ Searching for papers...
  Found 23 relevant papers
⠋ Resolving PDF URLs...
  Resolved 5 additional URLs via Unpaywall
⠋ Downloading [1/20]: High-Temperature_Creep_of_Ni...
⠋ Downloading [2/20]: Microstructure_Evolution_in...
...
⠋ Processing [1/15]: High-Temperature_Creep_of_Ni...
...

Acquisition complete!

┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric               ┃ Value ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Papers Found         │ 23    │
│ Papers Downloaded    │ 15    │
│ Papers Processed     │ 15    │
│ Duplicates Skipped   │ 3     │
│ Download Failures    │ 2     │
└──────────────────────┴───────┘

Session log saved to: ~/Documents/Research/Acquired/nickel-superalloys/session_log.json
```

**Data Sources:**

- **Semantic Scholar**: Comprehensive academic database with citation data
- **arXiv**: Preprint server for physics, math, CS, and more
- **Unpaywall**: Resolves DOIs to open access PDF URLs

---

### `hal scan`

Scan directories for PDF files without processing them.

```bash
hal scan [OPTIONS] [PATHS]...
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `PATHS` | One or more directories to scan. Uses config defaults if not specified. |

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--recursive / --no-recursive` | `--recursive` | Scan subdirectories |

**Examples:**

```bash
# Scan configured paths
hal scan

# Scan specific directories
hal scan ~/Documents/Research ~/Downloads/Papers

# Scan without recursion
hal scan --no-recursive ~/Papers

# Verbose output
hal -v scan ~/Papers
```

**Output:**

```
Scanning 2 path(s)...
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Metric             ┃ Value    ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ Total PDFs Found   │ 47       │
│ Total Size         │ 156.3 MB │
│ Paths Configured   │ 2        │
│ Valid Paths        │ 2        │
└────────────────────┴──────────┘
```

---

### `hal process`

Process a single PDF document through the full pipeline.

```bash
hal process [OPTIONS] PDF_PATH
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `PDF_PATH` | Path to the PDF file to process (required) |

**Options:**

| Option | Description |
|--------|-------------|
| `-o, --output PATH` | Save results to a JSON file |
| `--no-obsidian` | Skip Obsidian note creation |

**Examples:**

```bash
# Basic processing
hal process paper.pdf

# Save results to JSON
hal process paper.pdf --output results.json

# Process without creating Obsidian note
hal process paper.pdf --no-obsidian

# Verbose processing
hal -v process paper.pdf
```

**Processing Steps:**

1. **Initialize database** - Create/connect to SQLite database
2. **Extract PDF content** - Parse text, tables, and metadata
3. **Extract metadata** - Identify title, authors, DOI, abstract
4. **RLM analysis** - Analyze with Claude using chunking
5. **Classification** - Assign to taxonomy topics
6. **Store in database** - Save document record
7. **Create Obsidian note** - Generate linked markdown note

**Output:**

```
⠋ Initializing database...
⠋ Extracting PDF content...
  Extracted 12 pages, 45230 chars
⠋ Extracting metadata...
  Title: Novel Synthesis of Fe16N2 Magnets
  Authors: Smith, J., Johnson, M., Lee, K.
⠋ Analyzing document with RLM...
  Topics: rare-earth-free-magnets, iron nitride, synthesis
⠋ Classifying document...
  Categories: magnetic-materials/rare-earth-free-magnets
⠋ Creating Obsidian note...
  Note created: Novel_Synthesis_of_Fe16N2_Magnets.md

Processing complete!
```

**JSON Output Structure:**

```json
{
  "document_id": 1,
  "title": "Novel Synthesis of Fe16N2 Magnets",
  "metadata": {
    "title": "Novel Synthesis of Fe16N2 Magnets",
    "authors": ["Smith, J.", "Johnson, M.", "Lee, K."],
    "year": 2024,
    "doi": "10.1000/example.123",
    "abstract": "..."
  },
  "analysis": {
    "title": "Novel Synthesis of Fe16N2 Magnets",
    "summary": "This paper presents...",
    "primary_topics": ["rare-earth-free-magnets", "iron nitride"],
    "keywords": ["Fe16N2", "permanent magnet", "plasma arc"],
    "key_findings": ["...", "..."],
    "materials": [{"name": "Fe16N2", "properties": [...]}]
  },
  "classification": {
    "topics": ["magnetic-materials", "rare-earth-free-magnets"],
    "folder_path": "magnetic-materials/rare-earth-free-magnets"
  }
}
```

---

### `hal batch`

Process multiple PDFs and generate an ADAM research context.

```bash
hal batch [OPTIONS] [PATHS]...
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `PATHS` | Directories containing PDFs. Uses config defaults if not specified. |

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `-n, --limit` | `10` | Maximum number of PDFs to process |
| `-c, --context-name` | `research_context` | Name for the ADAM context |
| `-o, --output-dir PATH` | Config default | Directory for output files |

**Examples:**

```bash
# Process up to 10 PDFs (default)
hal batch ~/Papers

# Process more documents
hal batch ~/Papers --limit 50

# Name the context
hal batch ~/Papers --context-name "battery_research"

# Custom output directory
hal batch ~/Papers --output-dir ./my-contexts

# Multiple source directories
hal batch ~/Papers ~/Downloads/Research --limit 25
```

**Output:**

```
Processing PDFs from 1 path(s)...
Found 47 PDFs (processing up to 20)
⠋ Processing [1/20]: Novel_Synthesis_of_Fe16N2...
⠋ Processing [2/20]: Rare_Earth_Free_Permanent_Magnets...
⠋ Processing [3/20]: Solid_State_Battery_Review...
...
Successfully processed 20 documents

Generating ADAM research context...
ADAM context saved to: ./adam_contexts/adam_context_a1b2c3d4.json

┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Metric                   ┃ Value   ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ Context ID               │ a1b2c3d4│
│ Papers Analyzed          │ 20      │
│ Key Findings             │ 45      │
│ Experiment Suggestions   │ 5       │
│ Materials Identified     │ 23      │
│ Knowledge Graph Nodes    │ 87      │
└──────────────────────────┴─────────┘
```

---

### `hal init-vault`

Initialize a new Obsidian vault for research.

```bash
hal init-vault [OPTIONS]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--vault-path PATH` | Override the vault path from config |

**Examples:**

```bash
# Use configured vault path
hal init-vault

# Specify custom path
hal init-vault --vault-path ~/MyResearchVault
```

**Created Structure:**

```
HAL9000Research/
├── Papers/              # Paper notes go here
├── Concepts/            # Concept/keyword notes
├── Topics/              # Topic hierarchy notes
├── Canvas/              # Visual mind maps
├── Templates/           # Note templates
│   └── Paper Note.md
├── .obsidian/           # Obsidian configuration
│   ├── app.json
│   └── graph.json
└── Index.md             # Vault index note
```

**Output:**

```
Initializing Obsidian vault at: ~/ObsidianVault/HAL9000Research
Vault initialized successfully!
  Papers folder: Papers
  Concepts folder: Concepts
  Topics folder: Topics
```

---

### `hal status`

Show HAL 9000 status and statistics.

```bash
hal status
```

**Output:**

```
HAL 9000 Status

┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Setting         ┃ Value                                    ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Database        │ sqlite:///./hal9000.db                   │
│ Obsidian Vault  │ ~/ObsidianVault/HAL9000Research          │
│ ADAM Output     │ ./adam_contexts                          │
│ Log Level       │ INFO                                     │
└─────────────────┴──────────────────────────────────────────┘

┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric            ┃ Value ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Total Documents   │ 47    │
└───────────────────┴───────┘

┏━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric     ┃ Value ┃
┡━━━━━━━━━━━━╇━━━━━━━┩
│ Papers     │ 47    │
│ Concepts   │ 234   │
│ Topics     │ 12    │
└────────────┴───────┘
```

---

### `hal version`

Display the HAL 9000 version.

```bash
hal version
```

**Output:**

```
HAL 9000 v0.1.0
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error |
| `2` | Invalid arguments |

## Environment Variables

The CLI respects these environment variables:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `HAL9000_*` | Any HAL 9000 configuration setting |

See [Configuration Guide](configuration.md) for all environment variables.

## Verbose Mode

Enable verbose mode for detailed logging:

```bash
hal -v process paper.pdf
```

Verbose mode shows:
- Debug-level log messages
- API call details
- Processing timing
- Detailed error tracebacks

## Shell Completion

Generate shell completion scripts:

```bash
# Bash
_HAL_COMPLETE=bash_source hal > ~/.hal-complete.bash
echo '. ~/.hal-complete.bash' >> ~/.bashrc

# Zsh
_HAL_COMPLETE=zsh_source hal > ~/.hal-complete.zsh
echo '. ~/.hal-complete.zsh' >> ~/.zshrc

# Fish
_HAL_COMPLETE=fish_source hal > ~/.config/fish/completions/hal.fish
```

After reloading your shell, tab completion will work:

```bash
hal pro<TAB>  # Completes to "hal process"
hal process --<TAB>  # Shows available options
```
