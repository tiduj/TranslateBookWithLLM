<p align="center">
    <img src="https://github.com/hydropix/TranslateBookWithLLM/blob/main/static/TBL-Logo.png?raw=true" alt="Logo de l'application">
</p>

_Translating books with local LLMs powered by Ollama. TBL is a Python application designed for large-scale text translation, such as entire books, leveraging local LLMs via the Ollama API. The tool offers both a **modern web interface** for ease of use and a command-line interface for advanced users._

## Features

- 🌐 **Web Interface**: User-friendly browser-based interface with real-time progress tracking
- 💻 **CLI Support**: Command-line interface for automation and scripting

## Windows Installation Guide

This comprehensive guide walks you through setting up the complete environment on Windows.

### 1. Prerequisites: Software Installation

1. **Miniconda (Python Environment Manager)**
   - **Purpose:** Creates isolated Python environments to manage dependencies
   - **Download:** Get the latest Windows 64-bit installer from the [Miniconda documentation page](https://docs.conda.io/en/latest/miniconda.html)
   - **Installation:** Run installer, choose "Install for me only", use default settings

2. **Ollama (Local LLM Runner)**
   - **Purpose:** Runs large language models locally
   - **Download:** Get the Windows installer from [Ollama website](https://ollama.com/)
   - **Installation:** Run installer and follow instructions

3. **Git (Version Control)**
   - **Purpose:** Download and update the script from GitHub
   - **Download:** Get from [https://git-scm.com/download/win](https://git-scm.com/download/win)
   - **Installation:** Use default settings

### 2. Setting up the Python Environment

1. **Open Anaconda Prompt** (search in Start Menu)

2. **Create and Activate Environment:**
   ```bash
   # Create environment
   conda create -n translate_book_env python=3.9
   
   # Activate environment (do this every time)
   conda activate translate_book_env
   ```

### 3. Getting the Translation Application

```bash
# Navigate to your projects folder
cd C:\Projects
mkdir TranslateBookWithLLM
cd TranslateBookWithLLM

# Clone the repository
git clone https://github.com/hydropix/TranslateBookWithLLM.git .
```

### 4. Installing Dependencies

```bash
# Ensure environment is active
conda activate translate_book_env

# Install web interface dependencies (recommended)
pip install flask flask-cors flask-socketio python-socketio requests tqdm aiohttp

# Or install minimal dependencies for CLI only
pip install requests tqdm
```

### 5. Preparing Ollama

1. **Download an LLM Model:**
   ```bash
   # Download the default model (recommended for French translation)
   ollama pull mistral-small:24b
   
   # Or try other models
   ollama pull qwen2:7b
   ollama pull llama3:8b
   
   # List available models
   ollama list
   ```

2. **Start Ollama Service:**
   - Ollama usually runs automatically after installation
   - Look for Ollama icon in system tray
   - If not running, launch from Start Menu

### 6. Using the Application

## Option A: Web Interface (Recommended)

1. **Start the Server:**
   ```bash
   conda activate translate_book_env
   cd C:\Projects\TranslateBookWithLLM
   python translation_api.py
   ```

2. **Open Browser:** Navigate to http://localhost:5000

3. **Configure and Translate:**
   - Select source and target languages
   - Choose your LLM model
   - Upload your .txt file
   - Adjust advanced settings if needed
   - Start translation and monitor progress
   - Download the result

## Option B: Command Line Interface

Basic usage:
```bash
python translate.py -i input.txt -o output.txt
```

**Command Arguments:**
- `-i, --input`: (Required) Input text file path
- `-o, --output`: (Required) Output file path  
- `-sl, --source_lang`: Source language (default: "English")
- `-tl, --target_lang`: Target language (default: "French")
- `-m, --model`: LLM model (default: "mistral-small:24b")
- `-cs, --chunksize`: Lines per chunk (default: 25)

**Examples:**
```bash
# Basic English to French translation
python translate.py -i book.txt -o book_fr.txt

# English to German with different model
python translate.py -i story.txt -o story_de.txt -sl English -tl German -m qwen2:7b

# Custom chunk size for better context
python translate.py -i novel.txt -o novel_fr.txt -cs 40
```

---

## Advanced Configuration

### Web Interface Settings

The web interface provides easy access to:
- **Chunk Size**: Lines per translation chunk (10-100)
- **Timeout**: Request timeout in seconds (30-600)
- **Context Window**: Model context size (1024-32768)
- **Max Attempts**: Retry attempts for failed chunks (1-5)

### Script Configuration (translate.py)

Key settings you can modify in `translate.py`:

```python
# API and Model Configuration
API_ENDPOINT = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "mistral-small:24b"

# Processing Parameters
MAIN_LINES_PER_CHUNK = 25          # Default chunk size
REQUEST_TIMEOUT = 180              # API timeout (increase if needed)
OLLAMA_NUM_CTX = 4096             # Context window size
MAX_TRANSLATION_ATTEMPTS = 2       # Retry attempts
RETRY_DELAY_SECONDS = 2           # Wait between retries
```

### Custom Translation Prompts

The translation quality depends heavily on the prompt. You can modify the prompt in the `generate_translation_request` function:

```python
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
+ Surround your translation with <translate> and </translate> tags.
+ Return only the translation, nothing else.
"""
```

**Important:** If you change the `<translate>` tags, you must update the regex pattern that extracts the translation.

---

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
- **For Books**: Use 25-40 lines per chunk for best balance

### Content Preparation
- Clean your input text (remove artifacts, fix major typos)
- Use plain text (.txt) format
- Consider splitting very large files (>1MB) into sections

---

## Troubleshooting

### Common Issues

**Web Interface Won't Start:**
```bash
# Check if port 5000 is in use
netstat -an | find "5000"

# Try different port
python translation_api.py  # Check the code for port configuration
```

**Ollama Connection Issues:**
- Ensure Ollama is running (check system tray)
- Verify no firewall blocking `localhost:11434`
- Test with: `curl http://localhost:11434/api/tags`

**Translation Timeouts:**
- Increase `REQUEST_TIMEOUT` in `translate.py`
- Use smaller chunk sizes
- Try a faster model

**Poor Translation Quality:**
- Experiment with different models
- Adjust chunk size for better context
- Modify the translation prompt
- Clean input text beforehand

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

---

## Architecture

The application consists of:

- **`translate.py`**: Core translation engine with CLI interface
- **`translation_api.py`**: Flask web server with WebSocket support
- **`translation_interface.html`**: Modern web interface with real-time updates

The web interface communicates with the backend via REST API and WebSocket for real-time progress updates, while the CLI version can be used independently for automation and scripting.
