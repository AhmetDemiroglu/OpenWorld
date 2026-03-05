#!/usr/bin/env python3
"""
Fix mojibake encoding issues in Turkish text.
Multi-level UTF-8 → Latin-1 → UTF-8 corruption.
"""

import shutil
from pathlib import Path


def decode_mojibake(text):
    """
    Try to fix mojibake by iteratively encoding as latin1 and decoding as utf-8.
    This handles multiple levels of corruption.
    """
    result = text
    for attempt in range(5):  # Try up to 5 levels of decoding
        try:
            # Encode as latin1 (which accepts any byte 0-255)
            # then decode as utf-8
            new_result = result.encode('latin1').decode('utf-8')
            if new_result == result:
                # No more changes
                break
            result = new_result
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Can't decode further
            break
    return result


def fix_file(filepath):
    """Fix encoding in a file."""
    path = Path(filepath)
    print(f"Processing: {path}")
    
    # Read original
    with open(path, 'r', encoding='utf-8') as f:
        original = f.read()
    
    # Apply fix
    fixed = decode_mojibake(original)
    
    if fixed == original:
        print("  No changes needed")
        return False
    
    # Create backup
    backup_path = path.with_suffix(path.suffix + '.bak')
    shutil.copy2(path, backup_path)
    
    # Write fixed content
    with open(path, 'w', encoding='utf-8') as f:
        f.write(fixed)
    
    # Remove backup if successful
    backup_path.unlink()
    
    print("  Fixed!")
    return True


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
