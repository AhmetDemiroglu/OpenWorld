#!/usr/bin/env python3
"""
Analyze the encoding corruption patterns.
"""

# Let's trace through one specific corrupted character
# Looking at line 26, we see patterns like C3 83 C6 92 which shows as '\u00c3'

# First, let's see what '\u00c3' is in UTF-8
char = '\u00c3'
utf8_bytes = char.encode('utf-8')
print(f'"\u00c3" in UTF-8: {utf8_bytes.hex()}')  # Should be C3 83

# And 'ƒ'
char2 = 'ƒ'
utf8_bytes2 = char2.encode('utf-8')
print(f'"ƒ" in UTF-8: {utf8_bytes2.hex()}')  # Should be C6 92

# So '\u00c3' is C3 83 C6 92
# What if we interpret C3 83 C6 92 as Latin-1 bytes?
test_bytes = b'\xc3\x83\xc6\x92'
print(f'Bytes: {test_bytes}')
print(f'As Latin-1: {test_bytes.decode("latin-1")!r}')
print(f'As CP1252: {test_bytes.decode("cp1252")!r}')

# Now what character when encoded to UTF-8 gives us C3 83?
# C3 83 in UTF-8 is the character '\u00c3' followed by a control character
# Let's try the reverse: what is C3 in Latin-1?
c3_byte = b'\xc3'
print(f'C3 as Latin-1: {c3_byte.decode("latin-1")!r}')  # Should be '\u00c3'

# And 83 in Latin-1?
byte_83 = b'\x83'
print(f'83 as Latin-1: {byte_83.decode("latin-1")!r}')  # Control character

# Let me look at the actual file
print("\n--- Analyzing actual file ---")
with open('backend/app/tools/registry.py', 'rb') as f:
    data = f.read()

# Find the corrupted section around line 26
lines = data.split(b'\n')
line26 = lines[25]
print(f"Line 26 raw: {line26}")
print(f"Line 26 hex: {line26.hex()}")

# Let's extract just the first corrupted word
# It starts with 'S' (0x53) then the corruption
# Find where it ends (space after the word)
parts = line26.split(b' ')
first_word = parts[2] if len(parts) > 2 else parts[1]  # "#", "S<corrupted>", ...
print(f"First corrupted word bytes: {first_word}")
print(f"First corrupted word hex: {first_word.hex()}")

# Try to decode this word
# These bytes should form some Turkish word
try:
    as_utf8 = first_word.decode('utf-8')
    print(f"As UTF-8: {as_utf8!r}")
except:
    print("Not valid UTF-8")

try:
    as_latin1 = first_word.decode('latin-1')
    print(f"As Latin-1: {as_latin1!r}")
except:
    print("Not valid Latin-1")

# What we want is: these bytes, when properly decoded, should give us Turkish chars
# The pattern seems to be: byte sequence that is valid UTF-8 for mojibake chars
# We need to figure out what the original bytes were

# Let's think about this differently:
# If the file shows "\u00c3" (C3 83 C6 92 in UTF-8), what could that have been originally?
# C3 83 is the UTF-8 encoding of '\u00c3' (U+00C3)
# C6 92 is the UTF-8 encoding of 'ƒ' (U+0192)

# The key insight: if we encode "\u00c3" as Latin-1, we get bytes C3 83
# And if those bytes C3 83 are interpreted as UTF-8, we get... that's not valid UTF-8 for a single char

# Let me try yet another approach: directly map the byte patterns
print("\n--- Byte pattern analysis ---")
# The byte pattern C3 83 C6 92 appears in the file
pattern = b'\xc3\x83\xc6\x92'
if pattern in data:
    print(f"Found pattern C3 83 C6 92")
    # What Turkish character should this be?
    # If we decode C3 83 C6 92 as if it were UTF-8... that's '\u00c3'
    # But what if the original was:
    # - Some char X encoded as UTF-8
    # - Read as Latin-1 giving us chars that when re-encoded give C3 83 C6 92
    
    # Let's try: encode as latin1, decode as utf-8
    decoded = pattern.decode('latin-1')
    print(f"Pattern as Latin-1 chars: {decoded!r}")
    # Now re-encode these chars as UTF-8
    re_encoded = decoded.encode('utf-8')
    print(f"Re-encoded as UTF-8: {re_encoded.hex()}")
