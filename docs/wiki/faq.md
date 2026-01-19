# Frequently Asked Questions

Common questions about HAL 9000.

## General

### What is HAL 9000?

HAL 9000 is an AI-powered research assistant that:
- Processes PDF research papers
- Extracts metadata and insights using Claude
- Classifies documents into a topic taxonomy
- Creates interconnected notes in Obsidian
- Generates research contexts for the ADAM Platform

### What does HAL 9000 stand for?

It's a reference to the AI in "2001: A Space Odyssey" - but this HAL is here to help with research, not open pod bay doors.

### What makes HAL 9000 different from other PDF tools?

HAL 9000 uses **Recursive Language Model (RLM)** patterns to intelligently process large documents:
- Documents are chunked and analyzed recursively
- Results are aggregated using frequency-based ranking
- Outputs are structured for downstream systems (Obsidian, ADAM)

---

## Installation

### What are the system requirements?

- Python 3.11 or higher
- ~100MB disk space for dependencies
- Internet connection (for Claude API)
- Anthropic API key

### Do I need a GPU?

No. HAL 9000 uses the Claude API for AI processing, which runs on Anthropic's servers.

### How do I get an Anthropic API key?

1. Visit [console.anthropic.com](https://console.anthropic.com/)
2. Create an account
3. Generate an API key
4. Add to your `.env` file

### Can I use a local LLM instead of Claude?

Currently, HAL 9000 is designed for Claude. Supporting local models would require modifying `rlm/processor.py` to use a different API.

---

## Usage

### How long does processing take?

Processing time depends on document length:
- Short paper (10 pages): ~30 seconds
- Long paper (50+ pages): ~2-3 minutes

The bottleneck is LLM API calls, not local processing.

### Can I process scanned PDFs?

Yes, with OCR support:

```bash
pip install -e ".[ocr]"
brew install tesseract  # macOS
```

Scanned PDFs will be OCR'd before processing.

### How many PDFs can I process at once?

Use the `--limit` flag to control batch size:

```bash
hal batch ~/Papers --limit 50
```

There's no hard limit, but consider:
- API costs increase with volume
- Very large batches may timeout
- Start with 10-20 to test

### Can I process non-English papers?

Claude supports multiple languages, so non-English papers should work. However:
- Keyword matching in the taxonomy is English-focused
- Some metadata extraction patterns assume English

---

## Configuration

### Where is configuration stored?

1. `config/default.yaml` - Default settings
2. `.env` - Environment variables (API keys)
3. CLI flags - Per-command overrides

### How do I change the database location?

```yaml
# In config/default.yaml
hal9000:
  database:
    url: sqlite:////path/to/my/database.db
```

Or via environment:
```bash
export HAL9000_DATABASE__URL=sqlite:////path/to/db.db
```

### How do I use PostgreSQL instead of SQLite?

```yaml
hal9000:
  database:
    url: postgresql://user:password@localhost/hal9000
```

---

## Obsidian

### Do I need Obsidian installed?

No. HAL 9000 creates markdown files that are Obsidian-compatible. You can:
- Open the folder as an Obsidian vault
- View files with any markdown editor
- Use the files without Obsidian

### How do wikilinks work?

HAL 9000 creates links using Obsidian's `[[wikilink]]` syntax:

```markdown
## Key Concepts
- [[Fe16N2]]
- [[iron nitride]]

## Topics
- [[magnetic-materials|Magnetic Materials]]
```

These become clickable links in Obsidian's Graph View.

### Can I use an existing Obsidian vault?

Yes! Use `--vault-path` to specify your vault:

```bash
hal init-vault --vault-path ~/MyExistingVault
```

HAL 9000 will create its folders (Papers, Concepts, Topics) inside your vault.

### The graph view looks messy. How do I clean it up?

In Obsidian:
1. Open Graph View
2. Use filters to show only certain folders
3. Adjust link forces in settings
4. Use local graph (on a specific note) for focused view

---

## ADAM Platform

### What is the ADAM Platform?

[ADAM](https://github.com/arc-pbc-co/adam-platform) (Autonomous Discovery of Advanced Materials) is a platform for AI-driven materials discovery and experimental design.

### How does HAL 9000 integrate with ADAM?

HAL 9000 generates research context files that ADAM can use:
- Literature summaries
- Experiment suggestions
- Knowledge graphs
- Materials of interest

Currently, this is via JSON export. Future versions may include direct API integration.

### Can I use HAL 9000 without ADAM?

Yes. HAL 9000 is useful standalone for:
- Organizing research papers
- Creating Obsidian knowledge bases
- Extracting insights from literature

The ADAM context is just one output format.

---

## Taxonomy

### What topics are supported?

The default taxonomy covers Materials Science:
- Magnetic Materials
- Energy Storage
- Catalysis
- Thin Films & Coatings
- Nanomaterials
- Characterization
- Computational Materials
- Synthesis & Processing

See [Materials Taxonomy Wiki](materials-taxonomy.md) for details.

### Can I use a different taxonomy?

Yes! Create a custom YAML file:

```yaml
# config/my_taxonomy.yaml
taxonomy:
  name: My Domain
  topics:
    - name: Topic 1
      slug: topic-1
      keywords: [keyword1, keyword2]
```

Then configure:
```yaml
hal9000:
  taxonomy:
    base_file: ./config/my_taxonomy.yaml
```

### What happens if a paper doesn't match any topic?

If `auto_extend: true` (default), HAL 9000 creates a new topic based on the document's keywords. Otherwise, the document is classified as "uncategorized."

---

## Troubleshooting

### "ANTHROPIC_API_KEY not set"

Create a `.env` file with your API key:

```bash
echo "ANTHROPIC_API_KEY=sk-ant-your-key" > .env
```

### "No PDF files found"

Check that:
1. The path exists: `ls ~/Documents/Research`
2. Files have `.pdf` extension
3. You have read permissions

### Processing fails with "rate limit"

The Anthropic API has rate limits. Solutions:
- Reduce `max_concurrent_calls` in config
- Add delays between documents
- Upgrade your API plan

### Database locked errors

SQLite doesn't handle concurrent access well. Solutions:
- Don't run multiple HAL 9000 instances
- Switch to PostgreSQL for multi-user
- Delete `hal9000.db` and restart

### Notes not appearing in Obsidian

1. Verify the vault path matches Obsidian's open vault
2. Check notes exist in the filesystem
3. Refresh Obsidian (Cmd/Ctrl + R)

---

## API & Development

### How do I use HAL 9000 as a library?

```python
from hal9000.ingest import PDFProcessor
from hal9000.rlm import RLMProcessor
from hal9000.config import get_settings

settings = get_settings()
processor = RLMProcessor()

# Process a document
content = PDFProcessor().extract_text(Path("paper.pdf"))
analysis = processor.process_document(content.full_text)

print(analysis.summary)
```

### How do I add a new CLI command?

Edit `cli.py`:

```python
@cli.command()
@click.argument("query")
def search(query: str):
    """Search processed documents."""
    # Implementation
```

### How do I contribute?

1. Fork the repository
2. Create a feature branch
3. Add tests
4. Submit a pull request

See [Development Guide](../guides/development.md) for details.

---

## Costs

### How much does it cost to use HAL 9000?

HAL 9000 itself is free. Costs come from:
- **Claude API**: ~$0.01-0.10 per document (varies by length)
- **Storage**: Minimal (SQLite, markdown files)

### How can I reduce API costs?

1. **Increase chunk size**: Fewer API calls per document
2. **Skip materials analysis**: `include_materials_analysis=False`
3. **Use caching**: Enable `cache_enabled: true`
4. **Process selectively**: Don't reprocess already-processed papers

### Is there a free tier?

Anthropic offers a limited free tier for the Claude API. Check [anthropic.com](https://www.anthropic.com/) for current pricing.

---

## Privacy & Security

### Is my data sent to external servers?

Yes, document text is sent to Anthropic's Claude API for analysis. If this is a concern:
- Don't process confidential documents
- Consider self-hosted LLM alternatives (requires code changes)

### Are my API keys secure?

Store keys in `.env` (not committed to git):
```bash
chmod 600 .env
```

Never commit `.env` or API keys to version control.

### Can I use HAL 9000 offline?

Not currently. The RLM processing requires the Claude API. Offline support would require integrating a local LLM.
