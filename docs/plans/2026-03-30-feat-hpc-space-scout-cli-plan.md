---
title: "feat: HPC Space Scout CLI tool"
type: feat
status: completed
date: 2026-03-30
origin: docs/brainstorms/2026-03-30-hpc-space-usage-cli-brainstorm.md
---

# feat: HPC Space Scout CLI Tool

## Overview

A standalone Python CLI tool that scans all disk locations belonging to a user on a shared HPC cluster and produces an actionable report of what space is used, what's safe to remove, and what isn't backed up. Designed for two audiences: humans (rich terminal tables, tree views) and coding agents (flat JSON, no decoration).

This is a **general-purpose HPC utility**, not tied to any specific project. It lives at `/hpc/compgen/users/dstoker/Software/command_line_tools/hpc_space_scout.py`.

## Problem Statement / Motivation

Three concurrent pressures (see brainstorm: [2026-03-30 brainstorm](../brainstorms/2026-03-30-hpc-space-usage-cli-brainstorm.md)):

1. **Home directory 5GB limit** — easy to hit with caches, logs, tooling
2. **Project folder bloat** — analysis dirs accumulate large intermediate files across dozens of projects
3. **No cleanup guidance** — `du` shows sizes but not what's safe to remove. Git status is the best available proxy for "is this backed up?"

## Proposed Solution

A single-file Python script with two subcommands:

- **`scan`** (default) — scan home + project dirs, report N largest files/folders per location, tag each with a git-based safety recommendation
- **`search-formats`** — find files by extension across user-owned folders, report with sizes and safety tags

### Architecture

```
hpc_space_scout.py          # Single executable script (~800-1200 lines)
                            # Symlinked from /hpc/compgen/users/dstoker/bin/hpc-space-scout
```

No package structure. One file. Dependencies: Python 3.11 stdlib + `rich`.

### Module-level organization within the single file

```
# --- Data models (dataclasses) ---
@dataclass FileEntry         # path, size_bytes, size_human, owner, safety_tag, git_info
@dataclass FolderEntry       # path, size_bytes, size_human, owner, safety_tag, git_info, file_count
@dataclass GitInfo           # in_repo, repo_root, tracked, gitignored, modified, last_commit_date, has_remote
@dataclass ScanResult        # location, total_size, largest_files, largest_folders, git_repos_found
@dataclass CacheEnvelope     # version, timestamp, ttl_seconds, scan_results

# --- Scanning layer ---
def discover_user_folders()   # name matching + UID ownership + recursive search
def scan_folder()             # os.walk + os.stat, returns sizes
def get_folder_sizes()        # aggregate subfolder sizes including children
def find_largest_files()      # top-N files by size
def find_largest_folders()    # top-N folders by total size
def search_by_extension()     # extension-specific file search

# --- Git layer ---
def find_git_root()           # walk up to find .git/
def get_git_info_for_file()   # git ls-files, git status, git log
def get_git_info_for_folder() # repo detection, last commit, uncommitted changes
def classify_safety()         # safe / caution / risky based on GitInfo

# --- Cache layer ---
def get_cache_path()          # /hpc/compgen/users/<user>/.cache/hpc-space-scout/
def load_cache()              # read + validate TTL + schema version
def save_cache()              # atomic write (write to .tmp, rename)
def is_cache_valid()          # check TTL

# --- Output layer ---
def render_human()            # rich tables, colored safety tags, section headers
def render_agent_json()       # flat JSON list to stdout, no decoration
def render_tree()             # tree view with sizes (uses rich.tree)
def write_report_file()       # --output FILE (markdown or JSON)

# --- CLI layer ---
def build_parser()            # argparse with subparsers
def cmd_scan()                # scan subcommand handler
def cmd_search_formats()      # search-formats subcommand handler
def main()                    # dispatch
```

## Technical Approach

### Implementation Phases

#### Phase 1: Core scanning + human output

Deliver a working tool that scans directories and reports largest files/folders with `rich` tables.

**Tasks:**
- [x] `hpc_space_scout.py` — scaffold with argparse, `build_parser()`, `main()`, `cmd_scan()`
- [x] Data models: `FileEntry`, `FolderEntry`, `ScanResult` as dataclasses
- [x] `discover_user_folders(usernames, root_folders)` — three-strategy folder discovery:
  - Name matching: look for `*/<username>` and `*/analysis/<username>` paths
  - UID ownership: `os.stat().st_uid` on directories
  - Recursive search: `os.walk` with depth limit (max 4 levels) to find username-matching dirs
- [x] `scan_folder(path)` — `os.walk` + `os.stat`, skip `.git/`, `.venv/`, `__pycache__/`, `node_modules/` by default
- [x] `find_largest_files(path, n)` and `find_largest_folders(path, n)`
- [x] `render_human(scan_results)` — `rich.table.Table` with columns: Name, Size, Type, Location
- [x] Home dir section: total usage vs 5GB limit, with a usage bar
- [x] Symlink creation + shebang (standalone venv at `.venv/` next to the script)
- [x] Error handling: permission denied (skip + warn to stderr), missing paths (skip + warn), interrupted scan (clean exit)

**Exit criteria:** `hpc-space-scout` runs, scans home + projects, prints human-readable tables of largest files/folders.

#### Phase 2: Git safety analysis

Add git status checking and safety tagging to every reported item.

**Tasks:**
- [x] `GitInfo` dataclass: `in_repo`, `repo_root`, `tracked`, `gitignored`, `modified_since_commit`, `last_commit_date`, `has_remote`
- [x] `find_git_root(path)` — walk up parent dirs looking for `.git/`
- [x] `get_git_info_for_file(path)` — calls `git ls-files`, `git diff --name-only`, `git log -1 --format=%aI`
- [x] `get_git_info_for_folder(path)` — repo detection, `git status --porcelain`, last commit date
- [x] `classify_safety(git_info) -> str` — the classification logic:
  - **Safe**: tracked in git, unchanged since last commit, remote exists
  - **Caution**: tracked but modified since last commit, OR no remote configured
  - **Risky**: not in any git repo, OR untracked, OR .gitignored (see brainstorm: .gitignored = riskier, no backup)
- [x] Integrate safety tags into `render_human()` — colored tags: green=safe, yellow=caution, red=risky
- [x] Add git info columns to output: safety tag, last commit date, modified status

**Exit criteria:** Every reported file/folder has a safety tag. Tags are colored in terminal output.

**Note on the .gitignored contradiction:** The brainstorm's resolved questions explicitly state ".gitignored files are riskier — they have no backup." The safety tag table in Key Decisions #9 incorrectly listed .gitignored as "caution." This plan treats **.gitignored as risky**, consistent with the resolved rationale.

**Note on "safe" accuracy:** "Safe" means locally committed + unchanged + remote configured. The tool does NOT verify that the remote is up to date (no `git fetch` or network calls). A disclaimer is printed: "Safe assumes remote is current. Verify with `git push --dry-run` if unsure."

#### Phase 3: Agent output + caching + parallelism

Add `--agent` JSON output, scan caching, and parallel scanning.

**Tasks:**
- [x] `--agent` flag: suppress rich formatting, suppress progress bar, output JSON to stdout
- [x] Agent JSON schema (one object per item):
  ```json
  {
    "summary": {
      "total_usage_bytes": 12345678,
      "total_usage_human": "11.8 MB",
      "locations_scanned": 5,
      "safe_to_remove_count": 12,
      "safe_to_remove_bytes": 9876543,
      "safe_to_remove_human": "9.4 MB",
      "cache_age_seconds": 3600,
      "scan_timestamp": "2026-03-30T14:22:00Z"
    },
    "items": [
      {
        "path": "/hpc/compgen/projects/foo/analysis/dstoker/big_file.csv",
        "size_bytes": 1048576,
        "size_human": "1.0 MB",
        "is_directory": false,
        "owner": "dstoker",
        "location": "/hpc/compgen/projects/foo/analysis/dstoker",
        "safety_tag": "risky",
        "git_tracked": false,
        "git_modified": false,
        "gitignored": false,
        "in_git_repo": true,
        "last_commit_date": null,
        "has_remote": true,
        "recommendation": "Untracked file in git repo. No backup evidence."
      }
    ]
  }
  ```
- [x] `CacheEnvelope` dataclass with `version` (schema version int), `timestamp`, `ttl_seconds`, `scan_results`
- [x] `save_cache()` — atomic write (write `.tmp`, `os.rename`), file permissions `0o600`
- [x] `load_cache()` — validate schema version match + TTL not expired + file permissions
- [x] `--fresh` flag to bypass cache
- [x] `--cache-ttl` flag (default 24h, in hours)
- [x] Cache staleness notice in human output: "Results from cache (3h 12m old). Use --fresh to rescan."
- [x] Parallel scanning with `concurrent.futures.ThreadPoolExecutor` (I/O-bound workload: stat calls + git subprocesses)
- [x] `--workers` flag (default: `min(8, os.cpu_count())`) — exposed so users can tune for NFS load
- [x] `rich.progress` bar during scan (suppressed when `--agent` or no TTY via `sys.stdout.isatty()`)
- [x] Write cache only on complete scan (not on interrupted/partial runs) — register SIGINT handler that sets a `scan_interrupted` flag

**Exit criteria:** `--agent` produces valid JSON parseable by an agent. Cache works with TTL. Parallel scan is measurably faster than sequential.

#### Phase 4: search-formats mode + tree view + file output

Add the second subcommand, tree rendering, and `--output` file writing.

**Tasks:**
- [x] `cmd_search_formats(args)` subcommand handler
- [x] `search_by_extension(root_paths, extensions, usernames)` — recursive search, case-insensitive matching (compare `.lower()`)
- [x] Skip `.git/`, `.venv/`, `__pycache__/`, `node_modules/` by default in extension search too
- [x] `--include-hidden` flag to override directory exclusions
- [x] Extension search output: same dual format (human tables / agent JSON), with safety tags
- [x] Extension search summary: total count, total size, breakdown by extension
- [x] `--tree` flag with `--depth N` (default depth=2 when `--tree` is given)
- [x] Tree rendering via `rich.tree.Tree` with size annotations on each node
- [x] Tree augments the table output (shown after the per-location tables), not mutually exclusive
- [x] `--output FILE` — detect format from extension (`.json` = JSON, anything else = markdown/text)
- [x] When `--output` is used, ALSO print to terminal (tee behavior) unless `--quiet` is passed
- [x] `--json` flag — shorthand for `--agent` + write to stdout (no file). Redundant with `--agent` but explicit.
- [x] `--min-size` flag (e.g. `--min-size 1MB`) to filter noise from top-N results and extension searches

**Exit criteria:** Both subcommands work. Tree view renders. Reports can be saved to files.

### Default directory exclusion list

The following directories are skipped during scanning by default (overridable with `--include-hidden`):

```
.git/
.venv/
__pycache__/
node_modules/
.mypy_cache/
.pytest_cache/
.tox/
.eggs/
*.egg-info/
```

### CLI surface (final)

```
hpc-space-scout [scan]
    --usernames USER [USER ...]     # Default: $(whoami)
    --folders PATH [PATH ...]       # Default: /hpc/compgen/projects ~
    --n-largest-files N             # Default: 3
    --n-largest-folders N           # Default: 3
    --min-size SIZE                 # e.g. 1MB, 100KB. Default: no filter
    --tree                          # Enable tree view
    --depth N                       # Tree depth (default: 2, requires --tree)
    --agent                         # JSON output, no colors, no progress bar
    --json                          # Alias for --agent
    --output FILE                   # Write report to file (also prints to terminal)
    --quiet                         # Suppress terminal output (use with --output)
    --fresh                         # Ignore cache, force rescan
    --cache-ttl HOURS               # Cache TTL in hours (default: 24)
    --workers N                     # Thread pool size (default: min(8, cpu_count))
    --include-hidden                # Don't skip .git, .venv, etc.

hpc-space-scout search-formats EXT [EXT ...]
    --usernames USER [USER ...]     # Same defaults
    --folders PATH [PATH ...]       # Same defaults
    --min-size SIZE                 # Filter small files
    --agent / --json                # JSON output
    --output FILE                   # Write to file
    --quiet                         # Suppress terminal
    --include-hidden                # Include hidden dirs
```

## System-Wide Impact

**Minimal.** This is a standalone read-only utility. It:
- Only reads file metadata (`os.stat`, `os.walk`) and runs `git` subprocesses
- Never modifies, moves, or deletes any files
- Writes only to its own cache file (permissions `0o600`)
- Does not require network access (no `git fetch`, no API calls)

**NFS considerations:** Aggressive parallel `os.stat` on NFS can cause throttling. The `--workers` flag (default 8) lets users dial this down. Git subprocess calls are batched per-repo, not per-file.

**Security on shared HPC:**
- Cache file written with `0o600` permissions — other users cannot read your file inventory
- `--usernames` defaults to `whoami` — no accidental scanning of other users' files
- Scanning other usernames only shows directory-level sizes visible to anyone via `ls`, not file contents
- Git status calls only run against repos the scanning user has read access to

## Acceptance Criteria

### Functional Requirements

- [ ] `hpc-space-scout` (no args) scans `~` and `/hpc/compgen/projects/` for current user
- [ ] Reports N largest files and N largest subfolders per discovered location
- [ ] Each reported item has a safety tag (safe/caution/risky) based on git status
- [ ] `.gitignored` files are tagged as **risky** (not caution)
- [ ] `--agent` produces valid JSON matching the defined schema, no ANSI codes, no progress bar
- [ ] `search-formats .csv .sql` finds matching files case-insensitively across user-owned dirs
- [ ] `--tree --depth 3` renders a tree with size annotations after the tables
- [ ] Cache persists across runs, respects TTL, is invalidated by `--fresh`
- [ ] Interrupted scans do not write partial caches
- [ ] `--output report.md` writes a report file AND prints to terminal

### Non-Functional Requirements

- [ ] Full scan of home + projects completes in under 2 minutes with default parallelism
- [ ] Works on the HPC submit nodes (hpcs05, hpcs06) without SLURM — no GPU or heavy compute needed
- [ ] Graceful handling of permission denied errors (skip + warn, don't crash)
- [ ] Single file, no package installation required beyond `rich`
- [ ] Cache file permissions `0o600`

## Dependencies & Prerequisites

- Python 3.11 (any venv that has it, or system python if >=3.11)
- `rich` library — install via `uv pip install rich` into a venv or use an existing venv that has it
- `git` CLI available on PATH (standard on HPC)
- `/hpc/compgen/users/dstoker/bin/` exists and is on `$PATH` (for the symlink)

## Risk Analysis & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| NFS throttling from parallel stat calls | Scan slows or gets throttled | `--workers` flag, default 8, can reduce to 1 |
| Large repos with many files make git status slow | Scan hangs on one repo | Per-repo timeout (30s), skip + warn if exceeded |
| Cache schema changes between versions | Old cache crashes tool | `version` field in cache; mismatch = rescan |
| `rich` not installed in user's Python | ImportError on startup | Clear error message: "pip install rich" |
| Symlink target path hardcoded | Breaks if tool moves | Symlink is trivially re-creatable |

## Sources & References

### Origin

- **Brainstorm document:** [docs/brainstorms/2026-03-30-hpc-space-usage-cli-brainstorm.md](../brainstorms/2026-03-30-hpc-space-usage-cli-brainstorm.md)
- Key decisions carried forward: dual audience (human+agent), git-based safety tags, parallel+cached scanning, standalone script + symlink

### Internal References

- CLI patterns: `manage_configs.py` (argparse + subparsers + dispatch dict)
- Dual output pattern: `read_and_analyze_logs_and_traces_cli.py` (`--json` flag switching between human and JSON formatters)
- Error handling: stderr + `sys.exit(1)` pattern used across all existing CLI tools
- Existing tools at `/hpc/compgen/users/dstoker/Software/command_line_tools/` — `tree`, `entire`, `gdc-client`
