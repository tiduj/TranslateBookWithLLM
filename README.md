<p align="center">
    <img src="https://github.com/hydropix/TranslateBookWithLLM/blob/main/src/web/static/TBL-Logo.png?raw=true" alt="Logo de l'application">
</p>

*TBL is a Python application designed for large-scale text translation, such as entire books (.EPUB), subtitle file (.SRT) and plain text, leveraging local LLMs via the Ollama API. The tool offers both a **modern web interface** for ease of use and a command-line interface for advanced users.*

## Features

- 📚 **Multiple Format Support**: Translate both plain text (.txt) EPUB and SRT (Subtitle) files while preserving formatting
- 🌐 **Web Interface**: User-friendly browser-based interface with real-time progress tracking via WebSocket
- 💻 **CLI Support**: Command-line interface for automation and scripting
- 🎯 **Context Management**: Intelligent text chunking that preserves sentence boundaries and maintains context
- 🔒 **Secure File Handling**: Built-in security features for file uploads and processing
- 🤖 **Multiple LLM Providers**: Support for both local Ollama models and Google Gemini API

## Windows Installation Guide

This comprehensive guide walks you through setting up the complete environment on Windows.

### 1\. Prerequisites: Software Installation

1.  **Miniconda (Python Environment Manager)**

      - **Purpose:** Creates isolated Python environments to manage dependencies
      - **Download:** Get the latest Windows 64-bit installer from the [Miniconda install page](https://www.anaconda.com/docs/getting-started/miniconda/install#windows-installation)
      - **Installation:** Run installer, choose "Install for me only", use default settings

2.  **Ollama (Local LLM Runner)**

      - **Purpose:** Runs large language models locally
      - **Download:** Get the Windows installer from [Ollama website](https://ollama.com/)
      - **Installation:** Run installer and follow instructions

3.  **Git (Version Control)**

      - **Purpose:** Download and update the script from GitHub
      - **Download:** Get from [https://git-scm.com/download/win](https://git-scm.com/download/win)
      - **Installation:** Use default settings

-----

### 2\. Setting up the Python Environment

1.  **Open Anaconda Prompt** (search in Start Menu)

2.  **Create and Activate Environment:**

    ```bash
    # Create environment
    conda create -n translate_book_env python=3.9

    # Activate environment (do this every time)
    conda activate translate_book_env
    ```

-----

### 3\. Getting the Translation Application

```bash
# Navigate to your projects folder
cd C:\Projects
mkdir TranslateBookWithLLM
cd TranslateBookWithLLM

# Clone the repository
git clone https://github.com/hydropix/TranslateBookWithLLM.git .
```

-----

### 4\. Installing Dependencies

```bash
# Ensure environment is active
conda activate translate_book_env

# Install web interface dependencies (recommended)
pip install flask flask-cors flask-socketio python-socketio requests tqdm httpx lxml python-dotenv

# Or install minimal dependencies for CLI only
pip install requests tqdm python-dotenv

# For EPUB support, also install:
pip install lxml
```

-----

### 5\. Preparing Ollama

1.  **Download an LLM Model:**

    ```bash
    # Download the default model (recommended for French translation)
    ollama pull mistral-small:24b

    # Or try other models
    ollama pull qwen2:7b
    ollama pull llama3:8b

    # List available models
    ollama list
    ```

2.  **Start Ollama Service:**

      - Ollama usually runs automatically after installation
      - Look for Ollama icon in system tray
      - If not running, launch from Start Menu

-----

### 6\. Using the Application

## Option A: Web Interface (Recommended)

1.  **Start the Server:**

    ```bash
    conda activate translate_book_env
    cd C:\Projects\TranslateBookWithLLM
    python translation_api.py
    ```

2.  **Open Browser:** Navigate to `http://localhost:5000`

3. **Configure and Translate:**
   - Select source and target languages
   - Choose your LLM model
   - Upload your .txt or .epub file
   - Adjust advanced settings if needed
   - Start translation and monitor real-time progress
   - Download the translated result

## Option B: Command Line Interface

Basic usage:

```bash
python translate.py -i input.txt -o output.txt
```

**Command Arguments**

  - `-i, --input`: (Required) Path to the input file (.txt or .epub).
  - `-o, --output`: Output file path. If not specified, a default name will be generated.
  - `-sl, --source_lang`: Source language (default: "English").
  - `-tl, --target_lang`: Target language (default: "French").
  - `-m, --model`: LLM model to use (default: "mistral-small:24b").
  - `-cs, --chunksize`: Target lines per chunk for text files (default: 25).
  - `--api_endpoint`: Ollama API endpoint (default: "http://localhost:11434/api/generate").
  - `--provider`: LLM provider to use ("ollama" or "gemini", default: "ollama").
  - `--gemini_api_key`: Google Gemini API key (required when using gemini provider).

**Examples:**

```bash
# Basic English to French translation (text file)
python translate.py -i book.txt -o book_fr.txt

# Translate EPUB file
python translate.py -i book.epub -o book_fr.epub

# English to German with different model
python translate.py -i story.txt -o story_de.txt -sl English -tl German -m qwen2:7b

# Custom chunk size for better context with a text file
python translate.py -i novel.txt -o novel_fr.txt -cs 40

# Using Google Gemini instead of Ollama
python translate.py -i book.txt -o book_fr.txt --provider gemini --gemini_api_key YOUR_API_KEY -m gemini-2.0-flash
```

### EPUB File Support

The application fully supports EPUB files:
- **Preserves Structure**: Maintains the original EPUB structure and formatting
- **XML Processing**: Namespace-aware XML parsing for proper content handling
- **Selective Translation**: Only translates content blocks (paragraphs, headings, etc.)
- **Metadata Update**: Automatically updates language metadata in the EPUB
- **Error Recovery**: Falls back to original content if translation fails

### Google Gemini Support

In addition to local Ollama models, the application now supports Google Gemini API:

**Setup:**
1. Get your API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Use the `--provider gemini` flag with your API key

**Available Gemini Models:**
- `gemini-2.0-flash` (default, fast and efficient)
- `gemini-1.5-pro` (more capable, slower)
- `gemini-1.5-flash` (balanced performance)

**Web Interface:**
- Select "Google Gemini" from the LLM Provider dropdown
- Enter your API key in the secure field
- Choose your preferred Gemini model

**CLI Example:**
```bash
python translate.py -i book.txt -o book_translated.txt \
    --provider gemini \
    --gemini_api_key YOUR_API_KEY \
    -m gemini-2.0-flash \
    -sl English -tl Spanish
```

**Note:** Gemini API requires an internet connection and has usage quotas. Check [Google's pricing](https://ai.google.dev/pricing) for details.

---

## Advanced Configuration

### Web Interface Settings

The web interface provides easy access to:

  - **Chunk Size**: Lines per translation chunk (10-100)
  - **Timeout**: Request timeout in seconds (30-600)
  - **Context Window**: Model context size (1024-32768)
  - **Max Attempts**: Retry attempts for failed chunks (1-5)

### Configuration Files

Configuration is centralized in `src/config.py` with support for environment variables:

#### Environment Variables (.env file)

Create a `.env` file in the project root to override default settings:

```bash
# Copy the example file
cp .env.example .env

# Edit with your settings
API_ENDPOINT=http://localhost:11434/api/generate
DEFAULT_MODEL=mistral-small:24b
MAIN_LINES_PER_CHUNK=25
# ... see .env.example for all available settings
```

#### src/config.py - Main Settings
```python
# Configuration loads from environment variables (via .env file)
# with fallback to defaults:

# API and Model Configuration
API_ENDPOINT = os.getenv('API_ENDPOINT', 'http://localhost:11434/api/generate')
DEFAULT_MODEL = os.getenv('DEFAULT_MODEL', 'mistral-small:24b')

# Processing Parameters
MAIN_LINES_PER_CHUNK = int(os.getenv('MAIN_LINES_PER_CHUNK', '25'))
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '60'))
OLLAMA_NUM_CTX = int(os.getenv('OLLAMA_NUM_CTX', '2048'))
MAX_TRANSLATION_ATTEMPTS = int(os.getenv('MAX_TRANSLATION_ATTEMPTS', '2'))
RETRY_DELAY_SECONDS = int(os.getenv('RETRY_DELAY_SECONDS', '2'))

# Translation Tags (hardcoded)
TRANSLATE_TAG_IN = "<TRANSLATED>"
TRANSLATE_TAG_OUT = "</TRANSLATED>"

# EPUB Processing (hardcoded)
NAMESPACES = {...}                # XML namespace mappings
CONTENT_BLOCK_TAGS_EPUB = [...]   # Tags to translate
```

#### prompts.py - Translation Prompts

The translation quality depends heavily on the prompt. The prompts are now managed in `prompts.py`:

```python
# The prompt template uses the actual tags from config.py
structured_prompt = f"""
## [ROLE] 
# You are a {target_language} professional translator.

## [TRANSLATION INSTRUCTIONS] 
+ Translate in the author's style.
+ Precisely preserve the deeper meaning of the text.
+ Adapt expressions and culture to the {target_language} language.
+ Vary your vocabulary with synonyms, avoid repetition.
+ Maintain the original layout, remove typos and line-break hyphens.

## [FORMATTING INSTRUCTIONS] 
+ Translate ONLY the main content between the specified tags.
+ Surround your translation with {TRANSLATE_TAG_IN} and {TRANSLATE_TAG_OUT} tags.
+ Return only the translation, nothing else.
"""
```

**Note:** The translation tags are defined in `config.py` and automatically used by the prompt generator.

-----

## Tips for Better Translations

### Model Selection

  - **mistral-small:24b**: Excellent for French, good general performance
  - **qwen2:7b**: Fast, good for multiple languages
  - **llama3:8b**: Balanced performance and speed

### Optimal Settings

  - **Chunk Size**:
      - Small (10-20): Faster but may lose context
      - Large (40-60): Better context but slower, may hit limits
  - **Context Window**: Match your model's capabilities
  - **EPUB Files**:
      - The script preserves the structure of the EPUB file. The original quality of the structure is important, because if line breaks are present in the middle of a sentence, it will be cut off in the translation chunk, causing translation errors. If the quality is too poor, it is better to convert the EPUB file to .txt using Calibre, and then translate it into a .txt file.
      - The chunk size applies to lines within HTML content blocks, chunk are mostly shorter than in .txt files.

### Content Preparation
- Clean your input text (remove artifacts, fix major typos)
- Use plain text (.txt) or EPUB (.epub) format
- Consider splitting very large text files (>1MB) into sections
- EPUB files are processed automatically without size limitations
-----

## Troubleshooting

### Common Issues

**Web Interface Won't Start:**

```bash
# Check if port 5000 is in use
netstat -an | find "5000"

# Try different port
# Default port is 5000, configured in translation_api.py
```

**Ollama Connection Issues:**

  - Ensure Ollama is running (check system tray).
  - Verify no firewall blocking `localhost:11434`.
  - Test with: `curl http://localhost:11434/api/tags`.

**Translation Timeouts:**

- Increase `REQUEST_TIMEOUT` in `config.py` (default: 60 seconds)
- Use smaller chunk sizes
- Try a faster model
- For web interface, adjust timeout in advanced settings

**Poor Translation Quality:**

  - Experiment with different models.
  - Adjust chunk size for better context.
  - Modify the translation prompt.
  - Clean input text beforehand.

**Model Not Found:**

```bash
# List installed models
ollama list

# Install missing model
ollama pull your-model-name
```

### Getting Help

1. Check the browser console for web interface issues
2. Monitor the terminal output for detailed error messages  
3. Test with small text samples first
4. Verify all dependencies are installed correctly
5. For EPUB issues, check XML parsing errors in the console
6. Review `config.py` for adjustable timeout and retry settings
-----

## Architecture

The application follows a clean modular architecture:

### Project Structure
```
src/
├── core/                    # Core translation logic
│   ├── text_processor.py    # Text chunking and context management
│   ├── translator.py        # LLM communication and translation
│   └── epub_processor.py    # EPUB-specific processing
├── api/                     # Flask web server
│   ├── routes.py           # REST API endpoints
│   ├── websocket.py        # WebSocket handlers for real-time updates
│   └── handlers.py         # Translation job management
├── web/                     # Web interface
│   ├── static/             # CSS, JavaScript, images
│   └── templates/          # HTML templates
└── utils/                   # Utilities
    ├── file_utils.py       # File processing utilities
    └── security.py         # Security features for file handling
```

### Root Level Files
- **`translate.py`**: CLI interface (lightweight wrapper around core modules)
- **`translation_api.py`**: Web server entry point
- **`prompts.py`**: Translation prompt generation and management
- **`.env.example`**: Example environment variables file

### Configuration Files
- **`src/config.py`**: Centralized configuration with environment variable support

### Translation Pipeline
1. **Text Processing**: Intelligent chunking preserving sentence boundaries
2. **Context Management**: Maintains translation context between chunks
3. **LLM Communication**: Async requests with retry logic and timeout handling
4. **EPUB Processing**: XML namespace-aware processing preserving structure
5. **Error Recovery**: Graceful degradation with original text preservation

The web interface communicates via REST API and WebSocket for real-time progress, while the CLI version provides direct access for automation.

### Key Features Implementation

#### Asynchronous Processing
- Uses `httpx` for concurrent API requests
- Implements retry logic with exponential backoff
- Configurable timeout handling for long translations

#### Job Management System
- Unique translation IDs for tracking multiple jobs
- In-memory job storage with status updates
- WebSocket events for real-time progress streaming
- Support for translation interruption

#### Security Features
- File type validation for uploads
- Size limits for uploaded files
- Secure temporary file handling
- Sanitized file paths and names

#### Context-Aware Translation
- Preserves sentence boundaries across chunks
- Maintains translation context for consistency
- Handles line-break hyphens