---
name: linter
description: Runs ruff check to lint Python files in this project and reports errors. Use when the user asks to lint, check, or find linting errors in code. Automatically fix safe violations when asked.
disable-model-invocation: true
---

# Linter

Runs `ruff check` (configured in `pyproject.toml`, line-length 120).

## Usage

**Check all Python files:**
```bash
ruff check .
```

**Check specific files:**
```bash
ruff check sound_effects.py videoeditor.py
```

**Auto-fix safe violations:**
```bash
ruff check --fix .
```

**Show full error details:**
```bash
ruff check --show-source .
```

## Output

- Exit code `0` → no errors
- Exit code `1` → violations found; output lists `file:line:col: CODE message`

## After running

- Report all violations grouped by file
- For each violation, state whether it is auto-fixable (`--fix`) or requires manual intervention
- If `--fix` was applied, re-run `ruff check .` to confirm the output is clean
