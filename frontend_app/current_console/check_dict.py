"""Check PaddleOCR dictionary structure"""
import urllib.request
url = "https://cdn.jsdelivr.net/npm/paddleocr@1.1.1/assets/ppocrv5_dict.txt"
try:
    data = urllib.request.urlopen(url).read().decode("utf-8")
except:
    print("Cannot fetch dict, trying local...")
    data = None

if data:
    lines = data.split("\n")
    print(f"Total lines (split by \\n): {len(lines)}")
    
    # Check for empty lines
    empty_indices = []
    for i, line in enumerate(lines):
        stripped = line.rstrip("\r")
        if len(stripped) == 0:
            empty_indices.append(i)
    
    print(f"Empty lines count: {len(empty_indices)}")
    if empty_indices:
        print(f"Empty line indices: {empty_indices[:20]}")
    
    # Show first 10 entries
    print("\nFirst 10 entries:")
    for i in range(min(10, len(lines))):
        c = lines[i].rstrip("\r")
        print(f"  [{i}] len={len(c)} repr={repr(c)}")
    
    # Check space character
    for i, line in enumerate(lines):
        stripped = line.rstrip("\r")
        if stripped == " ":
            print(f"\nSpace character at index {i}")
            break
    
    # After filtering
    filtered = [l.rstrip("\r") for l in lines if len(l.rstrip("\r")) > 0]
    print(f"\nAfter .filter(line => line.length > 0): {len(filtered)} entries")
    print(f"Removed: {len(lines) - len(filtered)} entries")
    
    # Show what's at common Chinese char positions
    # The character "的" should be somewhere early
    for i, line in enumerate(lines):
        c = line.rstrip("\r")
        if c == "的":
            print(f"\n'的' is at raw index {i}")
            # Check what filtered index it would be
            filtered_idx = len([l.rstrip("\r") for l in lines[:i] if len(l.rstrip("\r")) > 0])
            print(f"'的' would be at filtered index {filtered_idx}")
            print(f"Index shift: {i - filtered_idx}")
            break
    
    # Check if last line is empty (common in text files)
    last = lines[-1].rstrip("\r")
    print(f"\nLast line: repr={repr(last)}, len={len(last)}")
    second_last = lines[-2].rstrip("\r") if len(lines) > 1 else ""
    print(f"Second-to-last: repr={repr(second_last)}, len={len(second_last)}")
