# TranslateBookWithLLM
A Python script designed for large-scale text translation, such as entire books, leveraging an LLM and the Ollama API.

## Windows Installation

This guide will walk you through setting up the necessary tools, configuring your environment, and executing the Python translation script.

---

**Table of Contents:**

1.  **A. Prerequisites: Software Installation**
    * Install Miniconda (Python Environment Manager)
    * Install Ollama (Local LLM Runner)
    * Install Git (Version Control - Recommended)
    * Install a Code Editor (e.g., VS Code - Optional)
2.  **B. Setting up the Python Environment with Miniconda (as `translate_book_env`)**
    * Create a Conda Environment
    * Activate the Environment
3.  **C. Getting the Translation Script (`translate.py`)**
    * Cloning from the `TranslateBookWithLLM` GitHub Repository (Recommended)
    * Saving the Script Manually
4.  **D. Installing Python Dependencies (in `translate_book_env`)**
5.  **E. Preparing and Running Ollama**
    * Pulling the Required LLM Model
    * Ensuring Ollama Service is Running
6.  **F. Running the Translation Script (`translate.py`) from `translate_book_env`**
    * Prepare your input file
    * Understanding Script Arguments
    * Execution Command
    * Example Usage
7.  **G. Understanding Key Script Configurations (Inside `translate.py`)**
8.  **H. Troubleshooting and Tips**

---

### A. Prerequisites: Software Installation

1.  **Install Miniconda (Python Environment Manager)**
    * **What it is:** Miniconda is a minimal installer for conda, a package, and environment manager. It helps you create isolated Python environments to avoid conflicts between project dependencies.
    * **Download:** Go to the Miniconda documentation page ([https://docs.conda.io/en/latest/miniconda.html](https://docs.conda.io/en/latest/miniconda.html)) and download the latest Windows 64-bit installer (Python 3.x version).
    * **Installation:**
        * Run the installer.
        * Choose "Install for me only" unless you have specific reasons for "All Users".
        * It's generally recommended **NOT** to add Miniconda to your PATH environment variable during installation if the installer advises against it (it can interfere with other Python installations). Instead, use the "Anaconda Prompt" (or "Miniconda Prompt") installed with Miniconda to access conda commands. If you *do* add it to PATH, ensure you understand the implications.
        * Accept default settings for other options unless you know what you're doing.

2.  **Install Ollama (Local LLM Runner)**
    * **What it is:** Ollama allows you to run large language models (LLMs) locally on your machine.
    * **Download:** Go to the Ollama website ([https://ollama.com/](https://ollama.com/)) and download the Windows installer.
    * **Installation:** Run the installer and follow the on-screen instructions. Ollama will typically set itself up to run in the background.

3.  **Install Git (Version Control - Recommended)**
    * **What it is:** Git is a version control system. Since the script comes from a GitHub repository (`TranslateBookWithLLM`), Git is the best way to download it and keep it updated.
    * **Download:** Go to [https://git-scm.com/download/win](https://git-scm.com/download/win) and download the Windows installer.
    * **Installation:** Run the installer. Default settings are generally fine for most users. Ensure "Git Bash Here" and "Git GUI Here" are selected in the context menu options if you want easy access.

4.  **Install a Code Editor (e.g., VS Code - Optional)**
    * **What it is:** While not strictly necessary to run the script, a good code editor makes it easier to view, edit, and understand the Python code (`translate.py`).
    * **Recommendation:** Visual Studio Code (VS Code) is a popular, free choice.
    * **Download:** Go to [https://code.visualstudio.com/](https://code.visualstudio.com/) and download the Windows installer.

### B. Setting up the Python Environment with Miniconda (as `translate_book_env`)

1.  **Open Anaconda Prompt:**
    * Search for "Anaconda Prompt" (or "Miniconda Prompt") in your Windows Start Menu and open it. This terminal is pre-configured to use conda commands.

2.  **Create a Conda Environment:**
    * We will name the environment `translate_book_env` to align with the project's purpose.
    * In the Anaconda Prompt, type the following command and press Enter:
        ```bash
        conda create -n translate_book_env python=3.9
        ```
        (You can choose a different Python version like 3.10 or 3.11 if preferred, but 3.9 is a stable choice.)
    * Conda will show you the packages to be installed and ask for confirmation. Type `y` and press Enter.

3.  **Activate the Environment:**
    * Once the environment is created, activate it using:
        ```bash
        conda activate translate_book_env
        ```
    * Your prompt should now change to indicate that the `translate_book_env` environment is active (e.g., `(translate_book_env) C:\Users\YourUser>`).
    * **Important:** You will need to activate this environment every time you open a new Anaconda Prompt to work with this script.

### C. Getting the Translation Script (`translate.py`)

1.  **Cloning from the `TranslateBookWithLLM` GitHub Repository (Recommended):**
    * Open Anaconda Prompt (or Git Bash if you prefer).
    * Navigate to the directory where you want to store your projects (e.g., `C:\Projects`). If the `Projects` directory doesn't exist, you can create it first with `mkdir C:\Projects`.
        ```bash
        cd C:\Projects
        ```
    * Clone the repository. You'll need the correct URL for the `TranslateBookWithLLM` repository. It will look something like `https://github.com/YourUsername/TranslateBookWithLLM.git`. **Replace `YourUsername` with the actual GitHub username of the repository owner.**
        ```bash
        git clone https://github.com/YourUsername/TranslateBookWithLLM.git
        ```
    * This will create a new folder named `TranslateBookWithLLM` inside your `C:\Projects` directory (i.e., `C:\Projects\TranslateBookWithLLM`). This folder will contain `translate.py` and any other files from the repository.
    * Navigate into the cloned repository folder:
        ```bash
        cd TranslateBookWithLLM
        ```
    This is the recommended method as it allows you to easily get updates to the script using `git pull`.

2.  **Saving the Script Manually (Alternative, if not using Git):**
    * If you have the code for `translate.py` directly (e.g., from the initial prompt):
    * Create a folder for your project, for example, `C:\Projects\TranslateBookWithLLM`.
    * Open a plain text editor (like Notepad, or preferably VS Code).
    * Copy the entire Python script code.
    * Paste it into the text editor.
    * Save the file as `translate.py` inside your project folder (e.g., `C:\Projects\TranslateBookWithLLM\translate.py`). Make sure the "Save as type" is set to "All Files (\*.\*)" if using Notepad, to avoid it being saved as `translate.py.txt`.

For this guide, we'll assume you have the script `translate.py` located in `C:\Projects\TranslateBookWithLLM`.

### D. Installing Python Dependencies (in `translate_book_env`)

1.  **Ensure your conda environment is active:** Your prompt should show `(translate_book_env)`.
2.  **Navigate to your script's directory:** If you cloned the repository or created the folder, make sure you are in it.
    ```bash
    cd C:\Projects\TranslateBookWithLLM
    ```
    (If you are already in this directory from the previous step, you don't need to do this again).
3.  **Install the required packages using `pip` (Python's package installer), which is integrated with conda environments:**
    * The script uses `requests` and `tqdm`.
    ```bash
    pip install requests tqdm
    ```
    Pip will download and install these packages into your active `translate_book_env` environment.

### E. Preparing and Running Ollama

1.  **Pulling the Required LLM Model:**
    * The script defaults to using the model `mistral-small:24b` (as defined in `DEFAULT_MODEL` within `translate.py`). You need to download this model via Ollama.
    * Open a new regular Command Prompt or PowerShell (or use the Anaconda Prompt).
    * Run the following command:
        ```bash
        ollama pull mistral-small:24b
        ```
    * This might take some time depending on your internet speed and the model size.
    * If you plan to use a different model (e.g., by specifying it with the `-m` argument when running the script), pull that model instead (e.g., `ollama pull qwen2:7b`).
    * You can see all models you've pulled with `ollama list`.

2.  **Ensuring Ollama Service is Running:**
    * Ollama typically runs as a background service after installation. You might see an Ollama icon in your system tray.
    * If it's not running, try launching the Ollama application from your Start Menu.
    * The script tries to connect to Ollama at `http://localhost:11434`. Make sure no firewall is blocking this local connection.

### F. Running the Translation Script (`translate.py`) from `translate_book_env`

1.  **Prepare your input file:**
    * Create a plain text file (e.g., `input.txt`) containing the text you want to translate. Save it in a known location. For ease of use, you can save it inside your project directory (`C:\Projects\TranslateBookWithLLM`).

2.  **Open Anaconda Prompt and activate the environment:**
    * If you don't have it open already, open Anaconda Prompt.
    * Activate the `translate_book_env` environment:
        ```bash
        conda activate translate_book_env
        ```
    * Navigate to the directory where `translate.py` is located:
        ```bash
        cd C:\Projects\TranslateBookWithLLM
        ```

3.  **Understanding Script Arguments:**
    The script `translate.py` accepts command-line arguments to customize its behavior:
    * `-i` or `--input`: (Required) Path to the input text file.
    * `-o` or `--output`: (Required) Path to save the translated output file.
    * `-sl` or `--source_lang`: Source language (default: "English").
    * `-tl` or `--target_lang`: Target language (default: "French").
    * `-m` or `--model`: LLM model to use (default: `mistral-small:24b`). Make sure you've pulled this model with Ollama.
    * `-cs` or `--chunksize`: Target number of lines per translation chunk (default: `200`).

4.  **Execution Command:**
    The basic command structure is:
    ```bash
    python translate.py -i <your_input_file> -o <your_output_file> [options]
    ```

5.  **Example Usage:**
    * **To translate `input.txt` (assumed to be in the current directory `C:\Projects\TranslateBookWithLLM`) from English to `output_fr.txt` (French) using the default model:**
        ```bash
        python translate.py -i input.txt -o output_fr.txt
        ```

    * **To translate a file from a different location, providing full paths:**
        ```bash
        python translate.py -i C:\Path\To\Your\my_story_en.txt -o C:\Path\To\Your\my_story_de.txt -sl English -tl German -m qwen2:7b
        ```
        *(Remember to pull `qwen2:7b` first if you use it: `ollama pull qwen2:7b`)*

    * **To translate `input.txt` with a smaller chunk size:**
        ```bash
        python translate.py -i input.txt -o output_fr.txt -cs 100
        ```

    The script will then start processing, showing a progress bar for the chunks being translated.

### G. Understanding Key Script Configurations (Inside `translate.py`)

While command-line arguments are preferred for run-specific changes, the script `translate.py` has some internal configurations you might want to be aware of or adjust if needed by editing the file itself:

* `API_ENDPOINT = "http://localhost:11434/api/generate"`: If your Ollama is running on a different port or host (unlikely for typical local setups).
* `DEFAULT_MODEL = "mistral-small:24b"`: The default model if not specified via CLI.
* `MAIN_LINES_PER_CHUNK = 200`: Default chunk size if not specified via CLI.
* `REQUEST_TIMEOUT = 2`: Timeout in seconds for API requests. **You might need to increase this if your model is slow or texts are very long per chunk, leading to timeouts.** For example, `REQUEST_TIMEOUT = 120` (for 2 minutes).
* `OLLAMA_NUM_CTX = 4096`: Context window size for Ollama. This is model-dependent. Some models support larger context windows. Adjusting this can impact memory usage and how much context the model "remembers."
* `MAX_TRANSLATION_ATTEMPTS = 2`: How many times to retry a failing chunk.
* `RETRY_DELAY_SECONDS = 2`: Wait time before retrying.

If you modify these directly in `translate.py`, remember to save the file.

---

### Modifying the LLM Prompt

The quality and style of the translation heavily depend on the prompt sent to the LLM. The prompt is constructed within the `generate_translation_request` function, specifically in the `structured_prompt` variable.

```python
# Inside generate_translation_request function:
# ...
# previous_translation_block_text = f"""...""" # Provides context from previous translation

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
# Refer to the "[START OF PREVIOUS TRANSLATION BLOCK ({target_language})]" section (if provided) to ensure stylistic and terminological consistency with previously translated text. Include the original novel's formatting. Surround your translation with <translate> and </translate> tags. For example: <translate>Your text translated here.</translate>
# Return only the translation of the main part, formatted as requested. The translation must be framed by <translate> and </translate> tags. DO NOT WRITE ANYTHING BEFORE OR AFTER.
# """
# ...
```

**Key areas you might want to customize in the `structured_prompt`:**

1.  **`[ROLE]` Definition:**
    * `You are a professional translator, and your native language is {target_language}.`
    * You can change the persona. For example, "You are an expert technical writer..." or "You are a creative storyteller..."

2.  **`[INSTRUCTIONS]` Block:**
    * This is the most impactful part. You can add, remove, or rephrase instructions to guide the LLM's translation style, tone, and handling of specific elements (e.g., idioms, technical terms, formality).
    * Example: If you want a more literal translation, you could change: "Precisely preserve the deeper meaning... without necessarily adhering strictly to the original wording..." to "Provide a highly literal and accurate translation, adhering closely to the original wording and sentence structure."
    * You can specify how to handle dialogue, character names, or placeholders.

3.  **Formatting Instructions:**
    * The current prompt asks to "Maintain the original layout" and "Include the original novel's formatting."
    * It also crucially instructs: "Surround your translation with `<translate>` and `</translate>` tags." **This is vital for the script to extract the translation.** If you modify this, ensure the script's parsing logic (see below) is also updated.

**Tips for Prompt Engineering:**

* **Be Specific:** Clearly state what you want and what you don't want.
* **Experiment:** Different models respond differently to prompts. Test changes on small text samples.
* **Iterate:** Make small changes and observe the results.
* **Context:** The prompt includes `[START OF PREVIOUS TRANSLATION BLOCK ({target_language})]` to provide the LLM with the last successfully translated chunk. This helps maintain consistency.

### Output Parsing

The script expects the LLM's response to contain the translation enclosed in `<translate>` and `</translate>` tags. This is handled by the following `re.search` in `generate_translation_request`:

```python
match = re.search(r"<translate>(.*?)</translate>", full_raw_response, re.DOTALL)
if match:
    extracted_translation = match.group(1).strip()
    return extracted_translation
else:
    # ... error handling ...
    return None
```
If you modify the prompt to use different tags (or no tags), you **must** update this regular expression accordingly, or the script will fail to extract the translated text.

## 5. Tips for Better Translations

* **Choose the Right Model:** Different LLMs excel at different languages and tasks. The default `mistral-small:24b` is noted as "best for french language" in the script comments, but experiment with other models available through Ollama (e.g., `qwen2:7b`, other Mistral variants, Llama models) for your specific language pair and content type.
* **Adjust Chunk Size (`-cs` or `MAIN_LINES_PER_CHUNK`):**
    * Too small: May lose broader context, leading to disjointed translations, but faster per chunk.
    * Too large: Better context, but may hit model context limits (`OLLAMA_NUM_CTX`), increase processing time per chunk, or lead to timeouts.
* **Refine the Prompt:** As detailed above, prompt engineering is key.
* **Pre-process Input:** Clean your input text. Remove unnecessary artifacts, correct major typos if the LLM struggles with them.
* **Post-process Output:** LLM translations are rarely perfect. Plan for a review and editing phase.
* **Context Window (`OLLAMA_NUM_CTX`):** Ensure this is set appropriately for your chosen model. A larger context window allows the model to "see" more of the surrounding text (if your chunking/context logic provides it), which can improve coherence. However, it also increases memory requirements.
* **Iterative Refinement:** If a particular section is poorly translated, you might isolate it, adjust the prompt specifically for that type of content, and re-translate only that part.

```
