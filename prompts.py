# prompts.py
def generate_translation_prompt(main_content, context_before, context_after, previous_translation_context,
                               source_language="English", target_language="French", 
                               translate_tag_in="[TRANSLATED]", translate_tag_out="[/TRANSLATED]",
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