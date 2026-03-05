#!/usr/bin/env python3
"""
Final comprehensive encoding fix.
Based on context analysis, manually map corrupted patterns to Turkish characters.
"""

import shutil
from pathlib import Path


def fix_file(filepath):
    """Fix remaining encoding issues comprehensively."""
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
    
    # Context-based replacements for remaining patterns
    # Pattern structure analysis:
    # C3 83 E2 80 9A C2 XX ... appears to represent ş/ç with following char
    
    replacements = [
        # İ patterns - appears in "OFİS" (office), "ARŞİV" (archive)
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb672\xc4\xb0', UTF8['İ'] + b'r'),  # İr
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc6e74\xc4\xb0', UTF8['İ'] + b'nt'),  # İnt
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc72\xc4\xb0', UTF8['İ'] + b'r'),  # İr
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc73\xc4\xb0', UTF8['İ'] + b's'),  # İs
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc7265736920', UTF8['İ'] + b'resi '),  # İresi
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc20646f7379', UTF8['ş'] + b' dosy'),  # ş dosy
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc63\xc4\xb0', UTF8['İ'] + b'c'),  # İc
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb67220796f6c', UTF8['ş'] + b'r yol'),  # şr yol
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc7374\xc4\xb0', UTF8['İ'] + b'st'),  # İst
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc20616c2e20', UTF8['ş'] + b' al. '),  # ş al.
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb66c6765205b', UTF8['ş'] + b'lge ['),  # şlge [
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb6737465722e', UTF8['ş'] + b'ster.'),  # şter.
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb66e65206765', UTF8['ş'] + b'ne ge'),  # şne ge
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc\xc4\xb0', UTF8['İ']),  # İ
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb672227d2c0d', UTF8['ş'] + b'r"},\r'),  # şr"},
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb672656c6929', UTF8['ş'] + b'reli)'),  # şreli)
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc7a6572696e', UTF8['ş'] + b'zerin'),  # şzerin
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb6726e3a202e', UTF8['ş'] + b'rn: .'),  # şrn: .
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc6c\xc4\xb0', UTF8['İ'] + b'l'),  # İl
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc7a6c65722c', UTF8['ş'] + b'zler,'),  # şzler,
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb67265762065', UTF8['ş'] + b'rev e'),  # şrev e
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb67265766c65', UTF8['ş'] + b'revle'),  # şrevle
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb67265762074', UTF8['ş'] + b'rev t'),  # şrev t
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc20656b7261', UTF8['ş'] + b' ekra'),  # ş ekra
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc6b6c656e6d', UTF8['ş'] + b'klenm'),  # şklenm
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc2061726120', UTF8['ş'] + b' ara '),  # ş ara
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc76656e6920', UTF8['ş'] + b'veni '),  # şveni
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc6b6c652d62', UTF8['ş'] + b'kle-b'),  # şkle-b
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc6b6c656d65', UTF8['ş'] + b'klem'),  # şklem
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc7265736922', UTF8['ş'] + b'resi"'),  # şresi"
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc6e\xc4\xb0', UTF8['İ'] + b'n'),  # İn
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc2067\xc4\xb0', UTF8['ş'] + b' g'),  # ş g
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc76656e6c69', UTF8['ş'] + b'venli'),  # şvenli
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc2068617266', UTF8['ş'] + b' harf'),  # ş harf
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc6c742e222c', UTF8['ş'] + b'lt.",'),  # şlt.",
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc6e64656e20', UTF8['ş'] + b'nden '),  # şnden
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb672652062\xc4', UTF8['ş'] + b're b'),  # şre b
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb66c2e222c0d', UTF8['ş'] + b'l.",\r'),  # şl.",
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb66e656b6922', UTF8['ş'] + b'neki"'),  # şneki"
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb6720d0a2020', UTF8['ş'] + b'r\r\n  '),  # şr\r\n
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc2056532043', UTF8['ş'] + b' VS C'),  # ş VS C
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc20446f7379', UTF8['ş'] + b' Dosy'),  # ş Dosy
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb672206f6c75', UTF8['ş'] + b'r olu'),  # şr olu
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc20796f6c75', UTF8['ş'] + b' yolu'),  # ş yolu
        (b'\xc3\x83\xe2\x80\x9a\xc2\xb672222c2022', UTF8['ş'] + b'r", "'),  # şr", "
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc222c202274', UTF8['ş'] + b'", "t'),  # ş", "t
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc6b6c65222c', UTF8['ş'] + b'kle",'),  # şkle",
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc222c202264', UTF8['ş'] + b'", "d'),  # ş", "d
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc7a696b222c', UTF8['ş'] + b'zik",'),  # şzik",
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc6c65222c0d', UTF8['ş'] + b'le",\r'),  # şle",\r
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc6e64657222', UTF8['ş'] + b'nder"'),  # şnder"
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc6c74222c20', UTF8['ş'] + b'lt", '),  # şlt",
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc726576222c', UTF8['ş'] + b'rev", '),  # şrev",
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc222c202265', UTF8['ş'] + b'", "e'),  # ş", "e
        (b'\xc3\x83\xe2\x80\x9a\xc2\xbc64656e222c', UTF8['ş'] + b'den",'),  # şden",
        
        # Remaining complex patterns
        (b'\xc3\x83\xc6\x92\xc2\xa2\xc3\x83\xc2\xa2"\xc5', UTF8['ş']),
        (b'\xc3\x83\xc2\xa2"\xc5\xa1\xc2\xac\xc3\x83\xc2', UTF8['ş']),
        (b'\xc3\x83\xc2\xa2\xc3\xa2\xe2\x80\x9a\xc2\xac\xc3', UTF8['ş']),
    ]
    
    # Sort by length (longest first) to avoid partial matches
    replacements.sort(key=lambda x: len(x[0]), reverse=True)
    
    for pattern, replacement in replacements:
        if pattern in data:
            count = data.count(pattern)
            data = data.replace(pattern, replacement)
            if count > 0:
                print(f"  Replaced {count} x {pattern[:10].hex()}...")
    
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
    ]
    
    for filepath in files:
        fix_file(filepath)


if __name__ == '__main__':
    main()
