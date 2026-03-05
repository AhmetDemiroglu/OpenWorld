#!/usr/bin/env python3
"""
Fix mojibake encoding issues in Turkish text.
"""

import shutil
from pathlib import Path


def apply_manual_fixes(text):
    """Apply manual character replacements based on observed patterns."""
    
    fixes = {
        # Double-encoded patterns
        'Ã„Â±': 'ı',
        'Ã„Å¸': 'ğ', 
        'Ã…Å¸': 'ş',
        'ÃƒÂ§': 'ç',
        'ÃƒÂ¶': 'ö',
        'ÃƒÂ¼': 'ü',
        'Ãƒâ€¡': 'Ç',
        'Ã„Å¾': 'Ğ',
        'Ã„Â°': 'İ',
        'Ãƒâ€“': 'Ö',
        'Ã…Å¾': 'Ş',
        'ÃƒÅ“': 'Ü',
        
        # Single-encoded patterns
        'Ã§': 'ç',
        'Ã¶': 'ö',
        'Ã¼': 'ü',
        'Ã‡': 'Ç',
        'ÄŸ': 'ğ',
        'Ä±': 'ı',
        'Ä°': 'İ',
        'ÅŸ': 'ş',
        'Åž': 'Ş',
        'Ã–': 'Ö',
        'Ãœ': 'Ü',
        'Äž': 'Ğ',
        'â€œ': '"',
        'â€': '"',
        'â€™': "'",
        'â€¦': '…',
        'â€“': '–',
        'â€”': '—',
        'Â': '',  # Remove spurious Â characters
    }
    
    for old, new in fixes.items():
        text = text.replace(old, new)
    
    return text


def fix_file(filepath):
    """Fix encoding in a file."""
    path = Path(filepath)
    print(f"Processing: {path}")
    
    # Read original
    with open(path, 'r', encoding='utf-8') as f:
        original = f.read()
    
    # Apply fixes
    fixed = apply_manual_fixes(original)
    
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
