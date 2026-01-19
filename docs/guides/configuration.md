# Configuration Guide

HAL 9000 uses a layered configuration system with sensible defaults. This guide covers all configuration options and how to customize them.

## Configuration Hierarchy

Configuration values are loaded in this order (later sources override earlier ones):

1. **Built-in defaults** - Hardcoded in `config.py`
2. **YAML config file** - `config/default.yaml` or custom path
3. **Environment variables** - `.env` file or system environment
4. **CLI flags** - Command-line options

## Environment Variables

### API Keys

```bash
# Required: Anthropic API key for Claude
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here

# Alternative prefix (both work)
HAL9000_ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

### HAL9000 Settings

All settings can be set via environment variables using the `HAL9000_` prefix and `__` for nesting:

```bash
# Database
HAL9000_DATABASE__URL=sqlite:///./my_database.db

# Obsidian
HAL9000_OBSIDIAN__VAULT_PATH=~/MyVault/Research
HAL9000_OBSIDIAN__CREATE_CANVAS=true
HAL9000_OBSIDIAN__AUTO_LINK=true

# Processing
HAL9000_PROCESSING__CHUNK_SIZE=50000
HAL9000_PROCESSING__MAX_CONCURRENT_CALLS=5
HAL9000_PROCESSING__CACHE_ENABLED=true

# ADAM
HAL9000_ADAM__ENABLED=true
HAL9000_ADAM__OUTPUT_PATH=./adam_contexts
HAL9000_ADAM__DEFAULT_DOMAIN=materials_science

# Logging
HAL9000_LOG_LEVEL=DEBUG
HAL9000_VERBOSE=true
```

## YAML Configuration

### Default Configuration File

The default configuration is in `config/default.yaml`:

```yaml
hal9000:
  # Document Sources
  sources:
    local_paths:
      - ~/Documents/Research
      - ~/Downloads/Papers
    watch_mode: false

  # Cloud Storage
  cloud:
    gdrive:
      enabled: false
      credentials_path: null
      folder_ids: []

  # Obsidian Integration
  obsidian:
    vault_path: ~/ObsidianVault/HAL9000Research
    templates_path: ./templates/obsidian
    create_canvas: true
    auto_link: true

  # ADAM Platform
  adam:
    enabled: true
    output_path: ./adam_contexts
    default_domain: materials_science
    api_url: null
    api_key: null

  # Processing Settings
  processing:
    chunk_size: 50000
    max_concurrent_calls: 5
    cache_enabled: true
    cache_path: ./.hal9000_cache

  # Taxonomy
  taxonomy:
    auto_extend: true
    base_file: ./config/materials_science_taxonomy.yaml

  # Database
  database:
    url: sqlite:///./hal9000.db

  # Logging
  log_level: INFO
  verbose: false
```

### Using a Custom Config File

```bash
hal --config ~/my-config.yaml scan
```

## Configuration Sections

### Sources Configuration

Control where HAL 9000 looks for PDFs.

```yaml
sources:
  local_paths:
    - ~/Documents/Research
    - ~/Downloads/Papers
    - /shared/lab-papers
  watch_mode: false  # Enable continuous monitoring
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `local_paths` | list[str] | `["~/Documents/Research", "~/Downloads/Papers"]` | Directories to scan for PDFs |
| `watch_mode` | bool | `false` | Enable continuous filesystem monitoring |

### Cloud Storage

Configure cloud storage integrations.

```yaml
cloud:
  gdrive:
    enabled: true
    credentials_path: ./credentials.json
    folder_ids:
      - "1abc123def456"
      - "2xyz789ghi012"
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `gdrive.enabled` | bool | `false` | Enable Google Drive integration |
| `gdrive.credentials_path` | str | `null` | Path to OAuth credentials JSON |
| `gdrive.folder_ids` | list[str] | `[]` | Google Drive folder IDs to scan |

### Obsidian Integration

Configure the Obsidian vault.

```yaml
obsidian:
  vault_path: ~/ObsidianVault/HAL9000Research
  templates_path: ./templates/obsidian
  create_canvas: true
  auto_link: true
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `vault_path` | str | `~/ObsidianVault/HAL9000Research` | Path to Obsidian vault |
| `templates_path` | str | `./templates/obsidian` | Path to note templates |
| `create_canvas` | bool | `true` | Generate Obsidian Canvas files |
| `auto_link` | bool | `true` | Auto-create wikilinks between notes |

### ADAM Platform

Configure ADAM context generation.

```yaml
adam:
  enabled: true
  output_path: ./adam_contexts
  default_domain: materials_science
  api_url: null  # Future: ADAM Platform API URL
  api_key: null  # Future: ADAM Platform API key
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable ADAM context generation |
| `output_path` | str | `./adam_contexts` | Directory for context JSON files |
| `default_domain` | str | `materials_science` | Default research domain |
| `api_url` | str | `null` | ADAM Platform API URL (future) |
| `api_key` | str | `null` | ADAM Platform API key (future) |

### Processing Settings

Control how documents are processed.

```yaml
processing:
  chunk_size: 50000
  max_concurrent_calls: 5
  cache_enabled: true
  cache_path: ./.hal9000_cache
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `chunk_size` | int | `50000` | Characters per chunk for RLM processing |
| `max_concurrent_calls` | int | `5` | Max concurrent LLM API calls |
| `cache_enabled` | bool | `true` | Cache processing results |
| `cache_path` | str | `./.hal9000_cache` | Cache directory |

**Chunk Size Guidelines:**
- Smaller chunks (25000): More detailed analysis, higher API costs
- Default (50000): Good balance of detail and cost
- Larger chunks (100000): Faster processing, may miss details

### Taxonomy Settings

Configure topic classification.

```yaml
taxonomy:
  auto_extend: true
  base_file: ./config/materials_science_taxonomy.yaml
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `auto_extend` | bool | `true` | Automatically add new topics |
| `base_file` | str | `./config/materials_science_taxonomy.yaml` | Taxonomy definition file |

### Database Configuration

Configure the database connection.

```yaml
database:
  url: sqlite:///./hal9000.db
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `url` | str | `sqlite:///./hal9000.db` | SQLAlchemy database URL |

**Database URL Examples:**
```yaml
# SQLite (default, local file)
url: sqlite:///./hal9000.db

# SQLite (absolute path)
url: sqlite:////Users/username/data/hal9000.db

# PostgreSQL
url: postgresql://user:password@localhost/hal9000

# PostgreSQL with SSL
url: postgresql://user:password@host.com:5432/hal9000?sslmode=require
```

### Logging

Configure log output.

```yaml
log_level: INFO
verbose: false
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `log_level` | str | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `verbose` | bool | `false` | Enable verbose console output |

## Example Configurations

### Minimal Configuration

```yaml
hal9000:
  sources:
    local_paths:
      - ~/Papers
  obsidian:
    vault_path: ~/MyVault
```

### Research Lab Configuration

```yaml
hal9000:
  sources:
    local_paths:
      - /shared/research/papers
      - ~/Downloads/Papers
    watch_mode: true

  cloud:
    gdrive:
      enabled: true
      credentials_path: /etc/hal9000/gdrive-credentials.json
      folder_ids:
        - "lab-papers-folder-id"

  obsidian:
    vault_path: /shared/research/knowledge-base
    create_canvas: true
    auto_link: true

  adam:
    enabled: true
    output_path: /shared/research/adam-contexts
    default_domain: materials_science

  processing:
    chunk_size: 75000
    max_concurrent_calls: 10
    cache_enabled: true
    cache_path: /var/cache/hal9000

  database:
    url: postgresql://hal9000:password@db.lab.local/hal9000

  log_level: INFO
```

### Development Configuration

```yaml
hal9000:
  sources:
    local_paths:
      - ./test-papers

  obsidian:
    vault_path: ./test-vault

  processing:
    chunk_size: 25000  # Smaller for testing
    max_concurrent_calls: 2
    cache_enabled: false  # Disable for testing

  database:
    url: sqlite:///./test.db

  log_level: DEBUG
  verbose: true
```

## Programmatic Access

Access configuration in Python code:

```python
from hal9000.config import get_settings, load_settings
from pathlib import Path

# Get global settings instance
settings = get_settings()

# Access nested values
vault_path = settings.get_vault_path()  # Returns expanded Path
local_paths = settings.get_local_paths()  # Returns list of Paths
cache_path = settings.get_cache_path()  # Returns expanded Path

# Access raw values
chunk_size = settings.processing.chunk_size
api_key = settings.anthropic_api_key

# Load from specific config file
custom_settings = load_settings(Path("~/my-config.yaml"))
```

## Security Considerations

1. **Never commit API keys** - Use `.env` files or environment variables
2. **Protect credentials** - Set appropriate file permissions on credential files
3. **Use read-only mounts** - When sharing configurations, mount config files read-only

```bash
# Secure your .env file
chmod 600 .env

# Secure Google Drive credentials
chmod 600 credentials.json
```
