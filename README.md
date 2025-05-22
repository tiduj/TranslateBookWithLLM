# Translating Books With LLMs

A Python script designed for large-scale text translation, such as entire books, leveraging a local LLM via the Ollama API.

## Windows Installation Guide

This guide walks you through setting up the necessary tools, configuring your environment, and executing the Python translation script on Windows.

---

**Table of Contents:**

1.  **[Prerequisites: Software Installation](#1-prerequisites-software-installation)**
    * Miniconda (Python Environment Manager)
    * Ollama (Local LLM Runner)
    * Git (Version Control - Recommended)
    * Code Editor (e.g., VS Code - Optional)
2.  **[Setting up the Python Environment](#2-setting-up-the-python-environment)**
    * Create and Activate Conda Environment (`translate_book_env`)
3.  **[Getting the Translation Script (translate.py)](#3-getting-the-translation-script-translatepy)**
    * Cloning from GitHub (Recommended)
    * Manual Download
4.  **[Installing Python Dependencies](#4-installing-python-dependencies)**
5.  **[Preparing and Running Ollama](#5-preparing-and-running-ollama)**
    * Pulling an LLM Model
    * Ensuring Ollama Service is Running
6.  **[Running the Translation Script](#6-running-the-translation-script)**
    * Prepare Your Input File
    * Script Arguments
    * Execution Command & Examples
7.  **[Advanced Configuration & Customization](#7-advanced-configuration--customization)**
    * Key Script Configurations (Inside `translate.py`)
    * Modifying the LLM Prompt
    * Output Parsing
8.  **[Tips for Better Translations](#8-tips-for-better-translations)**
9.  **[Troubleshooting](#9-troubleshooting)**

---

### 1. Prerequisites: Software Installation

Before you begin, install the following software:

1.  **Miniconda (Python Environment Manager)**
    * **Purpose:** Creates isolated Python environments to manage project dependencies and avoid conflicts.
    * **Download:** Get the latest Windows 64-bit installer (Python 3.x version) from the [Miniconda documentation page](https://docs.conda.io/en/latest/miniconda.html).
    * **Installation:**
        * Run the installer. Choose "Install for me only."
        * It's generally recommended **NOT** to add Miniconda to your PATH environment variable if the installer advises against it. Use the "Anaconda Prompt" (or "Miniconda Prompt") installed with Miniconda to access `conda` commands.
        * Accept default settings for other options unless you have specific reasons.

2.  **Ollama (Local LLM Runner)**
    * **Purpose:** Allows you to run large language models (LLMs) locally.
    * **Download:** Get the Windows installer from the [Ollama website](https://ollama.com/).
    * **Installation:** Run the installer and follow the on-screen instructions. Ollama will typically set itself up to run in the background.

3.  **Git (Version Control - Recommended)**
    * **Purpose:** Essential for downloading the script from its GitHub repository (`TranslateBookWithLLM`) and keeping it updated.
    * **Download:** Get the Windows installer from [https://git-scm.com/download/win](https://git-scm.com/download/win).
    * **Installation:** Run the installer. Default settings are generally fine.

4.  **Code Editor (e.g., VS Code - Optional)**
    * **Purpose:** Helpful for viewing, editing, and understanding the Python script (`translate.py`).
    * **Recommendation:** Visual Studio Code (VS Code) is a popular, free choice.
    * **Download:** Get it from [https://code.visualstudio.com/](https://code.visualstudio.com/).

### 2. Setting up the Python Environment

1.  **Open Anaconda Prompt:**
    * Search for "Anaconda Prompt" (or "Miniconda Prompt") in your Windows Start Menu and open it.

2.  **Create and Activate Conda Environment:**
    * We'll name the environment `translate_book_env`.
    * In the Anaconda Prompt, create the environment (e.g., with Python 3.9):
        ```bash
        conda create -n translate_book_env python=3.9
        ```
        (You can use Python 3.10, 3.11, etc., if preferred.)
    * When prompted, type `y` and press Enter to proceed.
    * Activate the environment:
        ```bash
        conda activate translate_book_env
        ```
    * Your prompt should now start with `(translate_book_env)`.
    * **Note:** Always activate this environment in any new Anaconda Prompt session before using the script.

### 3. Getting the Translation Script (`translate.py`)

Choose one of the following methods:

1.  **Cloning from GitHub (Recommended):**
    * In Anaconda Prompt (with `translate_book_env` active), navigate to where you want to store the project (e.g., `C:\Projects`):
        ```bash
        mkdir C:\Projects
        cd C:\Projects
        ```
    * Clone the repository:
        ```bash
        git clone [https://github.com/hydropix/TranslateBookWithLLM.git](https://github.com/hydropix/TranslateBookWithLLM.git)
        ```
    * Navigate into the cloned directory:
        ```bash
        cd TranslateBookWithLLM
        ```
    * This method allows easy updates via `git pull`.

2.  **Manual Download (Alternative):**
    * If you have the `translate.py` code directly:
    * Create a project folder (e.g., `C:\Projects\TranslateBookWithLLM`).
    * Save the Python script code as `translate.py` inside this folder.

This guide will assume the script is in `C:\Projects\TranslateBookWithLLM`.

### 4. Installing Python Dependencies

1.  Ensure your `translate_book_env` conda environment is active and you are in the script's directory (e.g., `C:\Projects\TranslateBookWithLLM`) in Anaconda Prompt.
2.  Install the required packages (`requests` and `tqdm`):
    ```bash
    pip install requests tqdm
    ```

### 5. Preparing and Running Ollama

1.  **Pulling an LLM Model:**
    * The script defaults to a specific model (e.g., `mistral-small:24b` as defined by `DEFAULT_MODEL` in `translate.py`). Download it (or any other model you intend to use) via Ollama.
    * Open a new regular Command Prompt, PowerShell, or use the Anaconda Prompt.
    * Run:
        ```bash
        ollama pull mistral-small:24b
        ```
        (Replace `mistral-small:24b` if you want to use a different model, e.g., `ollama pull qwen2:7b`).
    * This may take time. You can list your downloaded models with `ollama list`.

2.  **Ensuring Ollama Service is Running:**
    * Ollama usually runs as a background service. Look for its icon in your system tray.
    * If not running, launch the Ollama application from your Start Menu.
    * The script connects to Ollama at `http://localhost:11434`. Ensure no firewall blocks this.

### 6. Running the Translation Script

1.  **Prepare Your Input File:**
    * Create a plain text file (e.g., `input.txt`) with the text to translate. For simplicity, you can place it in your project directory (e.g., `C:\Projects\TranslateBookWithLLM\input.txt`).

2.  **Open Anaconda Prompt, activate the environment, and navigate to the script directory** (if not already done):
    ```bash
    conda activate translate_book_env
    cd C:\Projects\TranslateBookWithLLM
    ```

3.  **Script Arguments:**
    * `-i` or `--input`: (Required) Path to the input text file.
    * `-o` or `--output`: (Required) Path to save the translated output file.
    * `-sl` or `--source_lang`: Source language (default: "English").
    * `-tl` or `--target_lang`: Target language (default: "French").
    * `-m` or `--model`: LLM model to use (default set in script, e.g., `mistral-small:24b`). Must be pulled via Ollama.
    * `-cs` or `--chunksize`: Target number of lines per translation chunk (default: `25`).

4.  **Execution Command & Examples:**
    * **Basic command structure:**
        ```bash
        python translate.py -i <your_input_file> -o <your_output_file> [options]
        ```
    * **Example 1: Translate `input.txt` (in current directory) to French:**
        ```bash
        python translate.py -i input.txt -o output_fr.txt
        ```
    * **Example 2: Translate a file with full paths, to German, using a different model:**
        ```bash
        python translate.py -i C:\Path\To\Your\my_story_en.txt -o C:\Path\To\Your\my_story_de.txt -sl English -tl German -m qwen2:7b
        ```
        *(Ensure `qwen2:7b` is pulled: `ollama pull qwen2:7b`)*
    * **Example 3: Translate `input.txt` with a smaller chunk size:**
        ```bash
        python translate.py -i input.txt -o output_fr.txt -cs 10
        ```
    The script will display a progress bar as it processes chunks.

### 7. Advanced Configuration & Customization

Modify `translate.py` directly for deeper customization.

1.  **Key Script Configurations (Inside `translate.py`):**
    * `API_ENDPOINT = "http://localhost:11434/api/generate"`: Ollama API endpoint.
    * `DEFAULT_MODEL = "mistral-small:24b"`: Default model if not specified via CLI.
    * `MAIN_LINES_PER_CHUNK = 25`: Default chunk size if not specified via CLI.
    * `REQUEST_TIMEOUT = 60`: Timeout in seconds for API requests. **Increase this (e.g., to `120` or `300`) if your model is slow or chunks are large, causing timeouts.**
    * `OLLAMA_NUM_CTX = 4096`: Context window size for Ollama (model-dependent).
    * `MAX_TRANSLATION_ATTEMPTS = 3`: Retries for a failing chunk.
    * `RETRY_DELAY_SECONDS = 5`: Wait time before retrying a chunk.

2.  **Modifying the LLM Prompt:**
    The translation quality heavily depends on the prompt sent to the LLM. This is constructed in the `generate_translation_request` function, within the `structured_prompt` variable.

    ```python
    # Inside generate_translation_request function in translate.py:
    # ...
    # previous_translation_block_text = f"""...""" # Provides context

    # structured_prompt = f"""{previous_translation_block_text}
    # [START OF MAIN PART TO TRANSLATE ({source_lang_upper})]
    # {main_content}
    # [END OF MAIN PART TO TRANSLATE ({source_lang_upper})]
    # [ROLE] You are a professional translator, and your native language is {target_language}.
    # [INSTRUCTIONS] Your task is to translate in the author's style.
    # Precisely preserve the deeper meaning of the text, without necessarily adhering strictly to the original wording, to enhance style and fluidity.
    # For technical terms, you may retain the English words if they are commonly used in {target_language}.
    # It is critically important to adapt expressions and vocabulary to the {target_language} language.
    # Maintain the original layout of the text.
    # If the original text contains typos or extraneous elements, you may remove them.

    # Translate ONLY the text enclosed within the tags "[START OF MAIN PART TO TRANSLATE ({source_lang_upper})]" and "[END OF MAIN PART TO TRANSLATE ({source_lang_upper})]" from {source_language} into {target_language}.
    # Refer to the "[START OF PREVIOUS TRANSLATION BLOCK ({target_language})]""" section (if provided) to ensure stylistic and terminological consistency with previously translated text. Include the original novel's formatting. Surround your translation with <translate> and </translate> tags. For example: <translate>Your text translated here.</translate>
    # Return only the translation of the main part, formatted as requested. The translation must be framed by <translate> and </translate> tags. DO NOT WRITE ANYTHING BEFORE OR AFTER.
    # """
    # ...
    ```

    * **Key areas to customize in `structured_prompt`:**
        * **`[ROLE]` Definition:** Change the LLM's persona (e.g., "You are an expert technical writer...").
        * **`[INSTRUCTIONS]` Block:** Add, remove, or rephrase to guide style, tone, and handling of specific elements (idioms, technical terms, formality).
            * *Example for more literal translation:* "Provide a highly literal and accurate translation, adhering closely to the original wording and sentence structure."
        * **Formatting Instructions:** The current prompt asks to "Maintain the original layout" and crucially, "Surround your translation with `<translate>` and `</translate>` tags." **This tagging is vital for the script to extract the translation.**

    * **Tips for Prompt Engineering:**
        * Be specific and clear.
        * Experiment with small text samples.
        * Iterate on changes.
        * The `[START OF PREVIOUS TRANSLATION BLOCK]` helps maintain consistency.

3.  **Output Parsing:**
    The script uses a regular expression in `generate_translation_request` to find text between `<translate>` and `</translate>` tags:
    ```python
    match = re.search(r"<translate>(.*?)</translate>", full_raw_response, re.DOTALL)
    if match:
        extracted_translation = match.group(1).strip()
        # ...
    ```
    If you change the tags in the prompt, **you MUST update this regular expression** in `translate.py`, or the script will fail to extract translations.

### 8. Tips for Better Translations

* **Choose the Right Model:** Experiment with models available via Ollama (e.g., `qwen2:7b`, other Mistral variants, Llama models) for your specific language pair and content.
* **Adjust Chunk Size (`-cs` or `MAIN_LINES_PER_CHUNK`):**
    * *Too small:* May lose context, but faster per chunk.
    * *Too large:* Better context, but may hit model context limits (`OLLAMA_NUM_CTX`), increase processing time, or cause timeouts.
* **Refine the Prompt:** As detailed in section 7.2, this is key.
* **Pre-process Input:** Clean your input text (remove artifacts, correct major typos).
* **Post-process Output:** LLM translations usually require review and editing.
* **Context Window (`OLLAMA_NUM_CTX`):** Ensure it's appropriate for your model. Larger values use more memory.
* **Iterative Refinement:** For problematic sections, isolate them, adjust the prompt specifically, and re-translate.

### 9. Troubleshooting

* **Timeouts:** If translations time out, increase `REQUEST_TIMEOUT` in `translate.py`. Also, consider a smaller `chunksize` or a faster model.
* **Ollama Not Found/Connection Refused:**
    * Ensure Ollama application is running.
    * Check if any firewall is blocking `http://localhost:11434`.
    * Verify `API_ENDPOINT` in `translate.py` is correct.
* **Model Not Found:** Make sure you have pulled the specified model using `ollama pull your-model-name`.
* **Poor Translation Quality:**
    * Experiment with different models (see section 8).
    * Refine the LLM prompt (see section 7.2).
    * Adjust `chunksize`.
* **Script Fails to Extract Translation:** Ensure the LLM's output format (especially the `<translate>` tags) matches what the script expects (see section 7.3). Check Ollama logs or print the `full_raw_response` in the script for debugging.
* **Permission Denied (Writing Output File):** Ensure you have write permissions in the output directory.
