#!/usr/bin/env python3
"""
Find all unique byte patterns that appear to be corrupted Turkish characters.
"""

with open('backend/app/tools/registry.py', 'rb') as f:
    data = f.read()

# Find all occurrences of the common pattern C3 83...
pattern = b'\xc3\x83'
positions = []
idx = 0
while True:
    idx = data.find(pattern, idx)
    if idx == -1:
        break
    positions.append(idx)
    idx += 1

print(f"Found {len(positions)} occurrences of C3 83")

# Extract the patterns with context
print("\nFirst 20 occurrences with context:")
for i, pos in enumerate(positions[:20]):
    # Get 20 bytes of context
    start = max(0, pos - 5)
    end = min(len(data), pos + 20)
    context = data[start:end]
    
    # Show as hex and as CP1252
    hex_str = context.hex()
    cp1252_str = context.decode('cp1252', errors='replace')
    
    print(f"{i+1}. Pos {pos}: {hex_str}")
    print(f"   CP1252: {cp1252_str!r}")
    print()

# Look for unique patterns following C3 83
print("Unique patterns following C3 83 (first 4 bytes):")
patterns = set()
for pos in positions:
    end = min(len(data), pos + 10)
    pattern_bytes = data[pos:end]
    patterns.add(pattern_bytes.hex())

for p in sorted(patterns)[:20]:
    print(f"  {p}")
