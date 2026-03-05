#!/usr/bin/env python3
"""
Fix remaining encoding issues.
"""

import shutil
from pathlib import Path


def fix_file(filepath):
    """Fix remaining encoding issues."""
    path = Path(filepath)
    print(f"Processing: {path}")
    
    with open(path, 'rb') as f:
        data = f.read()
    
    original_data = data
    
    UTF8 = {
        'ç': b'\xc3\xa7', 'ğ': b'\xc4\x9f', 'ı': b'\xc4\xb1', 'ö': b'\xc3\xb6',
        'ş': b'\xc5\x9f', 'ü': b'\xc3\xbc',
        'Ç': b'\xc3\x87', 'Ğ': b'\xc4\x9e', 'İ': b'\xc4\xb0', 'Ö': b'\xc3\x96',
        'Ş': b'\xc5\x9e', 'Ü': b'\xc3\x9c',
    }
    
    # Additional patterns found from analysis
    replacements = [
        # From remaining patterns
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2', UTF8['ı']),
        (b'\xc3\x83\xc6\x92"\xc2\xa6\xc3\x83\xe2', UTF8['ç']),
        (b'\xc3\x83\xc6\x92\xc3\x86\xe2\x80\x99\xc5', UTF8['İ']),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbcm', UTF8['ş'] + b'm'),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb0', UTF8['ş']),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb8', UTF8['ş']),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb0', UTF8['ş']),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb020', UTF8['ş'] + b' '),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb053', UTF8['ş'] + b'S'),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb856', UTF8['ş'] + b'V'),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb86d', UTF8['ş'] + b'i'),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb865', UTF8['ş'] + b'e'),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb053', UTF8['ş'] + b'S'),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb04d', UTF8['ş'] + b'M'),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb00d', UTF8['ş'] + b'\r'),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xa7', UTF8['ş'] + b'g'),
        (b'\xc3\x83\xe2\x80\x9a\xc2\xa765', UTF8['ş'] + b'e'),
        (b'\xc3\x83\xe2\x80\x9a\xc29e', UTF8['ş']),
        (b'\xc3\x83\xe2\x80\x9a\xc29e20', UTF8['ş'] + b' '),
        (b'\xc3\x83\xe2\x80\x9a\xc29e44', UTF8['ş'] + b'D'),
        (b'\xc3\x83\xe2\x80\x9a\xc29e4d', UTF8['ş'] + b'M'),
    ]
    
    # Sort by length (longest first)
    replacements.sort(key=lambda x: len(x[0]), reverse=True)
    
    for pattern, replacement in replacements:
        if pattern in data:
            count = data.count(pattern)
            data = data.replace(pattern, replacement)
            if count > 0:
                print(f"  Replaced {count} x {pattern[:8].hex()}...")
    
    if data == original_data:
        print("  No changes")
        return False
    
    backup_path = path.with_suffix(path.suffix + '.bak')
    shutil.copy2(path, backup_path)
    with open(path, 'wb') as f:
        f.write(data)
    backup_path.unlink()
    
    remaining = data.count(b'\xc3\x83')
    print(f"  Fixed! Remaining C3 83: {remaining}")
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
