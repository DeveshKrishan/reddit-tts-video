---
name: pr-creator
description: >-
  Create GitHub pull requests with conventional commit messages and titles
  (feat, fix, docs, ci, test). Use when creating a PR, opening a pull request,
  preparing a branch for review, or when the user asks for commitlint-compliant
  commits and PR titles.
---

# PR Creator

Create PRs where every commit passes commitlint (`@commitlint/config-conventional`) and the PR title uses the same type prefix.

## Conventional commit format

```
<type>(<optional-scope>): <subject>

<optional body>
```

### Allowed types

| Type | Use for |
|------|---------|
| `feat` | New features or user-facing behavior |
| `fix` | Bug fixes |
| `docs` | Documentation and skills only |
| `test` | Tests only |
| `ci` | GitHub Actions, commitlint, pre-commit CI |
| `refactor` | Code changes without behavior change |
| `chore` | Tooling, deps, misc maintenance |

### Rules

- Subject: imperative mood, lowercase, no trailing period, max ~72 chars
- Scope: optional, lowercase (`shorts`, `youtube`, `workflow`)
- Header max length: 100 characters (commitlint default)

### Examples

```
feat(shorts): add vertical pipeline with multi-part splitting
test: add unit tests for segment splitting
ci: add checks workflow with commitlint
docs: add pr-creator skill for conventional commits
fix(youtube): append Shorts hashtag to upload description
```

## PR title format

Match the **primary change type** of the branch:

```
feat: configure pipeline for YouTube Shorts
ci: add checks workflow and commitlint
test: add unit tests for Shorts config
docs: document Shorts configuration options
```

PR title = one conventional header (type + subject). Do not include a body in the title.

## Workflow

### 1. Inspect the branch

Run in parallel:

```bash
git status
git diff
git log --oneline main..HEAD
git diff main...HEAD
```

### 2. Plan commits

Split changes into focused commits by type. Prefer several small commits over one large commit when changes span types (e.g. `feat` + `test` + `ci`).

### 3. Write conventional commit messages

Before committing, draft messages that will pass commitlint. If rewriting history on a feature branch:

```bash
git reset --soft main
# stage files per commit, then commit with conventional messages
```

Never use `git rebase -i` (non-interactive environments).

### 4. Validate before push

```bash
chmod +x scripts/validate-commits.sh
./scripts/validate-commits.sh main HEAD
python -m unittest discover -s tests -v
```

Fix any commitlint failures before pushing.

### 5. Push and create PR

```bash
git push -u origin HEAD
gh pr create --title "feat: short description of primary change" --body "$(cat <<'EOF'
## Summary
- bullet points

## Test plan
- [ ] checks workflow passes
- [ ] manual verification if needed
EOF
)"
```

### 6. Verify CI

```bash
gh pr checks --watch
```

Ensure `commitlint` and `python-tests` pass on `.github/workflows/checks.yaml`.

## Commit type decision guide

```
User-facing behavior change?     → feat
Bug fix?                         → fix
Only tests added/changed?        → test
Only .github/workflows or lint?  → ci
Only README/docs/skills?         → docs
Refactor without behavior change?→ refactor
Deps, config, housekeeping?    → chore
```

When a branch mixes types, use the **most significant** type for the PR title (usually `feat` or `fix`).

## Anti-patterns

- `Configure pipeline for YouTube Shorts` — missing type prefix
- `feat: Configure Pipeline.` — subject must be lowercase, no trailing period
- `feature: add shorts` — use `feat`, not `feature`
- PR title `Configure pipeline for YouTube Shorts` — must start with `feat:` / `ci:` / etc.

## Project-specific notes

- Commitlint config: `commitlint.config.cjs` extends `@commitlint/config-conventional`
- CI validates all commits in a PR via `wagoid/commitlint-github-action@v6`
- Lint/format/typecheck run locally via pre-commit, not GitHub Actions
- Python tests: `python -m unittest discover -s tests`
