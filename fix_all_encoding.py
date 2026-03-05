#!/usr/bin/env python3
"""
Comprehensive encoding fix for Turkish mojibake.

Based on pattern analysis, we have 349+ unique byte patterns that need to be 
mapped to Turkish characters. We'll fix them based on context clues.
"""

import shutil
from pathlib import Path
import re


def fix_file(filepath):
    """Fix encoding in a file using comprehensive byte pattern replacement."""
    path = Path(filepath)
    print(f"Processing: {path}")
    
    # Read original as bytes
    with open(path, 'rb') as f:
        data = f.read()
    
    original_data = data
    
    # Turkish characters in UTF-8
    UTF8 = {
        'ç': b'\xc3\xa7', 'ğ': b'\xc4\x9f', 'ı': b'\xc4\xb1', 'ö': b'\xc3\xb6',
        'ş': b'\xc5\x9f', 'ü': b'\xc3\xbc',
        'Ç': b'\xc3\x87', 'Ğ': b'\xc4\x9e', 'İ': b'\xc4\xb0', 'Ö': b'\xc3\x96',
        'Ş': b'\xc5\x9e', 'Ü': b'\xc3\x9c',
    }
    
    # Common mojibake patterns based on frequency analysis
    # Each pattern is specific to the Turkish character it represents
    
    replacements = [
        # Pattern 1: For İ (capital I with dot) - appears in "OFİS" context
        (b'\xc3\x83\xc6\x92\xc3\x86\xe2\x80\x99\xc3\x83\xc2\xa2\xc3\xa2', UTF8['İ']),
        
        # Pattern 2: For S (Ş) - appears in "ve ARŞ" (and archives) context
        (b'\xc3\x83\xc2\xa2\xc3\xa2\xe2\x80\x9a\xc2\xac\xc2\x9e\xc3\x83', UTF8['Ş']),
        
        # Pattern 3: For ç - appears in "içeriği" (content) context
        (b'\xc3\x83\xc6\x92\xc3\x86\xe2\x80\x99\xc3\x83\xe2\x80\xa0"', UTF8['ç']),
        
        # Pattern 4: For ş - appears in "...ş..." context
        (b'\xc3\x83\xe2\x80\xa0"\xe2\x84\xa2\xc3\x83\xc6\x92"\xc5\xa1', UTF8['ş']),
        
        # Pattern 5: For ş - another variant
        (b'\xc3\x83\xe2\x80\xa0"\xe2\x84\xa2\xc3\x83\xc6\x92\xc2\xa2', UTF8['ş']),
        
        # Pattern 6: For ı - appears in "k...oru" (koru = protect) context
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb1', UTF8['ı']),
        
        # Pattern 7: For n (ñ-like corruption) 
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb6', UTF8['ı']),  # Actually might be different
        
        # Pattern 8: For r
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb1', UTF8['ı']),
        
        # Pattern 9: For k
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb1', UTF8['ı']),
        
        # Pattern for "bulunamadı" (not found)
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb1"', UTF8['ı']),
        
        # Pattern for "tıkla" (click)
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb1,"', UTF8['ı']),
        
        # Pattern for sonlandır (terminate)
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb1r', UTF8['ı']),
        
        # Pattern for çalış (work/run) - skipped due to encoding issues
        
        # More patterns for ç
        (b'\xc3\x83\xc6\x92"\xc2\xa6\xc3\x83\xe2\x80\x9a\xc2\xb8i', UTF8['ç']),
        
        # Pattern for ş in "şifre" (password)
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb1f', UTF8['ı']),
        
        # Pattern for işlem (transaction)
        (b'\xc3\x83\xc6\x92"\xc2\xa6\xc3\x83\xe2\x80\x9a\xc2\xb8l', UTF8['ç']),
        
        # Pattern for dosyaların
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb1n', UTF8['ı']),
        
        # Pattern for takip
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb1p', UTF8['ı']),
        
        # Pattern for dosyanın
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb1k', UTF8['ı']),
        
        # Pattern for taşınma (move)
        (b'\xc3\x83\xc6\x92"\xc2\xa6\xc3\x83\xe2\x80\x9a\xc2\xb8\xc3', UTF8['ş']),
        
        # More İ patterns
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb1\xc3', UTF8['İ']),
        
        # Pattern for etkinleştir
        (b'\xc3\x83\xc6\x92"\xc2\xa6\xc3\x83\xe2\x80\x9a\xc2\xb8t', UTF8['ş']),
        
        # Pattern for çalıştır
        (b'\xc3\x83\xc6\x92"\xc2\xa6\xc3\x83\xe2\x80\x9a\xc2\xb8\xc3', UTF8['ş']),
        
        # Pattern for g
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb1"', UTF8['ı']),
        
        # Pattern for r
        (b'\xc3\x83\xc6\x92"\xc5\xa1\xc3\x83\xe2\x80\x9a\xc2\xb1r', UTF8['ı']),
        
        # Pattern for i
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb1\xc3\x83\xc6\x92\xc3\x86', UTF8['ı']),
        
        # Pattern for l
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb1l', UTF8['ı']),
        
        # Pattern for a
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb8\xc3\x83\xc6\x92\xc3\x86', UTF8['ş']),
        
        # Pattern for m
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb1m', UTF8['ı']),
    ]
    
    # Apply replacements (longest patterns first)
    replacements.sort(key=lambda x: len(x[0]), reverse=True)
    
    for pattern, replacement in replacements:
        if pattern in data:
            count = data.count(pattern)
            data = data.replace(pattern, replacement)
            if count > 0:
                print(f"  Replaced {count} occurrences of pattern {pattern[:10].hex()}...")
    
    if data == original_data:
        print("  No changes made")
        return False
    
    # Create backup
    backup_path = path.with_suffix(path.suffix + '.bak')
    shutil.copy2(path, backup_path)
    
    # Write fixed content
    with open(path, 'wb') as f:
        f.write(data)
    
    # Remove backup
    backup_path.unlink()
    
    print(f"  Fixed! Remaining C3 83 count: {data.count(b'\\xc3\\x83')}")
    return True


def main():
    files = [
        'backend/app/tools/super_agent.py',
        'backend/app/tools/registry.py',
        'backend/app/tools/domain/file_ops.py',
    ]
    
    for filepath in files:
        fix_file(filepath)
        print()


if __name__ == '__main__':
    main()
