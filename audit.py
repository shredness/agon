import re

with open(r'D:\rd-tracker\backend\main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

issues = {}

# ISSUE 1: Bare except clauses without logging
for i, line in enumerate(lines, 1):
    if re.match(r'\s*except\s+Exception\s*:', line):
        next_line = lines[i].strip() if i < len(lines) else ''
        if next_line in ['pass', 'continue', '']:
            if 'except_bare' not in issues:
                issues['except_bare'] = []
            issues['except_bare'].append(i)

# ISSUE 2: conn.close() statements
close_count = sum(1 for line in lines if 'conn.close()' in line)

print("=== BACKEND AUDIT REPORT ===\n")
print(f"Total lines: {len(lines)}")
print(f"Database close() statements: {close_count}")
print(f"Bare except clauses: {len(issues.get('except_bare', []))}")
print(f"\nSpecific issues found:")

# Sample issue lines
if 'except_bare' in issues:
    print(f"\n1. Bare exception handlers (first 5):")
    for line_no in issues['except_bare'][:5]:
        print(f"   Line {line_no}: {lines[line_no-1].strip()}")

print("\n=== FRONTEND AUDIT ===\n")

with open(r'D:\rd-tracker\frontend\index.html', 'r', encoding='utf-8') as f:
    frontend = f.readlines()

print(f"Total lines: {len(frontend)}")

# Check for console.error/log without context
errors = sum(1 for line in frontend if 'console.error' in line or 'console.log' in line)
print(f"Console output statements: {errors}")

# Check for bare catch blocks
catch_blocks = sum(1 for line in frontend if re.search(r'catch\s*\(', line))
print(f"Try/catch blocks: {catch_blocks}")

print("\nAudit complete. Ready for systematic fixes.")
