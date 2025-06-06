# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python application for translating large texts (books, documents) using local Large Language Models via the Ollama API. It supports both text (.txt) and EPUB files with dual interfaces: a modern web interface and command-line interface.

## Development Commands

### Environment Setup
```bash
# Create and activate conda environment
conda create -n translate_book_env python=3.9
conda activate translate_book_env

# Install web interface dependencies
pip install flask flask-cors flask-socketio python-socketio requests tqdm aiohttp

# Or minimal CLI-only dependencies  
pip install requests tqdm
```

### Running the Application
```bash
# Start web interface (runs on localhost:5000)
python translation_api.py

# CLI translation
python translate.py -i input.txt -o output.txt

# CLI with custom settings
python translate.py -i book.txt -o book_fr.txt -sl English -tl French -m mistral-small:24b -cs 25
```

### Docker Development
```bash
# Build container
docker build -t translate-book .

# Run container
docker run -p 5000:5000 translate-book
```

## Architecture Overview

### Modular Structure
The project has been refactored into a clean modular architecture:

```
src/
├── core/           # Core translation logic
│   ├── text_processor.py    # Text chunking and context management
│   ├── translator.py        # LLM communication and translation
│   └── epub_processor.py    # EPUB-specific processing
├── api/            # Flask web server
│   ├── routes.py           # REST API endpoints
│   ├── websocket.py        # WebSocket handlers
│   └── handlers.py         # Translation job management
├── web/            # Web interface
│   ├── static/            # CSS, JS, images
│   └── templates/         # HTML templates
├── utils/          # Utilities
│   └── file_utils.py      # File processing utilities
└── models/         # Data models (currently unused)
```

### Root Files
- **`translate.py`** - CLI interface (lightweight wrapper)
- **`translation_api.py`** - Web server entry point
- **`config.py`** - Centralized configuration
- **`prompts.py`** - Translation prompt generation

### Translation Pipeline
1. **Text Chunking**: Intelligently splits text while preserving sentence boundaries and context
2. **Context Management**: Maintains translation context between chunks for consistency
3. **LLM Communication**: Async requests to Ollama API with retry logic and timeout handling
4. **EPUB Processing**: XML namespace-aware processing that preserves document structure
5. **Error Handling**: Graceful degradation with original text preservation on failures

### Data Flow
- Text files: Read → Chunk → Translate → Reassemble → Save
- EPUB files: Extract → Parse XML → Translate content blocks → Rebuild → Repackage
- Web interface: Upload → Queue job → Stream progress via WebSocket → Download result

## Configuration

All settings are centralized in `config.py`:
- **API_ENDPOINT**: Ollama API endpoint (default: localhost:11434)
- **DEFAULT_MODEL**: LLM model (default: mistral-small:24b)
- **MAIN_LINES_PER_CHUNK**: Text segmentation size (default: 25 lines)
- **TRANSLATE_TAG_IN/OUT**: Response parsing tags
- **EPUB processing**: Namespace mappings and content block definitions

## Dependencies

### External Requirements
- **Ollama**: Must be running locally on port 11434 with models installed
- **Models**: Download via `ollama pull mistral-small:24b` (or other models)

### Python Packages
No requirements.txt exists - dependencies are documented in README and Dockerfile:
- Core: `requests`, `tqdm`, `lxml` (for EPUB), `asyncio`
- Web: `flask`, `flask-cors`, `flask-socketio`, `python-socketio`, `aiohttp`

## Key Implementation Details

### Text Processing
- Uses dictionary-based chunk structures: `{"context_before": "", "main_content": "", "context_after": ""}`
- Preserves sentence boundaries with configurable terminators
- Handles line-break hyphen removal and context windows

### EPUB Handling
- XML namespace-aware processing using lxml
- Selective translation of content blocks while preserving structure
- Maintains metadata and updates language tags

### Web Interface
- In-memory job tracking with unique translation IDs
- WebSocket events for real-time progress updates
- File upload/download with temporary file management
- Interruption support for long-running translations

### Error Recovery
- Configurable retry attempts with exponential backoff
- Timeout handling for LLM requests
- Preserves original content on translation failures
- Graceful degradation with partial results

## File Organization

### Module Structure
- **`src/core/`**: Core translation functionality (text processing, LLM communication, EPUB handling)
- **`src/api/`**: Web server components (routes, WebSocket, job handlers)
- **`src/web/`**: Frontend assets (templates, static files)
- **`src/utils/`**: Utility functions and file processing
- **Root level**: Entry points (`translate.py`, `translation_api.py`) and configuration

### Key Directories
- **`src/web/static/`**: CSS, JS, images
- **`src/web/templates/`**: HTML templates
- **`translated_files/`**: Output directory for results

### Migration
Use `python migrate_to_new_structure.py` to switch from old structure to new modular architecture

## Development Notes

- No formal build system - uses direct Python execution
- Main development branch: `dev`, PRs to `main`
- Recent refactoring removed model classes in favor of simple dictionaries
- No testing framework currently implemented
- Configuration is environment-variable free - all settings in config.py