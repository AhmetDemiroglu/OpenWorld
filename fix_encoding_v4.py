#!/usr/bin/env python3
"""
Fix mojibake by iterative encode/decode.

The corruption pattern is:
UTF-8 bytes → interpreted as CP1252/Latin-1 → saved as UTF-8 (multiple times)
"""

import shutil
from pathlib import Path


def fix_by_iterative_decode(text, encoding='latin-1'):
    """
    Fix mojibake by iteratively:
    1. Encode text as UTF-8 to get bytes
    2. Decode bytes as 'encoding' (latin-1 or cp1252)
    3. Repeat until no change or error
    
    This reverses: original UTF-8 → read as encoding → saved as UTF-8 (multiple times)
    """
    result = text
    for i in range(5):
        try:
            # Encode current result as UTF-8
            utf8_bytes = result.encode('utf-8')
            # Decode as if it were the intermediate encoding
            decoded = utf8_bytes.decode(encoding)
            if decoded == result:
                break
            result = decoded
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
    return result


def fix_file(filepath):
    """Fix encoding in a file."""
    path = Path(filepath)
    print(f"Processing: {path}")
    
    # Read original
    with open(path, 'r', encoding='utf-8') as f:
        original = f.read()
    
    # Try both latin-1 and cp1252
    fixed_latin1 = fix_by_iterative_decode(original, 'latin-1')
    fixed_cp1252 = fix_by_iterative_decode(original, 'cp1252')
    
    # Choose the one that gives us Turkish characters
    turkish_chars = set('çğışöüÇĞİŞÖÜ')
    
    has_turkish_latin1 = bool(set(fixed_latin1) & turkish_chars)
    has_turkish_cp1252 = bool(set(fixed_cp1252) & turkish_chars)
    
    if has_turkish_latin1 and not has_turkish_cp1252:
        fixed = fixed_latin1
    elif has_turkish_cp1252 and not has_turkish_latin1:
        fixed = fixed_cp1252
    elif has_turkish_latin1 and has_turkish_cp1252:
        # Both work, choose the shorter one (less corruption)
        fixed = fixed_latin1 if len(fixed_latin1) <= len(fixed_cp1252) else fixed_cp1252
    else:
        # Neither gave Turkish chars, check if original is better
        fixed = original
    
    if fixed != original:
        # Create backup
        backup_path = path.with_suffix(path.suffix + '.bak')
        shutil.copy2(path, backup_path)
        
        # Write fixed content
        with open(path, 'w', encoding='utf-8') as f:
            f.write(fixed)
        
        # Remove backup
        backup_path.unlink()
        
        print(f"  Fixed! (latin-1: {has_turkish_latin1}, cp1252: {has_turkish_cp1252})")
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
