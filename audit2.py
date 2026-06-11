import re

with open(r'D:\rd-tracker\backend\main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("=== CRITICAL ISSUES ===\n")

# 1. Check for missing type hints on response data
print("1. Endpoints without explicit return type hints:")
endpoints = []
for i, line in enumerate(lines, 1):
    if re.match(r'\s*@app\.(get|post|put|delete|patch)', line):
        # Get function definition
        for j in range(i, min(i+3, len(lines))):
            if 'def ' in lines[j]:
                func_sig = lines[j].strip()
                if '->' not in func_sig:
                    endpoints.append((i+1, func_sig[:80]))
                break

if endpoints:
    for line_no, sig in endpoints[:5]:
        print(f"   Line {line_no}: {sig}")
    if len(endpoints) > 5:
        print(f"   ... and {len(endpoints)-5} more")
else:
    print("   ✓ All endpoints have return type hints")

# 2. Check for inconsistent return formats
print("\n2. Return statement patterns:")
returns = [i for i, line in enumerate(lines, 1) if re.match(r'\s*return\s+{', line)]
print(f"   Direct dict returns: {len(returns)}")

returns_no_dict = [i for i, line in enumerate(lines, 1) if 'return ' in line and '{' not in line and 'return ' in line.split('#')[0]]
print(f"   Other returns: {len(returns_no_dict)}")

# 3. Check for unvalidated user input
print("\n3. Query parameter validation:")
query_params = [i for i, line in enumerate(lines, 1) if 'query' in line and 'Query' in line]
print(f"   Query parameter declarations: {len(query_params)}")

# 4. Check for rate limiting consistency
print("\n4. Rate limiting:")
rate_limit = sum(1 for line in lines if 'rate_limit' in line or 'RateLimit' in line)
print(f"   Rate limit mentions: {rate_limit}")

# 5. Check database transaction consistency
print("\n5. Database transactions:")
with_tx = sum(1 for line in lines if 'transaction' in line.lower())
print(f"   Explicit transaction mentions: {with_tx}")

print("\nDetailed fix plan will be applied systematically...")
