from config import TRANSLATE_TAG_IN, TRANSLATE_TAG_OUT

def generate_translation_prompt(main_content, context_before, context_after, previous_translation_context,
                               source_language="English", target_language="French", 
                               translate_tag_in=TRANSLATE_TAG_IN, translate_tag_out=TRANSLATE_TAG_OUT,
                               custom_instructions=""):
    """
    Generate the translation prompt with all contextual elements.
    
    Returns:
    str: The complete prompt formatted for translation
    """
    source_lang = source_language.upper()

    # PROMPT - can be edited for custom usages
    role_and_instructions_block = f"""
## ROLE
# You are a {target_language} writer.

## TRANSLATION
+ Translate in the author's style
+ Preserve meaning and enhance fluidity
+ Adapt expressions and culture to the {target_language} language
+ Maintain the original layout of the text

## FORMATING
+ Translate ONLY the text enclosed within the tags "[TO TRANSLATE]" and "[/TO TRANSLATE]" from {source_lang} into {target_language}
+ Surround your translation with {translate_tag_in} and {translate_tag_out} tags. For example: {translate_tag_in}Your text translated here.{translate_tag_out}
+ Return ONLY the translation, formatted as requested
"""

    previous_translation_block_text = ""
    if previous_translation_context and previous_translation_context.strip():
        previous_translation_block_text = f"""

## Previous paragraph :
(...) {previous_translation_context}

"""

    custom_instructions_block = ""
    if custom_instructions and custom_instructions.strip():
        custom_instructions_block = f"""

### INSTRUCTIONS
{custom_instructions.strip()}

"""

    text_to_translate_block = f"""
[TO TRANSLATE]
{main_content}
[/TO TRANSLATE]"""

    structured_prompt_parts = [
        role_and_instructions_block,
        custom_instructions_block,
        previous_translation_block_text,
        text_to_translate_block
    ]
    
    return "\n\n".join(part.strip() for part in structured_prompt_parts if part and part.strip()).strip()


def generate_subtitle_block_prompt(subtitle_blocks, previous_translation_block, 
                                 source_language="English", target_language="French",
                                 translate_tag_in=TRANSLATE_TAG_IN, translate_tag_out=TRANSLATE_TAG_OUT,
                                 custom_instructions=""):
    """
    Generate translation prompt for multiple subtitle blocks with index markers.
    
    Args:
        subtitle_blocks: List of tuples (index, text) for subtitles to translate
        previous_translation_block: Previous translated block for context
        source_language: Source language 
        target_language: Target language
        translate_tag_in/out: Tags for translation markers
        custom_instructions: Additional translation instructions
        
    Returns:
        str: The complete prompt formatted for subtitle block translation
    """
    source_lang = source_language.upper()
    
    # Enhanced instructions for subtitle translation
    role_and_instructions_block = f"""
## ROLE
# You are a {target_language} subtitle translator and dialogue adaptation specialist.

## TRANSLATION
+ Translate dialogues naturally for subtitles
+ Adapt expressions and cultural references for {target_language} viewers
+ Keep subtitle length appropriate for reading speed

## FORMATING
+ Translate ONLY the text enclosed within the tags "[TO TRANSLATE]" and "[/TO TRANSLATE]" from {source_lang} into {target_language}
+ Each subtitle is marked with its index: [index]text
+ A la fin d'UN subtitle passe TOUJOURS à la ligne
+ Preserve the index markers in your translation
+ Surround your ENTIRE translation block with {translate_tag_in} and {translate_tag_out} tags
+ Return ONLY the translation block, formatted as requested
+ Maintain line breaks between indexed subtitles
"""

    # Custom instructions
    custom_instructions_block = ""
    if custom_instructions and custom_instructions.strip():
        custom_instructions_block = f"""
### ADDITIONAL INSTRUCTIONS
{custom_instructions.strip()}
"""
        
    # Previous translation context
    previous_translation_block_text = ""
    if previous_translation_block and previous_translation_block.strip():
        previous_translation_block_text = f"""
## Previous subtitle block (for context and consistency):
{previous_translation_block}
"""
        
    # Format subtitle blocks with indices
    formatted_subtitles = []
    for idx, text in subtitle_blocks:
        formatted_subtitles.append(f"[{idx}]{text}")
    
    text_to_translate_block = f"""
[TO TRANSLATE]
{chr(10).join(formatted_subtitles)}
[/TO TRANSLATE]"""

    structured_prompt_parts = [
        role_and_instructions_block,
        custom_instructions_block,
        previous_translation_block_text,
        text_to_translate_block
    ]
    
    return "\n\n".join(part.strip() for part in structured_prompt_parts if part and part.strip()).strip()