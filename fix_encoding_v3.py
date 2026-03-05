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
        'ı': 'ı',
        '\u00c4Ÿ': 'ğ', 
        '\u00c5Ÿ': 'ş',
        'ç': 'ç',
        'ö': 'ö',
        'ü': 'ü',
        'Ç': 'Ç',
        '\u00c4ž': 'Ğ',
        'İ': 'İ',
        'Ö': 'Ö',
        '\u00c5ž': 'Ş',
        'Ü': 'Ü',
        
        # Single-encoded patterns
        'ç': 'ç',
        'ö': 'ö',
        'ü': 'ü',
        'Ç': 'Ç',
        '\u00c4Ÿ': 'ğ',
        'ı': 'ı',
        'İ': 'İ',
        '\u00c5Ÿ': 'ş',
        '\u00c5ž': 'Ş',
        'Ö': 'Ö',
        'Ü': 'Ü',
        '\u00c4ž': 'Ğ',
        '"': '"',
        '\u00e2€': '"',
        ''': "'",
        '…': '…',
        '–': '–',
        '—': '—',
        '': '',  # Remove spurious  characters
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
