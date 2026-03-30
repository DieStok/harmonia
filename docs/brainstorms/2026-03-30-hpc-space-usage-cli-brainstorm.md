# Brainstorm: HPC Space Usage CLI Tool

**Date:** 2026-03-30
**Status:** Brainstorm

## What We're Building

A Python CLI tool that scans all disk locations belonging to a user on the HPC cluster and produces an actionable report of what space is used, what's safe to remove, and what isn't backed up. The tool supports two audiences: **humans** (overview tables, tree views, colored output) and **coding agents** (short, structured, actionable output).

### Core capabilities

1. **Home directory scan** — report total usage vs 5GB limit, largest files and subfolders
2. **Project folder scan** — find all folders the user owns under `/hpc/compgen/projects/`, including `analysis/<username>/` dirs inside other people's projects. Also finds folders owned by the user's UID even if not named after them.
3. **Git safety analysis** — for each reported file/folder: is the containing dir a git repo? Is the file tracked, .gitignored, or untracked? Last commit date? Modified since last commit? Produces a safety tag: safe / caution / risky.
4. **File format search** (separate mode) — scan user-owned folders for specific extensions (e.g. `.csv`, `.sql`) with a dedicated report, skipping the usual largest-files output.
5. **Tree view** (opt-in) — `--tree --depth N` shows a tree of identified folders with sizes.

## Why This Approach

- **Scan + recommend, don't auto-delete.** The tool's value is surfacing what's removable with confidence, not removing it. Soft safety tags let users (and agents) make informed decisions.
- **Agent-friendly as a first-class mode**, not bolted on — agents need structured JSON with flat entries, not parsed terminal tables.
- **Git as the backup heuristic.** On this HPC, code goes to GitHub and data goes to Yoda. Git status is a good proxy for "is this backed up?" for code artifacts. Data files are typically untracked and large — exactly the pattern we want to surface.

## Key Decisions

1. **User detection: name + ownership + recursive search.** Look for folders named after the usernames AND check UNIX ownership AND search deeper in the tree. This catches dirs the user owns even if not following the naming convention.

2. **Git check at both levels.** Folder-level (is it a repo? last commit?) AND per-file (tracked? .gitignored? changed since commit?). This powers the safety recommendations.

3. **File-format search is a separate mode**, not an add-on to the main scan. Invoked with e.g. `--search-formats .csv .sql`. Reports only matching files in user-owned folders.

4. **Tree view is off by default.** Opt-in via `--tree [--depth N]`.

5. **Parallel scanning + progress bar + caching.** Use multiprocessing for folder scanning, show a progress bar, cache results to JSON. `--fresh` to force rescan. Cache expires after 24 hours by default (configurable via `--cache-ttl`).

6. **Dual output: terminal + file.** Colored terminal output by default. `--output report.md` or `--json` for file export.

7. **Dual audience: human + agent output modes.** `--agent` produces structured JSON to stdout (one entry per actionable item, no colors). The default mode is human-friendly with tables and colors.

8. **Location:** `/hpc/compgen/users/dstoker/Software/command_line_tools/` alongside existing CLI utilities.

9. **Soft safety recommendations.** Each reported item gets a tag:
   - **Safe** — tracked in git, unchanged since last commit (backed up, removable)
   - **Caution** — tracked but modified, or in a git repo but .gitignored (may have unsaved changes)
   - **Risky** — not in any git repo, or untracked (no backup evidence, think twice)

## Design Constraints

### Agent-friendly output
- `--agent` flag: JSON output with flat structure, one entry per actionable item
- Each entry includes: path, size_bytes, size_human, safety_tag, git_tracked, git_modified, last_commit_date, recommendation_reason
- No ANSI colors, no decorative formatting, no multi-page output
- Summary line at top: total usage, number of safe-to-remove items, total reclaimable space

### Human-friendly output (default)
- Colored terminal tables (rich or similar)
- Section headers per scanned location
- Progress bar during scan
- Optional tree view

### CLI structure (proposed)
```
hpc-space-scout [scan]              # Main scan (default subcommand)
    --usernames dstoker dstoker6
    --folders /hpc/compgen/projects /home/cog/dstoker
    --n-largest-files 3
    --n-largest-folders 3
    --tree [--depth N]
    --agent                         # Agent-friendly compact output
    --json                          # JSON output to stdout
    --output FILE                   # Write report to file
    --fresh                         # Ignore cache

hpc-space-scout search-formats .csv .sql  # File format search mode
    --usernames dstoker dstoker6
    --folders /hpc/compgen/projects
    --agent
    --json
```

### Dependencies (keep minimal for HPC)
- Python 3.11 (available in .venv)
- `rich` for terminal formatting — required dependency, not optional (install via `uv pip install rich`)
- Standard library only for core logic (os, stat, subprocess for git, multiprocessing, json, pathlib)

## Resolved Questions

1. **Name:** `hpc-space-scout`
2. **Cache location:** `/hpc/compgen/users/dstoker/.cache/` — avoids 5GB home limit
3. **`.gitignored` files are riskier** — they have no backup, so the tool warns about them rather than treating them as disposable
4. **Standalone script + symlink** — a `.py` file in `command_line_tools/` with a symlink on PATH (e.g. `/hpc/compgen/users/dstoker/bin/hpc-space-scout` to avoid home dir bloat, added to `$PATH`)
