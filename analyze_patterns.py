#!/usr/bin/env python3
"""
Analyze the specific byte patterns for Turkish character replacement.
"""

with open('backend/app/tools/registry.py', 'rb') as f:
    data = f.read()

# Find the section with PER AJAN ARA...LARI
idx = data.find(b'PER AJAN')
if idx > 0:
    # Get the corrupted bytes before "PER"
    # The pattern ends right before 'P' (0x50)
    start = idx - 44  # Approximate based on hex analysis
    section = data[start:idx]
    print(f"Bytes before 'PER': {section.hex()}")
    print(f"Length: {len(section)}")
    
    # Decode as CP1252
    as_cp1252 = section.decode('cp1252', errors='replace')
    print(f"As CP1252: {as_cp1252!r}")
    
    # This should be "SÜPER" where Ü is corrupted
    # The expected output is: "S" + corruption + "PER"
    
print()
print("=" * 60)

# Now let's find the pattern for ç in ARAçLARI
# Looking for bytes between "ARA" and "LARI"
idx2 = data.find(b'ARA')
if idx2 > 0:
    section2 = data[idx2+3:idx2+3+40]  # After "ARA"
    print(f"Bytes after 'ARA': {section2.hex()}")
    as_cp1252_2 = section2.decode('cp1252', errors='replace')
    print(f"As CP1252: {as_cp1252_2!r}")

print()
print("=" * 60)
print("Creating byte pattern mappings...")

# Based on the hex dump, let's identify the exact byte patterns
# Line 26 shows: S(c3 83 c6 92 c3 86 e2 80 99 ...)PER
# The part in parentheses should be "Ü"

# Let me extract the exact pattern for the first corrupted char
# Looking at the raw bytes before 'P' (0x50)
idx_p = data.find(b'PER')
if idx_p > 0:
    # Go back from PER to find where the corruption starts
    # PER starts with 'P' = 0x50
    # Before that we have the corrupted Turkish char
    corruption_start = idx_p - 44  # Approximate
    corruption = data[corruption_start:idx_p]
    print(f"Corruption before 'PER': {corruption.hex()}")
    print(f"As CP1252: {corruption.decode('cp1252', errors='replace')!r}")

# Let me try a different approach - search for the exact byte patterns
# and replace them directly

# From hex: C3 83 C6 92 appears multiple times
pattern_c383c692 = b'\xc3\x83\xc6\x92'
count = data.count(pattern_c383c692)
print(f"\nPattern C3 83 C6 92 appears {count} times")

# This pattern in CP1252 is: Ãƒ
as_chars = pattern_c383c692.decode('cp1252')
print(f"As CP1252 chars: {as_chars!r}")

# The question is: what should this be replaced with?
# In the context "S...PER" it should be "Ü"
# In the context "ARA...LARI" it should be "ç"

# So we need to look at the full context and replace accordingly
