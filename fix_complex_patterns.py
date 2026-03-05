#!/usr/bin/env python3
"""
Fix complex multi-byte mojibake patterns.
"""

import shutil
from pathlib import Path


def fix_file(filepath):
    """Fix complex patterns by direct byte replacement."""
    path = Path(filepath)
    print(f"Processing: {path}")
    
    with open(path, 'rb') as f:
        data = f.read()
    
    original = data
    
    # Turkish UTF-8 bytes
    T = {
        'ç': b'\xc3\xa7', 'ğ': b'\xc4\x9f', 'ı': b'\xc4\xb1', 'ö': b'\xc3\xb6',
        'ş': b'\xc5\x9f', 'ü': b'\xc3\xbc',
        'Ç': b'\xc3\x87', 'Ğ': b'\xc4\x9e', 'İ': b'\xc4\xb0', 'Ö': b'\xc3\x96',
        'Ş': b'\xc5\x9e', 'Ü': b'\xc3\x9c',
    }
    
    # Complex patterns identified from hex analysis
    # These are the exact byte sequences that appear in the file
    replacements = [
        # Pattern for "Ü" in "SÜPER" context - the most recognizable one
        (b'\xc3\x83\xc6\x92\xc3\x86\xe2\x80\x99\xc3\x83\xe2\x80\xa0"\xe2\x84\xa2\xc3\x83\xc6\x92"\xc2\xa6\xc3\x83\xc2\xa2\xc3\xa2\xe2\x80\x9a\xc2\xac\xc3\x85\xe2\x80\x9c', T['Ü']),
        
        # Pattern for "ç" in "ARAÇLARI" context
        (b'\xc3\x83\xc6\x92\xc3\x86\xe2\x80\x99\xc3\x83\xe2\x80\xa0"\xe2\x84\xa2\xc3\x83\xc6\x92\xc2\xa2\xc3\x83\xc2\xa2"\xc5\xa1\xc2\xac\xc3\x83\xe2\x80\x9a\xc2\xa1', T['ç']),
        
        # Pattern for "İ" in various contexts
        (b'\xc3\x83\xc6\x92\xc3\x86\xe2\x80\x99\xc3\x83\xc2\xa2\xc3\xa2\xe2\x80\x9a\xc2\xac\xc2\x9e\xc3\x83', T['İ']),
        
        # Pattern for "Ş" 
        (b'\xc3\x83\xc2\xa2\xc3\xa2\xe2\x80\x9a\xc2\xac\xc2\x9e\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb0', T['Ş']),
        
        # Additional patterns discovered
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb0', T['ş']),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb1', T['ı']),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb8', T['ş']),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xa7', T['ş']),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xa6', T['ç']),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc', T['ş']),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb6', T['ş']),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb1', T['ı']),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb672', T['ş'] + b'r'),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb67220', T['ş'] + b'r '),
        
        # Clean up spurious bytes that may appear after replacement
        (b'\xc4\xb0', T['İ']),  # İ in UTF-8
        (b'\xc4\xb1', T['ı']),  # ı in UTF-8
        (b'\xc5\x9f', T['ş']),  # ş in UTF-8
        (b'\xc5\x9e', T['Ş']),  # Ş in UTF-8
    ]
    
    # Sort by length (longest first)
    replacements.sort(key=lambda x: len(x[0]), reverse=True)
    
    for pattern, replacement in replacements:
        if pattern in data:
            count = data.count(pattern)
            data = data.replace(pattern, replacement)
            print(f"  Replaced {count} x {pattern[:8].hex()}... -> {replacement.hex()}")
    
    if data == original:
        print("  No changes")
        return False
    
    # Verify the result is valid UTF-8
    try:
        data.decode('utf-8')
    except UnicodeDecodeError as e:
        print(f"  ERROR: Result is not valid UTF-8: {e}")
        return False
    
    backup_path = path.with_suffix(path.suffix + '.bak')
    shutil.copy2(path, backup_path)
    with open(path, 'wb') as f:
        f.write(data)
    backup_path.unlink()
    
    remaining = data.count(b'\xc3\x83')  # Corruption indicator
    print(f"  Fixed! Remaining corruption indicators: {remaining}")
    return True


def main():
    files = [
        'backend/app/tools/registry.py',
        'backend/app/tools/domain/file_ops.py',
    ]
    
    for filepath in files:
        fix_file(filepath)
        print()


if __name__ == '__main__':
    main()
