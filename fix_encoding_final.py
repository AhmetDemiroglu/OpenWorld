#!/usr/bin/env python3
"""
Final fix for mojibake encoding issues.

The corruption is severe - multiple levels of UTF-8 → Latin-1 → UTF-8.
We'll use iterative decoding to fix it.
"""

import shutil
from pathlib import Path


def iterative_decode(text, max_iterations=5):
    """
    Iteratively try to fix mojibake by:
    1. Encode text as UTF-8 to get bytes
    2. Decode bytes as if they were Latin-1
    3. If result is different, repeat
    
    This reverses the process where UTF-8 bytes were interpreted as Latin-1 chars.
    """
    result = text
    for i in range(max_iterations):
        try:
            # Get the UTF-8 bytes of the current string
            utf8_bytes = result.encode('utf-8')
            # Interpret these bytes as Latin-1 (which accepts all 0-255 values)
            latin1_text = utf8_bytes.decode('latin-1')
            # Now encode as UTF-8 again and see if we get valid text
            new_bytes = latin1_text.encode('utf-8')
            # Try to decode these new bytes
            new_text = new_bytes.decode('utf-8')
            
            if new_text == result:
                # No change, we're done
                break
            result = new_text
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
    return result


def encode_latin1_decode_utf8(text):
    """
    Direct approach: encode as latin1, decode as utf-8.
    This works when the file contains UTF-8 bytes that were 
    interpreted as characters in some single-byte encoding.
    """
    try:
        # First get the UTF-8 representation
        utf8_bytes = text.encode('utf-8')
        # Now interpret these bytes as Latin-1 characters
        # and get the resulting text
        return utf8_bytes.decode('latin-1')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def decode_utf8_bytes_as_latin1_then_utf8(text):
    """
    Alternative: The text we're seeing is actually UTF-8 bytes
    that were decoded as Latin-1. We need to reverse this.
    
    1. Get UTF-8 bytes of current text
    2. These bytes should be interpreted as UTF-8 directly
    """
    try:
        # The current text is UTF-8, get its bytes
        current_bytes = text.encode('utf-8')
        # These bytes were originally valid UTF-8 for Turkish chars
        # Just return as-is since we're already reading UTF-8
        return text
    except:
        return text


def apply_replacement_map(text):
    """
    Manual replacement of observed mojibake patterns.
    This is the most reliable approach for severe cases.
    """
    # Build a comprehensive mapping
    # Based on the pattern: original char -> mojibake after corruption
    
    # Let's decode the specific patterns we see:
    # From the hex dump: C3 83 C6 92 C3 86 E2 80 99 ... -> should be Ü
    # This is actually: \u00c3 (C3 83) ƒ (C6 92) Æ (C3 86) ' (E2 80 99) -> Ü
    
    # Let me trace through: Ü in UTF-8 is C3 9C
    # Interpreted as Latin-1: Ü
    # Re-encoded to UTF-8: C3 83 C5 93
    # That's for double encoding
    
    # For triple encoding, we get longer sequences
    # C3 83 C6 92 C3 86 E2 80 99 ... is the triple-encoded pattern for Ü
    
    replacements = {
        # Triple-encoded patterns (from analyzing the hex dump)
        # These need to be applied in order from longest to shortest
        
        # For 'Ü' (U+00DC) - observed pattern
        '\u00c3Æ\'\u00e2€\u00c5"': 'Ü',
        
        # For 'ç' (U+00E7) - observed pattern
        '\u00c3Æ\'‡': 'ç',
        
        # For 'ş' (U+015F) - observed pattern  
        '\u00c5Ÿ': 'ş',
        '\u00c5Ÿ': 'ş',
        
        # For 'ğ' (U+011F)
        '\u00c4Ÿ': 'ğ',
        '\u00c4Ÿ': 'ğ',
        
        # For 'ı' (U+0131)
        'ı': 'ı',
        'ı': 'ı',
        
        # For 'ö' (U+00F6)
        'ö': 'ö',
        'ö': 'ö',
        
        # For 'ü' (U+00FC)
        'ü': 'ü',
        'ü': 'ü',
        
        # For 'Ç' (U+00C7)
        'Ç': 'Ç',
        'Ç': 'Ç',
        
        # For 'Ğ' (U+011E)
        '\u00c4ž': 'Ğ',
        '\u00c4ž': 'Ğ',
        
        # For 'İ' (U+0130)
        'İ': 'İ',
        'İ': 'İ',
        
        # For 'Ö' (U+00D6)
        'Ö': 'Ö',
        'Ö': 'Ö',
        
        # For 'Ş' (U+015E)
        '\u00c5ž': 'Ş',
        '\u00c5ž': 'Ş',
        
        # For 'Ü' (U+00DC)
        'Ü': 'Ü',
        'Ü': 'Ü',
        
        # Cleanup patterns
        '\u00c3Æ\'': '',  # Remove stray patterns
        '': '',  # Remove spurious 
    }
    
    # Sort by length (longest first) to avoid partial replacements
    for old, new in sorted(replacements.items(), key=lambda x: len(x[0]), reverse=True):
        text = text.replace(old, new)
    
    return text


def fix_file(filepath):
    """Fix encoding in a file."""
    path = Path(filepath)
    print(f"Processing: {path}")
    
    # Read original
    with open(path, 'r', encoding='utf-8') as f:
        original = f.read()
    
    # Try multiple approaches
    fixed = original
    
    # Approach 1: Direct encode latin1, decode utf-8
    # This works if the file shows UTF-8 bytes that were interpreted as chars
    try:
        # Get bytes and decode differently
        test = original.encode('utf-8').decode('latin-1')
        # Now these chars when encoded to UTF-8 should give us Turkish chars
        test2 = test.encode('latin-1').decode('utf-8', errors='ignore')
        if any(c in test2 for c in 'çğışöüÇĞİŞÖÜ'):
            fixed = test2
    except:
        pass
    
    # Approach 2: Manual replacements
    if fixed == original:
        fixed = apply_replacement_map(original)
    
    if fixed != original:
        # Create backup
        backup_path = path.with_suffix(path.suffix + '.bak')
        shutil.copy2(path, backup_path)
        
        # Write fixed content
        with open(path, 'w', encoding='utf-8') as f:
            f.write(fixed)
        
        # Remove backup
        backup_path.unlink()
        
        print("  Fixed!")
        return True
    
    print("  No changes needed")
    return False


def main():
    files = [
        'backend/app/tools/super_agent.py',
        'backend/app/tools/registry.py',
        'backend/app/tools/domain/file_ops.py',
    ]
    
    for filepath in files:
        fix_file(filepath)


if __name__ == '__main__':
    main()
