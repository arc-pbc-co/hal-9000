# Configuration API Reference

Module: `hal9000.config`

Configuration management using Pydantic settings with environment variable support.

## Classes

### Settings

Main configuration container for HAL 9000.

```python
from hal9000.config import Settings, get_settings

# Get global settings instance
settings = get_settings()

# Or create with custom values
settings = Settings(
    log_level="DEBUG",
    verbose=True
)
```

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `sources` | `SourcesConfig` | `SourcesConfig()` | Document source paths |
| `cloud` | `CloudConfig` | `CloudConfig()` | Cloud storage settings |
| `obsidian` | `ObsidianConfig` | `ObsidianConfig()` | Obsidian vault settings |
| `adam` | `ADAMConfig` | `ADAMConfig()` | ADAM Platform settings |
| `processing` | `ProcessingConfig` | `ProcessingConfig()` | Processing parameters |
| `taxonomy` | `TaxonomyConfig` | `TaxonomyConfig()` | Taxonomy settings |
| `database` | `DatabaseConfig` | `DatabaseConfig()` | Database connection |
| `anthropic_api_key` | `Optional[str]` | `None` | Anthropic API key |
| `log_level` | `str` | `"INFO"` | Logging level |
| `verbose` | `bool` | `False` | Verbose output |

#### Methods

##### get_vault_path

```python
def get_vault_path(self) -> Path
```

Get expanded Obsidian vault path.

**Returns**: `Path` - Expanded absolute path to vault

##### get_local_paths

```python
def get_local_paths(self) -> list[Path]
```

Get expanded local source paths.

**Returns**: `list[Path]` - List of expanded source paths

##### get_cache_path

```python
def get_cache_path(self) -> Path
```

Get expanded cache directory path.

**Returns**: `Path` - Expanded absolute cache path

---

### SourcesConfig

Configuration for document sources.

```python
from hal9000.config import SourcesConfig

sources = SourcesConfig(
    local_paths=["~/Documents/Research", "~/Papers"],
    watch_mode=True
)
```

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `local_paths` | `list[str]` | `["~/Documents/Research", "~/Downloads/Papers"]` | Paths to scan |
| `watch_mode` | `bool` | `False` | Enable continuous monitoring |

---

### CloudConfig

Cloud storage configuration.

```python
from hal9000.config import CloudConfig, GDriveConfig

cloud = CloudConfig(
    gdrive=GDriveConfig(
        enabled=True,
        credentials_path="./creds.json",
        folder_ids=["abc123"]
    )
)
```

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `gdrive` | `GDriveConfig` | `GDriveConfig()` | Google Drive settings |

---

### GDriveConfig

Google Drive configuration.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `bool` | `False` | Enable Google Drive |
| `credentials_path` | `Optional[str]` | `None` | OAuth credentials path |
| `folder_ids` | `list[str]` | `[]` | Folder IDs to scan |

---

### ObsidianConfig

Obsidian vault configuration.

```python
from hal9000.config import ObsidianConfig

obsidian = ObsidianConfig(
    vault_path="~/MyVault",
    create_canvas=True,
    auto_link=True
)
```

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `vault_path` | `str` | `"~/ObsidianVault/HAL9000Research"` | Vault location |
| `templates_path` | `str` | `"./templates/obsidian"` | Templates directory |
| `create_canvas` | `bool` | `True` | Generate Canvas files |
| `auto_link` | `bool` | `True` | Auto-create wikilinks |

---

### ADAMConfig

ADAM Platform configuration.

```python
from hal9000.config import ADAMConfig

adam = ADAMConfig(
    enabled=True,
    output_path="./contexts",
    default_domain="materials_science"
)
```

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `bool` | `True` | Enable ADAM generation |
| `output_path` | `str` | `"./adam_contexts"` | Output directory |
| `default_domain` | `str` | `"materials_science"` | Default domain |
| `api_url` | `Optional[str]` | `None` | ADAM API URL (future) |
| `api_key` | `Optional[str]` | `None` | ADAM API key (future) |

---

### ProcessingConfig

Document processing configuration.

```python
from hal9000.config import ProcessingConfig

processing = ProcessingConfig(
    chunk_size=75000,
    max_concurrent_calls=10
)
```

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `chunk_size` | `int` | `50000` | Characters per chunk |
| `max_concurrent_calls` | `int` | `5` | Max concurrent API calls |
| `cache_enabled` | `bool` | `True` | Enable result caching |
| `cache_path` | `str` | `"./.hal9000_cache"` | Cache directory |

---

### TaxonomyConfig

Taxonomy configuration.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `auto_extend` | `bool` | `True` | Auto-add new topics |
| `base_file` | `str` | `"./config/materials_science_taxonomy.yaml"` | Taxonomy file |

---

### DatabaseConfig

Database configuration.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `str` | `"sqlite:///./hal9000.db"` | SQLAlchemy URL |

---

## Functions

### get_settings

```python
def get_settings() -> Settings
```

Get the global settings instance (lazy loaded singleton).

**Returns**: `Settings` - Global settings instance

**Example**:
```python
from hal9000.config import get_settings

settings = get_settings()
print(settings.processing.chunk_size)  # 50000
```

---

### load_settings

```python
def load_settings(config_file: Optional[Path] = None) -> Settings
```

Load settings from environment and optional YAML config file.

**Parameters**:
- `config_file`: Optional path to YAML configuration file

**Returns**: `Settings` - Loaded settings instance

**Example**:
```python
from pathlib import Path
from hal9000.config import load_settings

# Load from custom config
settings = load_settings(Path("~/my-config.yaml"))

# Load from environment only
settings = load_settings()
```

---

## Environment Variables

All settings can be configured via environment variables:

| Variable | Setting |
|----------|---------|
| `ANTHROPIC_API_KEY` | API key |
| `HAL9000_LOG_LEVEL` | `log_level` |
| `HAL9000_VERBOSE` | `verbose` |
| `HAL9000_DATABASE__URL` | `database.url` |
| `HAL9000_OBSIDIAN__VAULT_PATH` | `obsidian.vault_path` |
| `HAL9000_PROCESSING__CHUNK_SIZE` | `processing.chunk_size` |

Use `__` for nested settings.
