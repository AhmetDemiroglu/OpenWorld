#!/usr/bin/env python3
"""
Correct encoding fix for Turkish mojibake.

The corruption pattern is:
- Original UTF-8 text was interpreted as single-byte encoding (CP1252/Latin-1)
- Then re-encoded to UTF-8 multiple times
- The result is valid UTF-8 but with wrong characters (mojibake)

Fix approach:
- Replace known mojibake character sequences with correct Turkish characters
- Only replace complete, valid patterns
"""

import shutil
from pathlib import Path


def fix_file(filepath):
    """Fix encoding using string-level replacement."""
    path = Path(filepath)
    print(f"Processing: {path}")
    
    # Read as UTF-8 (the file is valid UTF-8, just with wrong characters)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # Mojibake to Turkish character mappings
    # These are the observed patterns in the files
    
    replacements = [
        # Most common patterns
        ('Ã§', 'ç'),  # ç - most common Turkish char
        ('Ã¶', 'ö'),  # ö
        ('Ã¼', 'ü'),  # ü
        ('ÄŸ', 'ğ'),  # ğ
        ('Ä±', 'ı'),  # ı (dotless i)
        ('ÅŸ', 'ş'),  # ş
        ('Ã‡', 'Ç'),  # Ç
        ('Äž', 'Ğ'),  # Ğ
        ('Ä°', 'İ'),  # İ (dotted I)
        ('Ã–', 'Ö'),  # Ö
        ('Åž', 'Ş'),  # Ş
        ('Ãœ', 'Ü'),  # Ü
        
        # Double-encoded patterns
        ('ÃƒÂ§', 'ç'),
        ('ÃƒÂ¶', 'ö'),
        ('ÃƒÂ¼', 'ü'),
        ('Ã„Å¸', 'ğ'),
        ('Ã„Â±', 'ı'),
        ('Ã…Å¸', 'ş'),
        ('Ãƒâ€¡', 'Ç'),
        ('Ã„Å¾', 'Ğ'),
        ('Ã„Â°', 'İ'),
        ('Ãƒâ€“', 'Ö'),
        ('Ã…Å¾', 'Ş'),
        ('ÃƒÅ“', 'Ü'),
        
        # Quote marks and punctuation
        ('â€œ', '"'),  # left double quote
        ('â€', '"'),   # right double quote
        ('â€™', "'"),  # apostrophe
        ('â€¦', '…'),  # ellipsis
        ('â€“', '–'),  # en dash
        ('â€”', '—'),  # em dash
        
        # Cleanup
        ('Â', ''),  # spurious Â
    ]
    
    # Sort by length (longest first) to avoid partial replacements
    replacements.sort(key=lambda x: len(x[0]), reverse=True)
    
    for old, new in replacements:
        if old in content:
            count = content.count(old)
            content = content.replace(old, new)
            if count > 0:
                print(f"  Replaced {count} x '{old}' -> '{new}'")
    
    if content == original:
        print("  No changes")
        return False
    
    # Create backup
    backup_path = path.with_suffix(path.suffix + '.bak')
    shutil.copy2(path, backup_path)
    
    # Write fixed content
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    
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
        print()


if __name__ == '__main__':
    main()
