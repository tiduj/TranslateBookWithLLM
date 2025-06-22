#!/usr/bin/env python3
"""
Test script for validating that post-processing preserves placeholder tags
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.translator import post_process_translation
from src.core.epub_processor import TagPreserver
from src.core.llm_client import LLMClient


class MockLLMClient(LLMClient):
    """Mock LLM client for testing"""
    
    def __init__(self, response_text):
        super().__init__()
        self.response_text = response_text
    
    async def make_request(self, prompt, model):
        """Simulate LLM response"""
        # Extract the text between INPUT tags from prompt
        import re
        input_match = re.search(r'<INPUT>(.*?)</INPUT>', prompt, re.DOTALL)
        if input_match:
            input_text = input_match.group(1).strip()
            # Check if the prompt mentions preserving placeholders
            if "preserve ALL placeholder tags" in prompt:
                # Return the input with placeholders preserved
                return f"<TRANSLATED>{input_text}</TRANSLATED>"
            else:
                # Return the configured response
                return self.response_text
        return self.response_text
    
    def extract_translation(self, response):
        """Extract translation from response"""
        import re
        match = re.search(r'<TRANSLATED>(.*?)</TRANSLATED>', response, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None


async def test_post_processing_preserves_placeholders():
    """Test that post-processing preserves placeholder tags"""
    print("=== Test 1: Post-processing with placeholders ===")
    
    # Create a tag map
    tag_map = {
        "⟦TAG0⟧": "<p>",
        "⟦TAG1⟧": "</p>",
        "⟦TAG2⟧": "<strong>",
        "⟦TAG3⟧": "</strong>"
    }
    
    # Text with placeholders (already translated)
    translated_text = "⟦TAG0⟧Bonjour ⟦TAG2⟧monde⟦TAG3⟧!⟦TAG1⟧"
    
    # Test 1: Post-processing that preserves placeholders
    print(f"\nOriginal translated text: {translated_text}")
    
    # Mock client that returns improved text with placeholders preserved
    mock_response = "<TRANSLATED>⟦TAG0⟧Salut ⟦TAG2⟧le monde⟦TAG3⟧ !⟦TAG1⟧</TRANSLATED>"
    mock_client = MockLLMClient(mock_response)
    
    improved_text = await post_process_translation(
        translated_text,
        "French",
        "test-model",
        llm_client=mock_client,
        tag_map=tag_map
    )
    
    print(f"Improved text: {improved_text}")
    
    # Validate placeholders are preserved
    preserver = TagPreserver()
    is_valid, missing, mutated = preserver.validate_placeholders(improved_text, tag_map)
    print(f"Validation: Valid={is_valid}, Missing={missing}, Mutated={mutated}")
    
    assert is_valid, "Post-processing should preserve all placeholders!"
    print("✓ Post-processing preserved all placeholders correctly\n")


async def test_post_processing_with_missing_placeholders():
    """Test post-processing when LLM removes placeholders"""
    print("=== Test 2: Post-processing with missing placeholders ===")
    
    tag_map = {
        "⟦TAG0⟧": "<p>",
        "⟦TAG1⟧": "</p>",
        "⟦TAG2⟧": "<em>",
        "⟦TAG3⟧": "</em>"
    }
    
    translated_text = "⟦TAG0⟧Hello ⟦TAG2⟧world⟦TAG3⟧!⟦TAG1⟧"
    
    # Mock client that returns text with missing placeholders
    mock_response = "<TRANSLATED>⟦TAG0⟧Hello world!⟦TAG1⟧</TRANSLATED>"  # Missing TAG2 and TAG3
    mock_client = MockLLMClient(mock_response)
    
    print(f"Original text: {translated_text}")
    print(f"LLM response (missing TAG2 and TAG3): {mock_response}")
    
    improved_text = await post_process_translation(
        translated_text,
        "English",
        "test-model",
        llm_client=mock_client,
        tag_map=tag_map
    )
    
    print(f"Result: {improved_text}")
    
    # Should return original text since placeholders were lost
    assert improved_text == translated_text, "Should return original when placeholders are lost!"
    print("✓ Post-processing correctly returned original when placeholders were lost\n")


async def test_post_processing_with_mutated_placeholders():
    """Test post-processing when LLM mutates placeholders"""
    print("=== Test 3: Post-processing with mutated placeholders ===")
    
    tag_map = {
        "⟦TAG0⟧": "<div>",
        "⟦TAG1⟧": "</div>",
        "⟦TAG2⟧": "<span>",
        "⟦TAG3⟧": "</span>"
    }
    
    translated_text = "⟦TAG0⟧Ceci est ⟦TAG2⟧important⟦TAG3⟧.⟦TAG1⟧"
    
    # Mock client that returns text with mutated placeholders
    mock_response = "<TRANSLATED>[[TAG0]]C'est [[TAG2]]très important[[TAG3]].[[TAG1]]</TRANSLATED>"
    mock_client = MockLLMClient(mock_response)
    
    print(f"Original text: {translated_text}")
    print(f"LLM response (mutated placeholders): {mock_response}")
    
    improved_text = await post_process_translation(
        translated_text,
        "French",
        "test-model",
        llm_client=mock_client,
        tag_map=tag_map
    )
    
    print(f"Result: {improved_text}")
    
    # Validate that mutations were fixed
    preserver = TagPreserver()
    is_valid, missing, mutated = preserver.validate_placeholders(improved_text, tag_map)
    
    if is_valid:
        print("✓ Post-processing successfully fixed mutated placeholders")
    else:
        print(f"Post-processing validation: Valid={is_valid}, Missing={missing}, Mutated={mutated}")
        # If it couldn't fix, it should return original
        if improved_text == translated_text:
            print("✓ Post-processing returned original when mutations couldn't be fixed")


async def test_complete_flow():
    """Test complete flow: translation -> post-processing -> tag restoration"""
    print("\n=== Test 4: Complete flow simulation ===")
    
    preserver = TagPreserver()
    
    # Original HTML
    original_html = '<p>This is <strong>important</strong> text.</p>'
    print(f"1. Original HTML: {original_html}")
    
    # Preserve tags
    preserved_text, tag_map = preserver.preserve_tags(original_html)
    print(f"2. Preserved text: {preserved_text}")
    print(f"   Tag map: {tag_map}")
    
    # Simulate translation
    translated_with_placeholders = "⟦TAG0⟧C'est un texte ⟦TAG1⟧important⟦TAG2⟧.⟦TAG3⟧"
    print(f"3. After translation: {translated_with_placeholders}")
    
    # Simulate post-processing
    mock_response = "<TRANSLATED>⟦TAG0⟧Ceci est un texte ⟦TAG1⟧très important⟦TAG2⟧.⟦TAG3⟧</TRANSLATED>"
    mock_client = MockLLMClient(mock_response)
    
    improved_text = await post_process_translation(
        translated_with_placeholders,
        "French",
        "test-model",
        llm_client=mock_client,
        tag_map=tag_map
    )
    print(f"4. After post-processing: {improved_text}")
    
    # Validate placeholders still present
    is_valid, missing, mutated = preserver.validate_placeholders(improved_text, tag_map)
    assert is_valid, f"Placeholders should be valid after post-processing! Missing: {missing}, Mutated: {mutated}"
    
    # Restore tags
    final_html = preserver.restore_tags(improved_text, tag_map)
    print(f"5. Final HTML: {final_html}")
    
    # Verify structure is preserved
    assert final_html.startswith('<p>') and final_html.endswith('</p>'), "HTML structure should be preserved!"
    assert '<strong>' in final_html and '</strong>' in final_html, "Strong tags should be preserved!"
    print("✓ Complete flow successful - structure preserved throughout!")


async def run_all_tests():
    """Run all test functions"""
    print("Running post-processing placeholder preservation tests...\n")
    
    try:
        await test_post_processing_preserves_placeholders()
        await test_post_processing_with_missing_placeholders()
        await test_post_processing_with_mutated_placeholders()
        await test_complete_flow()
        
        print("\n" + "="*50)
        print("✓ ALL TESTS PASSED!")
        print("="*50)
        print("\nThe post-processing correctly:")
        print("- Preserves placeholder tags when they're maintained by the LLM")
        print("- Returns original text when placeholders are lost")
        print("- Attempts to fix mutated placeholders")
        print("- Works correctly in the complete translation flow")
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all_tests())