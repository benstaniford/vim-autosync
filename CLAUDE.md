# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

vim-autosync is a Vim plugin that automatically synchronizes files to Git repositories as you edit them. It uses a hybrid VimScript/Python architecture with asynchronous threading to prevent blocking the editor during Git operations.

## Architecture

### Three-Layer Design

1. **Plugin Layer** (`plugin/autosync.vim`)
   - Initializes configuration variables and default settings
   - Loads Python module and sets up Python path
   - Registers Vim commands and autocommands
   - Manages message processing timer (500ms interval)

2. **Autoload Layer** (`autoload/autosync.vim`)
   - Implements Vim-side functions for all commands
   - Handles Python module initialization and error recovery
   - Bridges between Vim events and Python backend
   - Manages buffer reload checks after pull operations

3. **Python Core** (`python3/autosync_core.py`)
   - Performs all Git operations using GitPython library
   - Implements threading for async pull/push operations
   - Maintains repository state (cached Repo objects, pull timestamps)
   - Provides thread-safe message queue for UI updates

### Critical Threading Model

**Thread Safety Design:**
- Git operations run in daemon threads to avoid blocking Vim
- Message queue (`Queue`) bridges thread boundary for safe UI updates
- Vim timer polls queue every 500ms via `autosync#process_messages()`
- Active operations tracked with locks to prevent duplicate operations

**Why This Matters:**
- Vim's Python integration is NOT thread-safe for vim.command()
- Direct vim.command() from threads causes crashes/corruption
- All UI updates must be queued and processed from main thread
- Special "SCHEDULE_RELOAD" message triggers buffer reload timer

### State Management

**Repository Caching:**
- `_repos` dict caches GitPython Repo objects by directory path
- Prevents repeated repository initialization overhead
- Managed directories determined by `g:autosync_dirs` configuration

**Pull Timing:**
- `.last_pull_timestamp` files track last pull time per repository
- `_last_pull_times` dict provides in-memory cache
- Pull occurs only if `g:autosync_pull_interval` seconds have elapsed

**Conflict Handling:**
- Before pull: auto-commits uncommitted changes if `g:autosync_auto_commit_before_pull` is enabled
- Merge conflicts displayed as error messages for manual resolution
- Operation tracking prevents concurrent operations on same repo

## Development Commands

### Testing the Plugin

```vim
" Load the plugin in Vim
:packadd vim-autosync

" Check Python 3 support
:echo has('python3')

" Diagnose plugin status and dependencies
:AutoSyncDiagnose

" Test message queue system
:AutoSyncTestMessages
```

### Manual Git Operations

```vim
" Manually pull for current file's repo
:AutoSyncPull

" Manually commit and push current file
:AutoSyncPush

" Check plugin status
:AutoSyncStatus
```

### Debugging

Enable debug logging in your vimrc:
```vim
let g:autosync_debug = 1
```

This enables Python logging to see detailed operation flow, useful for diagnosing threading issues or Git errors.

## Configuration Variables Reference

| Variable | Type | Default | Critical Behavior |
|----------|------|---------|-------------------|
| `g:autosync_dirs` | List | `[]` | Directories to monitor - must be Git repos with remotes |
| `g:autosync_pull_interval` | Number | `60` | Seconds between automatic pulls |
| `g:autosync_auto_commit_before_pull` | Boolean | `1` | Auto-commit dirty repo before pull to avoid conflicts |
| `g:autosync_commit_message_template` | String | `'Auto-sync: Updated %s'` | Template for commit messages (`%s` = relative path) |
| `g:autosync_debug` | Boolean | `0` | Enable Python logging to console |
| `g:autosync_silent` | Boolean | `0` | Suppress all status messages |

## Key Implementation Details

### Message Queue Pattern

The plugin cannot call `vim.command()` from background threads safely. Instead:

```python
# In Python thread:
_message_queue.put(("Status message", False))  # Non-error
_message_queue.put(("Error message", True))    # Error

# In Vim main thread (timer callback):
def process_queued_messages():
    message, error = _message_queue.get_nowait()
    vim.command(f"echo '{escaped_message}'")
```

When modifying code that displays messages, always use `_echo_message()` which queues messages, never call `vim.command()` directly from threads.

### Buffer Reload After Pull

When a pull completes, the Python thread queues a special message:
```python
_message_queue.put(("SCHEDULE_RELOAD", False))
```

The message processor recognizes this and schedules a timer to call `autosync#check_buffer_reload()`, which runs `:checktime` to reload modified buffers.

### Operation Deduplication

The `_active_operations` set prevents concurrent operations:
```python
operation_key = f"pull:{repo_dir}"
with _lock:
    if operation_key in _active_operations:
        return  # Already running
    _active_operations.add(operation_key)
```

Always use try/finally to ensure operation keys are removed even on error.

## Common Gotchas

1. **Python Module Path**: The plugin dynamically adds `plugin_dir/python3` to `sys.path`. If imports fail, check `s:ensure_python_module()` logic in `autoload/autosync.vim`.

2. **GitPython Requirement**: Plugin will error if GitPython is not installed for the Python version Vim uses. Vim's Python may differ from system Python.

3. **Dirty Repository Handling**: If `g:autosync_auto_commit_before_pull = 0` and repo is dirty, pull is skipped entirely to avoid conflicts.

4. **Timer Persistence**: The message timer runs continuously when plugin is enabled. Disable plugin with `:AutoSyncDisable` to stop background processing.

5. **Autocommand Scope**: The plugin uses `BufReadPre` (before buffer load) for pulls and `BufWritePost` (after save) for pushes. This timing is intentional to ensure file state consistency.

## File Locations

- `plugin/autosync.vim` - Entry point, loaded on Vim startup
- `autoload/autosync.vim` - Lazy-loaded functions (loaded on first command)
- `python3/autosync_core.py` - All Git operations and threading logic
- `doc/autosync.txt` - Vim help documentation (`:help autosync`)
- `.last_pull_timestamp` - Created in each managed repo (should be .gitignored)

## Requirements

- Vim with `+python3` support
- GitPython: `pip install GitPython` (for Vim's Python interpreter)
- Git repositories must be initialized with remote configured
- Managed directories specified in `g:autosync_dirs` must be repo roots
