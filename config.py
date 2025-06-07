# --- Configuration ---
API_ENDPOINT = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "mistral-small:24b"
MAIN_LINES_PER_CHUNK = 25
REQUEST_TIMEOUT = 60
OLLAMA_NUM_CTX = 2048
SENTENCE_TERMINATORS = tuple(list(".!?") + ['."', '?"', '!"', '."', ".'", "?'", "!'", ":", ".)"])
MAX_TRANSLATION_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 2
TRANSLATE_TAG_IN = "<TRANSLATED>"
TRANSLATE_TAG_OUT = "</TRANSLATED>"
INPUT_TAG_IN = "<TO TRANSLATE>"
INPUT_TAG_OUT = "</TO TRANSLATE>"

# SRT-specific configuration
SRT_LINES_PER_BLOCK = 5  # Number of subtitle lines to translate together
SRT_MAX_CHARS_PER_BLOCK = 500  # Maximum characters per translation block

NAMESPACES = {
    'opf': 'http://www.idpf.org/2007/opf',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'xhtml': 'http://www.w3.org/1999/xhtml',
    'epub': 'http://www.idpf.org/2007/ops'
}

IGNORED_TAGS_EPUB = [
    '{http://www.w3.org/1999/xhtml}script',
    '{http://www.w3.org/1999/xhtml}style',
    '{http://www.w3.org/1999/xhtml}meta',
    '{http://www.w3.org/1999/xhtml}link'
]

CONTENT_BLOCK_TAGS_EPUB = [
    '{http://www.w3.org/1999/xhtml}p', '{http://www.w3.org/1999/xhtml}div',
    '{http://www.w3.org/1999/xhtml}li', '{http://www.w3.org/1999/xhtml}h1',
    '{http://www.w3.org/1999/xhtml}h2', '{http://www.w3.org/1999/xhtml}h3',
    '{http://www.w3.org/1999/xhtml}h4', '{http://www.w3.org/1999/xhtml}h5',
    '{http://www.w3.org/1999/xhtml}h6', '{http://www.w3.org/1999/xhtml}blockquote',
    '{http://www.w3.org/1999/xhtml}td', '{http://www.w3.org/1999/xhtml}th',
    '{http://www.w3.org/1999/xhtml}caption',
    '{http://www.w3.org/1999/xhtml}dt', '{http://www.w3.org/1999/xhtml}dd'
]