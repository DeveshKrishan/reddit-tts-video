---
name: formatter
description: Runs ruff format to auto-format Python files in this project. Use when the user asks to format, fix formatting, or run the code formatter. Reports which files were reformatted.
disable-model-invocation: true
---

# Formatter

Runs `ruff format` (configured in `pyproject.toml`, line-length 120).

## Usage

**Format all Python files:**
```bash
ruff format .
```

**Format specific files:**
```bash
ruff format sound_effects.py videoeditor.py
```

**Preview changes without writing (dry-run):**
```bash
ruff format --check .
```

## Output

- `ruff format .` rewrites files in place and prints which files were reformatted
- `ruff format --check .` exits `1` with a list of files that would change (nothing is written)

## After running

- Report which files were reformatted
- If no files changed, confirm formatting is already clean
- Re-stage any reformatted files with `git add` before committing
