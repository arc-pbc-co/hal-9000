# Getting Started with HAL 9000

This guide walks you through installing HAL 9000 and processing your first research paper.

## Prerequisites

- Python 3.11 or higher
- An Anthropic API key ([get one here](https://console.anthropic.com/))
- PDF research papers to process

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/yourusername/hal-9000.git
cd hal-9000

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install HAL 9000
pip install -e .
```

### With Optional Dependencies

```bash
# Include OCR support for scanned PDFs
pip install -e ".[ocr]"

# Include Google Drive integration
pip install -e ".[gdrive]"

# Include vector search capabilities
pip install -e ".[vector]"

# Install all optional dependencies
pip install -e ".[ocr,gdrive,vector]"
```

## Configuration

### 1. Set Up Your API Key

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and add your Anthropic API key:

```
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

### 2. Configure Settings (Optional)

HAL 9000 works with sensible defaults, but you can customize settings in `config/default.yaml`:

```yaml
hal9000:
  sources:
    local_paths:
      - ~/Documents/Research
      - ~/Downloads/Papers

  obsidian:
    vault_path: ~/ObsidianVault/HAL9000Research

  processing:
    chunk_size: 50000  # Characters per chunk
```

See the [Configuration Guide](configuration.md) for all options.

## Quick Start

### 1. Initialize the Obsidian Vault

```bash
hal init-vault
```

This creates the vault structure at the configured path:
```
HAL9000Research/
├── Papers/          # Paper notes
├── Concepts/        # Concept notes
├── Topics/          # Topic hierarchy notes
├── Canvas/          # Visual mind maps
├── Templates/       # Note templates
└── .obsidian/       # Vault configuration
```

### 2. Scan for PDFs

See what PDFs HAL 9000 can find:

```bash
hal scan ~/Documents/Research
```

Output:
```
Scanning 1 path(s)...
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Metric             ┃ Value    ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ Total PDFs Found   │ 47       │
│ Total Size         │ 156.3 MB │
│ Paths Configured   │ 1        │
│ Valid Paths        │ 1        │
└────────────────────┴──────────┘
```

### 3. Process a Single PDF

Process your first paper:

```bash
hal process ~/Documents/Research/paper.pdf
```

HAL 9000 will:
1. Extract text and metadata from the PDF
2. Analyze the document using Claude (RLM processing)
3. Classify it into the Materials Science taxonomy
4. Store results in the database
5. Create an Obsidian note with wikilinks

Output:
```
⠋ Extracting PDF content...
  Extracted 12 pages, 45,230 chars
⠋ Extracting metadata...
  Title: Novel Fe16N2 Synthesis via Plasma Arc
  Authors: Smith, J., Johnson, M.
⠋ Analyzing document with RLM...
  Topics: rare-earth-free-magnets, iron nitride, magnetic materials
⠋ Classifying document...
  Categories: magnetic-materials/rare-earth-free-magnets
⠋ Creating Obsidian note...
  Note created: Novel_Fe16N2_Synthesis_via_Plasma_Arc.md

Processing complete!
```

### 4. Save Analysis Results

Save the analysis to a JSON file:

```bash
hal process paper.pdf --output results.json
```

The JSON includes:
- Document metadata (title, authors, DOI)
- RLM analysis (topics, keywords, findings)
- Classification results
- Materials information

### 5. Batch Process Multiple PDFs

Process all PDFs in a directory and generate an ADAM context:

```bash
hal batch ~/Documents/Research --limit 20 --context-name "magnets_research"
```

This:
1. Scans for PDFs (up to the limit)
2. Processes each document
3. Aggregates findings across all papers
4. Builds a knowledge graph
5. Generates experiment suggestions
6. Saves an ADAM-compatible context file

Output:
```
Processing PDFs from 1 path(s)...
Found 47 PDFs (processing up to 20)
⠋ Processing [1/20]: Novel_Fe16N2_Synthesis...
⠋ Processing [2/20]: Rare_Earth_Free_Magnets...
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

### 6. Check Status

View the current state of HAL 9000:

```bash
hal status
```

Output:
```
HAL 9000 Status

┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Setting         ┃ Value                                   ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Database        │ sqlite:///./hal9000.db                  │
│ Obsidian Vault  │ ~/ObsidianVault/HAL9000Research         │
│ ADAM Output     │ ./adam_contexts                         │
│ Log Level       │ INFO                                    │
└─────────────────┴─────────────────────────────────────────┘

┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric            ┃ Value ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Total Documents   │ 20    │
└───────────────────┴───────┘

┏━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric     ┃ Value ┃
┡━━━━━━━━━━━━╇━━━━━━━┩
│ Papers     │ 20    │
│ Concepts   │ 156   │
│ Topics     │ 8     │
└────────────┴───────┘
```

## Next Steps

- [Configure cloud storage](configuration.md#cloud-storage) for Google Drive integration
- [Customize the taxonomy](taxonomy.md) for your research domain
- [Explore the Obsidian vault](obsidian-integration.md) and create mind maps
- [Generate ADAM contexts](adam-integration.md) for experimental design

## Troubleshooting

### "ANTHROPIC_API_KEY not set"

Ensure your `.env` file exists and contains a valid API key:

```bash
cat .env
# Should show: ANTHROPIC_API_KEY=sk-ant-...
```

### "No PDF files found"

Check that the paths exist and contain PDFs:

```bash
ls ~/Documents/Research/*.pdf
```

### PDF extraction errors

Some PDFs may be scanned images. Install OCR support:

```bash
pip install -e ".[ocr]"
brew install tesseract  # macOS
# or: apt-get install tesseract-ocr  # Ubuntu
```

### Database errors

Reset the database:

```bash
rm hal9000.db
hal process paper.pdf  # Will recreate the database
```

## Getting Help

```bash
# Show all commands
hal --help

# Show help for a specific command
hal process --help
hal batch --help
```
