#!/usr/bin/env python3
import re

# Read the current main.py
with open(r'D:\rd-tracker\backend\main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with "# ── DB" and get_db() definition
# Remove everything from after get_db() until "# ── Event logging"

new_lines = []
skip_mode = False
preserve_next_block = False

for i, line in enumerate(lines):
    # Start of DB section we want to keep
    if '# ── DB' in line and 'def get_db' in lines[i+1] if i+1 < len(lines) else False:
        new_lines.append(line)
        # Add the get_db function
        for j in range(i+1, min(i+8, len(lines))):
            new_lines.append(lines[j])
            if 'def ' in lines[j] and j > i+2:
                break
        skip_mode = True
        continue
    
    # Skip old migration code
    if skip_mode and ('# ── Event logging' in line or '# ── Auth' in line):
        new_lines.append('\n')
        new_lines.append(line)
        skip_mode = False
    elif skip_mode:
        continue
    else:
        new_lines.append(line)

with open(r'D:\rd-tracker\backend\main.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"✓ main.py cleaned (removed {len(lines) - len(new_lines)} lines)")
