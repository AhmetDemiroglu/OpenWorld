#!/usr/bin/env python3
"""
Find all unique corrupted patterns and map them to Turkish characters.
"""

with open('backend/app/tools/registry.py', 'rb') as f:
    data = f.read()

# Find all byte sequences that start with C3 83
patterns = {}
pattern = b'\xc3\x83'
idx = 0

while True:
    idx = data.find(pattern, idx)
    if idx == -1:
        break
    
    # Get the next 15 bytes (typical pattern length)
    end = min(len(data), idx + 15)
    seq = data[idx:end]
    
    # Use the hex as key
    hex_key = seq.hex()
    
    # Get context (ASCII only for readability)
    ctx_start = max(0, idx - 30)
    ctx_end = min(len(data), idx + 30)
    context = data[ctx_start:ctx_end]
    
    if hex_key not in patterns:
        patterns[hex_key] = {
            'count': 0,
            'contexts': []
        }
    
    patterns[hex_key]['count'] += 1
    if len(patterns[hex_key]['contexts']) < 2:
        # Store only ASCII characters from context
        ascii_ctx = ''.join(chr(b) if 32 <= b < 127 else '?' for b in context)
        patterns[hex_key]['contexts'].append(ascii_ctx)
    
    idx += 1

# Sort by count
sorted_patterns = sorted(patterns.items(), key=lambda x: x[1]['count'], reverse=True)

print(f"Found {len(patterns)} unique patterns starting with C3 83")
print(f"\nTop 20 patterns by frequency:")
print("=" * 80)

for i, (hex_key, info) in enumerate(sorted_patterns[:20], 1):
    print(f"{i}. Pattern: {hex_key}")
    print(f"   Count: {info['count']}")
    print(f"   Byte length: {len(hex_key)//2}")
    for ctx in info['contexts']:
        print(f"   Context: {ctx}")
    print()

# Save to file
with open('encoding_patterns.txt', 'w', encoding='utf-8') as f:
    f.write("Encoding Pattern Analysis\n")
    f.write("=" * 80 + "\n\n")
    for hex_key, info in sorted_patterns:
        f.write(f"Pattern: {hex_key}\n")
        f.write(f"Count: {info['count']}\n")
        f.write(f"Byte length: {len(hex_key)//2}\n")
        for ctx in info['contexts']:
            f.write(f"Context: {ctx}\n")
        f.write("\n")

print("Full analysis saved to encoding_patterns.txt")
