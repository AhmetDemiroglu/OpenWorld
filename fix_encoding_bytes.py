#!/usr/bin/env python3
"""
Fix encoding by direct byte replacement.

Based on analysis, the file contains UTF-8 encoded mojibake.
We need to replace specific byte patterns with the correct Turkish character bytes.
"""

import shutil
from pathlib import Path


def fix_file(filepath):
    """Fix encoding in a file using byte-level replacements."""
    path = Path(filepath)
    print(f"Processing: {path}")
    
    # Read original as bytes
    with open(path, 'rb') as f:
        data = f.read()
    
    original_data = data
    
    # Turkish characters in UTF-8
    turkish_utf8 = {
        'ç': b'\xc3\xa7',
        'ğ': b'\xc4\x9f',
        'ı': b'\xc4\xb1',
        'ö': b'\xc3\xb6',
        'ş': b'\xc5\x9f',
        'ü': b'\xc3\xbc',
        'Ç': b'\xc3\x87',
        'Ğ': b'\xc4\x9e',
        'İ': b'\xc4\xb0',
        'Ö': b'\xc3\x96',
        'Ş': b'\xc5\x9e',
        'Ü': b'\xc3\x9c',
    }
    
    # Based on the hex analysis, the corrupted patterns are complex multi-byte sequences
    # Let's create a mapping from the observed byte patterns to correct Turkish chars
    
    # From analysis:
    # Pattern for Ü in "SÜPER" context: C3 83 C6 92 C3 86 E2 80 99 C3 83 E2 80 A0 22 E2 84 A2 C3 83 C6 92 22 C2 A6 C3 83 C2 A2 C3 A2 E2 80 9A C2 AC C3 85 E2 80 9C
    # This is a very long pattern!
    
    # The key insight: the pattern varies by context, so we need to handle each case
    # Let's look for the most common patterns and replace them
    
    # Common mojibake to Turkish char mappings based on context
    replacements = []
    
    # Pattern 1: "S...PER" -> "SÜPER"
    # The full pattern before PER is quite long
    pattern_s_uper = b'\xc3\x83\xc6\x92\xc3\x86\xe2\x80\x99\xc3\x83\xe2\x80\xa0"\xe2\x84\xa2\xc3\x83\xc6\x92"\xc2\xa6\xc3\x83\xc2\xa2\xc3\xa2\xe2\x80\x9a\xc2\xac\xc3\x85\xe2\x80\x9c'
    if pattern_s_uper in data:
        print(f"  Found pattern_s_uper ({len(pattern_s_uper)} bytes)")
        data = data.replace(pattern_s_uper, b'\xc3\x9c')  # Ü in UTF-8
    
    # Pattern 2: "ARA...LARI" -> "ARAÇLARI"
    pattern_ara_c = b'\xc3\x83\xc6\x92\xc3\x86\xe2\x80\x99\xc3\x83\xe2\x80\xa0"\xe2\x84\xa2\xc3\x83\xc6\x92\xc2\xa2\xc3\x83\xc2\xa2"\xc5\xa1\xc2\xac\xc3\x83\xe2\x80\x9a\xc2\xa1'
    if pattern_ara_c in data:
        print(f"  Found pattern_ara_c ({len(pattern_ara_c)} bytes)")
        data = data.replace(pattern_ara_c, b'\xc3\xa7')  # ç in UTF-8
    
    if data == original_data:
        print("  No patterns matched")
        return False
    
    # Create backup
    backup_path = path.with_suffix(path.suffix + '.bak')
    shutil.copy2(path, backup_path)
    
    # Write fixed content
    with open(path, 'wb') as f:
        f.write(data)
    
    # Remove backup
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
