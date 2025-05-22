# TranslateBookWithLLM
A Python script designed for large-scale text translation, such as entire books, leveraging an LLM and the Ollama API.

## Comprehensive Guide: Running the Python Translation Script on Windows with Miniconda and Ollama

This guide will walk you through setting up the necessary tools, configuring your environment, and executing the Python translation script.

---

**Table of Contents:**

1.  **A. Prerequisites: Software Installation**
    * Install Miniconda (Python Environment Manager)
    * Install Ollama (Local LLM Runner)
    * Install Git (Version Control - Optional but Recommended)
    * Install a Code Editor (e.g., VS Code - Optional)
2.  **B. Setting up the Python Environment with Miniconda**
    * Create a Conda Environment
    * Activate the Environment
3.  **C. Getting the Translation Script**
    * Saving the Script Manually
    * (Alternative) Cloning from a GitHub Repository
4.  **D. Installing Python Dependencies**
5.  **E. Preparing and Running Ollama**
    * Pulling the Required LLM Model
    * Ensuring Ollama Service is Running
6.  **F. Running the Translation Script**
    * Understanding Script Arguments
    * Execution Command
    * Example Usage
7.  **G. Understanding Key Script Configurations**
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

3.  **Install Git (Version Control - Optional but Recommended)**
    * **What it is:** Git is a version control system. If the script is hosted on GitHub, Git makes it easy to download and update.
    * **Download:** Go to [https://git-scm.com/download/win](https://git-scm.com/download/win) and download the Windows installer.
    * **Installation:** Run the installer. Default settings are generally fine for most users. Ensure "Git Bash Here" and "Git GUI Here" are selected in the context menu options if you want easy access.

4.  **Install a Code Editor (e.g., VS Code - Optional)**
    * **What it is:** While not strictly necessary to run the script, a good code editor makes it easier to view, edit, and understand the Python code.
    * **Recommendation:** Visual Studio Code (VS Code) is a popular, free choice.
    * **Download:** Go to [https://code.visualstudio.com/](https://code.visualstudio.com/) and download the Windows installer.

### B. Setting up the Python Environment with Miniconda

1.  **Open Anaconda Prompt:**
    * Search for "Anaconda Prompt" (or "Miniconda Prompt") in your Windows Start Menu and open it. This terminal is pre-configured to use conda commands.

2.  **Create a Conda Environment:**
    * It's best practice to create a separate environment for each project to keep dependencies isolated. Let's call this environment `ollama_translator`.
    * In the Anaconda Prompt, type the following command and press Enter:
        ```bash
        conda create -n ollama_translator python=3.9
        ```
        (You can choose a different Python version like 3.10 or 3.11 if preferred, but 3.9 is a stable choice.)
    * Conda will show you the packages to be installed and ask for confirmation. Type `y` and press Enter.

3.  **Activate the Environment:**
    * Once the environment is created, activate it using:
        ```bash
        conda activate ollama_translator
        ```
    * Your prompt should now change to indicate that the `ollama_translator` environment is active (e.g., `(ollama_translator) C:\Users\YourUser>`).
    * **Important:** You will need to activate this environment every time you open a new Anaconda Prompt to work with this script.

### C. Getting the Translation Script

You have two main ways to get the script:

1.  **Saving the Script Manually (If you have the code directly):**
    * Open a plain text editor (like Notepad, or preferably VS Code).
    * Copy the entire Python script you provided in the prompt.
    * Paste it into the text editor.
    * Save the file with a `.py` extension (e.g., `ollama_translate_script.py`) in a directory of your choice (e.g., `C:\Projects\OllamaTranslator`). Make sure the "Save as type" is set to "All Files (\*.\*)" if using Notepad, to avoid it being saved as `ollama_translate_script.py.txt`.

2.  **(Alternative) Cloning from a GitHub Repository (If the script is hosted on GitHub):**
    * If the script were on a GitHub repository (e.g., `https://github.com/username/repository-name.git`), you would:
        * Open Anaconda Prompt (or Git Bash if you prefer).
        * Navigate to the directory where you want to store the project (e.g., `cd C:\Projects`).
        * Clone the repository:
            ```bash
            git clone https://github.com/username/repository-name.git
            ```
        * This will create a new folder (e.g., `C:\Projects\repository-name`) containing the script and any other files from the repository.
        * Navigate into the cloned repository folder:
            ```bash
            cd repository-name
            ```

For this guide, we'll assume you saved the script as `ollama_translate_script.py` in a folder like `C:\Projects\OllamaTranslator`.

### D. Installing Python Dependencies

The script imports several Python libraries. Some are built-in, but others need to be installed.

1.  **Ensure your conda environment is active:** Your prompt should show `(ollama_translator)`.
2.  **Navigate to your script's directory (optional but good practice):**
    ```bash
    cd C:\Projects\OllamaTranslator
    ```
3.  **Install the required packages using `pip` (Python's package installer), which is integrated with conda environments:**
    * The script uses `requests` and `tqdm`.
    ```bash
    pip install requests tqdm
    ```
    Pip will download and install these packages into your active `ollama_translator` environment.

### E. Preparing and Running Ollama

1.  **Pulling the Required LLM Model:**
    * The script defaults to using the model `mistral-small:24b` (as defined in `DEFAULT_MODEL`). You need to download this model via Ollama.
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

### F. Running the Translation Script

1.  **Prepare your input file:**
    * Create a plain text file (e.g., `input.txt`) containing the English text you want to translate. Save it in a known location, for example, within your project directory (`C:\Projects\OllamaTranslator`).

2.  **Open Anaconda Prompt and activate the environment:**
    * If you don't have it open already, open Anaconda Prompt.
    * Activate the environment:
        ```bash
        conda activate ollama_translator
        ```
    * Navigate to the directory where you saved `ollama_translate_script.py` and your `input.txt`:
        ```bash
        cd C:\Projects\OllamaTranslator
        ```

3.  **Understanding Script Arguments:**
    The script accepts command-line arguments to customize its behavior:
    * `-i` or `--input`: (Required) Path to the input text file.
    * `-o` or `--output`: (Required) Path to save the translated output file.
    * `-sl` or `--source_lang`: Source language (default: "English").
    * `-tl` or `--target_lang`: Target language (default: "French").
    * `-m` or `--model`: LLM model to use (default: `mistral-small:24b`). Make sure you've pulled this model with Ollama.
    * `-cs` or `--chunksize`: Target number of lines per translation chunk (default: `200`).

4.  **Execution Command:**
    The basic command structure is:
    ```bash
    python ollama_translate_script.py -i <your_input_file> -o <your_output_file> [options]
    ```

5.  **Example Usage:**
    * **To translate `input.txt` (English) to `output_fr.txt` (French) using the default model:**
        ```bash
        python ollama_translate_script.py -i input.txt -o output_fr.txt
        ```

    * **To translate `my_story_en.txt` to `my_story_de.txt` (German) using a different model (e.g., `qwen2:7b`, assuming you've pulled it):**
        ```bash
        python ollama_translate_script.py -i my_story_en.txt -o my_story_de.txt -sl English -tl German -m qwen2:7b
        ```

    * **To translate with a smaller chunk size:**
        ```bash
        python ollama_translate_script.py -i input.txt -o output_fr.txt -cs 100
        ```

    The script will then start processing, showing a progress bar for the chunks being translated.

### G. Understanding Key Script Configurations (Inside the Python file)

While command-line arguments are preferred for run-specific changes, the script has some internal configurations you might want to be aware of or adjust if needed:

* `API_ENDPOINT = "http://localhost:11434/api/generate"`: If your Ollama is running on a different port or host (unlikely for typical local setups).
* `DEFAULT_MODEL = "mistral-small:24b"`: The default model if not specified via CLI.
* `MAIN_LINES_PER_CHUNK = 200`: Default chunk size if not specified via CLI.
* `REQUEST_TIMEOUT = 2`: Timeout in seconds for API requests. **You might need to increase this if your model is slow or texts are very long per chunk, leading to timeouts.** For example, `REQUEST_TIMEOUT = 120` (for 2 minutes).
* `OLLAMA_NUM_CTX = 4096`: Context window size for Ollama. This is model-dependent. Some models support larger context windows. Adjusting this can impact memory usage and how much context the model "remembers."
* `MAX_TRANSLATION_ATTEMPTS = 2`: How many times to retry a failing chunk.
* `RETRY_DELAY_SECONDS = 2`: Wait time before retrying.

If you modify these directly in the script, remember to save the file.

### H. Troubleshooting and Tips

* **`ModuleNotFoundError`:** You haven't installed a required package or haven't activated the correct conda environment. Ensure `(ollama_translator)` is in your prompt and run `pip install <missing_package_name>`.
* **`conda: command not found` (in regular cmd/PowerShell):** Miniconda is not in your system PATH. Use the "Anaconda Prompt" instead, or add Miniconda to your PATH (re-open terminal after).
* **Ollama Connection Errors (e.g., `ConnectionRefusedError`):**
    * Ensure the Ollama application is running. Check your system tray or task manager.
    * Verify the `API_ENDPOINT` in the script matches where Ollama is listening (default is usually correct).
    * Check if a firewall is blocking the connection to `localhost:11434`.
* **Model Not Found by Ollama:**
    * Ensure you've pulled the model using `ollama pull <model_name>`.
    * Double-check the model name spelling in the script or command-line argument.
* **Slow Translations / Timeouts:**
    * Larger models are slower.
    * Your hardware (CPU/GPU, RAM) impacts speed.
    * Increase `REQUEST_TIMEOUT` in the script if API calls are consistently timing out.
    * Consider reducing `MAIN_LINES_PER_CHUNK` to send smaller pieces of text, which might process faster individually but result in more API calls.
* **Poor Translation Quality:**
    * Experiment with different models. Some models are better for specific language pairs or styles. The script mentions `mistral-small:24b` is "best for french language" – this is subjective and model performance changes.
    * The prompt engineering within `generate_translation_request` function is crucial. You might need to tweak the instructions for the LLM if results are not satisfactory.
    * Ensure `OLLAMA_NUM_CTX` is appropriate for the model. Too small can truncate context.
* **`Error translating/extracting chunk... Marking as ERROR in output.`:**
    * This means the LLM failed to provide a valid response or the script couldn't parse it (e.g., missing `<translate>` tags) after `MAX_TRANSLATION_ATTEMPTS`.
    * Check Ollama's logs for more detailed errors (often accessible via the Ollama system tray icon or command line).
    * The model might be overloaded, or the input for that chunk could be problematic.
    * Try increasing `REQUEST_TIMEOUT` or `MAX_TRANSLATION_ATTEMPTS`.
* **Output File Issues:** Ensure you have write permissions in the directory specified for the output file.
* **To stop a running script:** Press `Ctrl+C` in the Anaconda Prompt.

---

This comprehensive guide should help you get the translation script up and running. Remember to adapt file paths and model names to your specific setup. Good luck!
