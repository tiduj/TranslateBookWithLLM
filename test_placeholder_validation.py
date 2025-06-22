#!/usr/bin/env python3
"""
Test script for validating placeholder tag handling improvements
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.epub_processor import TagPreserver


def test_tag_preservation():
    """Test basic tag preservation and restoration"""
    print("=== Test 1: Basic tag preservation ===")
    
    preserver = TagPreserver()
    
    # Test HTML content with various tags
    original_text = '<p>Hello <strong>world</strong>! <br/> This is a <em>test</em>.</p>'
    print(f"Original: {original_text}")
    
    # Preserve tags
    preserved_text, tag_map = preserver.preserve_tags(original_text)
    print(f"Preserved: {preserved_text}")
    print(f"Tag map: {tag_map}")
    
    # Restore tags
    restored_text = preserver.restore_tags(preserved_text, tag_map)
    print(f"Restored: {restored_text}")
    
    assert restored_text == original_text, "Restoration failed!"
    print("✓ Basic preservation/restoration works correctly\n")


def test_placeholder_validation():
    """Test placeholder validation functionality"""
    print("=== Test 2: Placeholder validation ===")
    
    preserver = TagPreserver()
    
    # Create a tag map
    tag_map = {
        "⟦TAG0⟧": "<p>",
        "⟦TAG1⟧": "</p>",
        "⟦TAG2⟧": "<strong>",
        "⟦TAG3⟧": "</strong>"
    }
    
    # Test 1: All placeholders present
    text_valid = "⟦TAG0⟧Hello ⟦TAG2⟧world⟦TAG3⟧!⟦TAG1⟧"
    is_valid, missing, mutated = preserver.validate_placeholders(text_valid, tag_map)
    print(f"Valid text: {text_valid}")
    print(f"Is valid: {is_valid}, Missing: {missing}, Mutated: {mutated}")
    assert is_valid, "Should be valid!"
    print("✓ Valid placeholder detection works\n")
    
    # Test 2: Missing placeholders
    text_missing = "⟦TAG0⟧Hello world!⟦TAG1⟧"  # Missing TAG2 and TAG3
    is_valid, missing, mutated = preserver.validate_placeholders(text_missing, tag_map)
    print(f"Text with missing tags: {text_missing}")
    print(f"Is valid: {is_valid}, Missing: {missing}, Mutated: {mutated}")
    assert not is_valid, "Should be invalid!"
    assert len(missing) == 2, "Should have 2 missing tags!"
    print("✓ Missing placeholder detection works\n")


def test_mutation_detection():
    """Test detection of mutated placeholders"""
    print("=== Test 3: Mutation detection ===")
    
    preserver = TagPreserver()
    
    tag_map = {
        "⟦TAG0⟧": "<p>",
        "⟦TAG1⟧": "</p>",
        "⟦TAG2⟧": "<br/>"
    }
    
    # Test various mutations
    mutations_to_test = [
        ("[[TAG0]]Hello[[TAG1]][[TAG2]]", "Double brackets"),
        ("[TAG0]Hello[TAG1][TAG2]", "Single brackets"),
        ("TAG0 Hello TAG1 TAG2", "No brackets"),
        ("{TAG0}Hello{TAG1}{TAG2}", "Curly braces"),
        ("<TAG0>Hello<TAG1><TAG2>", "Angle brackets"),
    ]
    
    for mutated_text, description in mutations_to_test:
        print(f"\nTesting {description}: {mutated_text}")
        is_valid, missing, mutated = preserver.validate_placeholders(mutated_text, tag_map)
        print(f"Is valid: {is_valid}, Missing: {missing}, Mutated: {mutated}")
        
        assert not is_valid, f"Should be invalid for {description}!"
        assert len(mutated) > 0, f"Should detect mutations for {description}!"
        
        # Test fixing mutations
        fixed_text = preserver.fix_mutated_placeholders(mutated_text, mutated)
        print(f"Fixed text: {fixed_text}")
        
        # Validate fixed text
        is_valid_fixed, missing_fixed, mutated_fixed = preserver.validate_placeholders(fixed_text, tag_map)
        assert is_valid_fixed, f"Fixed text should be valid for {description}!"
        print(f"✓ Mutation detection and fixing works for {description}")


def test_complex_scenario():
    """Test a complex scenario with mixed issues"""
    print("\n=== Test 4: Complex scenario ===")
    
    preserver = TagPreserver()
    
    # Original HTML
    original_html = '<div class="content"><p>This is <strong>important</strong> text.</p><br/></div>'
    print(f"Original HTML: {original_html}")
    
    # Preserve tags
    preserved_text, tag_map = preserver.preserve_tags(original_html)
    print(f"Preserved text: {preserved_text}")
    
    # Simulate LLM output with various issues
    llm_outputs = [
        # Some tags mutated, some missing
        '[[TAG0]][[TAG1]]This is [[TAG2]]important text.⟦TAG4⟧⟦TAG5⟧⟦TAG6⟧',
        # All tags mutated differently
        '<TAG0><TAG1>This is {TAG2}important{TAG3} text.<TAG4><TAG5><TAG6>',
        # Mix of correct and mutated
        '⟦TAG0⟧[TAG1]This is ⟦TAG2⟧important[[TAG3]] text.⟦TAG4⟧TAG5⟦TAG6⟧',
    ]
    
    for i, llm_output in enumerate(llm_outputs):
        print(f"\n--- LLM Output {i+1}: {llm_output}")
        
        # Validate
        is_valid, missing, mutated = preserver.validate_placeholders(llm_output, tag_map)
        print(f"Initial validation - Is valid: {is_valid}, Missing: {missing}, Mutated: {mutated}")
        
        if not is_valid:
            # Try to fix mutations
            if mutated:
                fixed_output = preserver.fix_mutated_placeholders(llm_output, mutated)
                print(f"After mutation fix: {fixed_output}")
                
                # Re-validate
                is_valid, missing, mutated = preserver.validate_placeholders(fixed_output, tag_map)
                print(f"After fix - Is valid: {is_valid}, Missing: {missing}, Mutated: {mutated}")
                
                if is_valid:
                    # Restore tags
                    restored = preserver.restore_tags(fixed_output, tag_map)
                    print(f"Restored HTML: {restored}")
                    assert restored == original_html, f"Restoration failed for output {i+1}!"
                    print(f"✓ Successfully handled LLM output {i+1}")
                else:
                    print(f"✗ Could not fully fix LLM output {i+1} - would need retry")
            else:
                print(f"✗ Missing placeholders in output {i+1} - would need retry")


async def test_integration_with_retry():
    """Test integration scenario simulating retry logic"""
    print("\n=== Test 5: Integration test with retry simulation ===")
    
    preserver = TagPreserver()
    
    # Simulate EPUB content
    epub_content = '<p>Bonjour <strong>le monde</strong>! <br/> Ceci est un <em>test</em>.</p>'
    preserved_text, tag_map = preserver.preserve_tags(epub_content)
    
    print(f"Original content: {epub_content}")
    print(f"Text to translate: {preserved_text}")
    
    # Simulate first translation attempt (with missing/mutated tags)
    first_translation = "⟦TAG0⟧Hello [[TAG2]]world[[TAG3]]! This is a ⟦TAG6⟧test⟦TAG7⟧.⟦TAG1⟧"
    print(f"\nFirst translation attempt: {first_translation}")
    
    is_valid, missing, mutated = preserver.validate_placeholders(first_translation, tag_map)
    print(f"Validation: Valid={is_valid}, Missing={missing}, Mutated={mutated}")
    
    if not is_valid:
        # Fix mutations first
        if mutated:
            first_translation = preserver.fix_mutated_placeholders(first_translation, mutated)
            is_valid, missing, mutated = preserver.validate_placeholders(first_translation, tag_map)
        
        if not is_valid and missing:
            print(f"\nRetrying translation with emphasis on missing tags: {missing}")
            # Simulate retry with better result
            retry_translation = "⟦TAG0⟧Hello ⟦TAG2⟧world⟦TAG3⟧! ⟦TAG4⟧ This is a ⟦TAG6⟧test⟦TAG7⟧.⟦TAG1⟧"
            print(f"Retry translation: {retry_translation}")
            
            is_valid, missing, mutated = preserver.validate_placeholders(retry_translation, tag_map)
            print(f"Retry validation: Valid={is_valid}, Missing={missing}, Mutated={mutated}")
            
            if is_valid:
                # Restore tags
                final_result = preserver.restore_tags(retry_translation, tag_map)
                print(f"\nFinal result: {final_result}")
                print("✓ Retry successful - all placeholders preserved!")
            else:
                print("✗ Retry failed - would use original with missing tags")


def run_all_tests():
    """Run all test functions"""
    print("Running placeholder validation tests...\n")
    
    try:
        test_tag_preservation()
        test_placeholder_validation()
        test_mutation_detection()
        test_complex_scenario()
        asyncio.run(test_integration_with_retry())
        
        print("\n" + "="*50)
        print("✓ ALL TESTS PASSED!")
        print("="*50)
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()