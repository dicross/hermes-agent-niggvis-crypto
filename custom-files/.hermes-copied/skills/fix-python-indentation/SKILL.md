---
name: fix-python-indentation
description: Fix IndentationError in Python skill scripts by rewriting with consistent 4-space indentation
version: 1.0.0
author: Niggvis
tags: [python, debugging, indentation, skills]
---

# Fix Python Indentation Errors in Skill Scripts

When skill scripts (executor.py, journal.py, scanner.py, etc.) have indentation errors that cause `IndentationError`, use this approach:

## Problem
- Skill scripts may have inconsistent indentation (mixed 1-space, 2-space, 4-space)
- `patch` tool often fails because `old_string` doesn't match due to invisible whitespace differences
- Line-by-line fixes are error-prone and time-consuming

## Solution: Rewrite Entire File with Consistent Indentation

1. **Read the file** to understand the structure and logic
2. **Rewrite the entire file** with consistent 4-space indentation (Python standard)
3. **Test the script** immediately after rewriting

## Example Pattern

```python
# BAD: inconsistent indentation (1-2 spaces)
def cmd_buy(args):
 cfg = _get_risk_config()  # 1 space
 mode = cfg["mode"]        # 1 space
   print(f"Processing")    # 3 spaces - ERROR!

# GOOD: consistent 4-space indentation
def cmd_buy(args):
    cfg = _get_risk_config()  # 4 spaces
    mode = cfg["mode"]        # 4 spaces
    print(f"Processing")      # 4 spaces
```

## When to Use
- `IndentationError: unindent does not match any outer indentation level`
- `patch` tool fails multiple times on the same file
- File has mixed indentation (visible when checking with `repr()`)

## Verification
```bash
python3 ~/.hermes/skills/<skill>/scripts/<script>.py --help
# Should run without syntax errors
```

## Pitfalls
- Don't try to patch individual lines - whitespace is invisible and patches fail
- Don't use `sed` or `awk` - they can't handle multi-line indentation fixes
- Always verify the script runs after rewriting
- Preserve all original functionality - only fix indentation
