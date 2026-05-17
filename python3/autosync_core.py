"""
vim-autosync core module

This module handles the asynchronous git operations for the vim-autosync plugin.

Threading model:
    Vim's Python integration is NOT thread-safe — vim.eval() and vim.command()
    must only be called from the main thread. Background threads communicate
    with the main thread exclusively through _message_queue, which is drained
    by process_queued_messages() on a Vim timer.

    Any config needed by an async function is captured via _snapshot_config()
    on the main thread before the thread is spawned, and passed in as an arg.
"""

import os
import threading
import time
import logging
from queue import Queue, Empty
from typing import TYPE_CHECKING, Dict, List, Optional, Set

import vim  # type: ignore[import-not-found]  # available only inside Vim

if TYPE_CHECKING:
    from git import Repo, GitCommandError
    GIT_AVAILABLE = True
else:
    try:
        from git import Repo, GitCommandError
        GIT_AVAILABLE = True
    except ImportError:
        GIT_AVAILABLE = False
        Repo = None
        GitCommandError = Exception

# Global state
_repos: Dict[str, "Repo"] = {}
_last_pull_times: Dict[str, float] = {}
_active_operations: Set[str] = set()
_active_threads: List[threading.Thread] = []
_lock = threading.Lock()
_initialized = False

# Message queue for thread-safe UI communication
_message_queue: Queue = Queue()

# Logger setup
_logger = logging.getLogger('vim-autosync')
_logger.setLevel(logging.WARNING)
_logger.addHandler(logging.NullHandler())


def initialize():
    """Initialize the plugin. Must be called from the main (Vim) thread."""
    global _initialized
    if not GIT_AVAILABLE:
        error_msg = "vim-autosync requires GitPython. Install with: python3 -m pip install GitPython"
        _logger.error(error_msg)
        try:
            escaped_msg = error_msg.replace("'", "''")
            vim.command(f"echoerr '{escaped_msg}'")
        except Exception:
            _message_queue.put((error_msg, True))
        raise ImportError("GitPython not available")

    if _is_debug():
        _logger.setLevel(logging.DEBUG)
        if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.NullHandler)
                   for h in _logger.handlers):
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            _logger.addHandler(handler)
        _logger.debug("vim-autosync initialized in debug mode")

    _initialized = True


# --- Config readers (main thread only) ---------------------------------------

def _get_managed_dirs() -> List[str]:
    try:
        dirs = vim.eval('g:autosync_dirs')
        return [os.path.expanduser(d) for d in dirs] if dirs else []
    except vim.error:
        return []


def _get_pull_interval() -> int:
    try:
        return int(vim.eval('g:autosync_pull_interval'))
    except (vim.error, ValueError):
        return 60


def _get_commit_template() -> str:
    try:
        return vim.eval('g:autosync_commit_message_template')
    except vim.error:
        return 'Auto-sync: Updated %s'


def _is_debug() -> bool:
    try:
        return bool(int(vim.eval('g:autosync_debug')))
    except (vim.error, ValueError):
        return False


def _is_silent() -> bool:
    try:
        return bool(int(vim.eval('g:autosync_silent')))
    except (vim.error, ValueError):
        return False


def _auto_commit_before_pull() -> bool:
    try:
        return bool(int(vim.eval('g:autosync_auto_commit_before_pull')))
    except (vim.error, ValueError):
        return True


def _snapshot_config() -> Dict[str, object]:
    """Capture config values needed by async workers. Main-thread only."""
    return {
        'silent': _is_silent(),
        'auto_commit_before_pull': _auto_commit_before_pull(),
        'commit_template': _get_commit_template(),
    }


# --- Message queue -----------------------------------------------------------

def _echo_message(message: str, error: bool = False):
    """Queue a message for the main thread. Safe to call from any thread."""
    _message_queue.put((message, error))


def process_queued_messages():
    """Drain queued messages on the main thread. Called via Vim timer."""
    # Silent-mode is read once per tick (main thread, so safe).
    silent = _is_silent()
    deadline = time.monotonic() + 0.05  # cap work per tick at 50ms

    while time.monotonic() < deadline:
        try:
            message, error = _message_queue.get_nowait()
        except Empty:
            break

        if message == "SCHEDULE_RELOAD":
            try:
                vim.command("call timer_start(100, 'autosync#check_buffer_reload')")
            except vim.error as e:
                _logger.error(f"Failed to schedule buffer reload: {e}")
            continue

        if silent:
            continue

        escaped_message = message.replace("'", "''")
        try:
            if error:
                vim.command(f"echohl ErrorMsg | echo '{escaped_message}' | echohl None")
            else:
                vim.command(f"echo '{escaped_message}'")
        except vim.error as e:
            _logger.error(f"Failed to display message: {e}")


def test_message_queue():
    """Test function to verify message queue is working."""
    _echo_message("Message queue test successful!", error=False)
    _echo_message("Error message test", error=True)


# --- Path / repo helpers -----------------------------------------------------

def _is_under(path: str, parent: str) -> bool:
    """Return True if `path` is `parent` or a descendant of it."""
    try:
        return os.path.commonpath([path, parent]) == parent
    except ValueError:
        # ValueError if paths are on different drives (Windows) or mixed types
        return False


def _get_repo_for_file(filepath: str) -> Optional["Repo"]:
    """Get the git repository for a given file path. Main-thread only."""
    if not filepath:
        return None

    abs_path = os.path.abspath(filepath)
    managed_dirs = _get_managed_dirs()

    for managed_dir in managed_dirs:
        abs_managed_dir = os.path.abspath(managed_dir)
        if not _is_under(abs_path, abs_managed_dir):
            continue

        if abs_managed_dir not in _repos:
            try:
                _repos[abs_managed_dir] = Repo(abs_managed_dir)
            except Exception as e:
                _logger.error(f"Failed to initialize repo for {abs_managed_dir}: {e}")
                _echo_message(
                    f"Error initializing Git repository for {abs_managed_dir}: {e}",
                    error=True)
                continue

        return _repos[abs_managed_dir]

    return None


# --- Pull-timestamp tracking -------------------------------------------------

def _get_last_pull_file(repo_dir: str) -> str:
    return os.path.join(repo_dir, '.last_pull_timestamp')


def _get_last_pull_time(repo_dir: str) -> float:
    """Read cached or persisted last-pull time. Thread-safe."""
    with _lock:
        cached = _last_pull_times.get(repo_dir)
        if cached is not None:
            return cached

        last_pull_file = _get_last_pull_file(repo_dir)
        value = 0.0
        if os.path.exists(last_pull_file):
            try:
                with open(last_pull_file, 'r') as f:
                    value = float(f.read().strip())
            except (IOError, ValueError):
                value = 0.0
        _last_pull_times[repo_dir] = value
        return value


def _update_last_pull_time(repo_dir: str):
    """Persist the current time as the last-pull time. Thread-safe."""
    current_time = time.time()
    with _lock:
        _last_pull_times[repo_dir] = current_time

    try:
        with open(_get_last_pull_file(repo_dir), 'w') as f:
            f.write(str(current_time))
    except IOError as e:
        _logger.error(f"Failed to update last pull time: {e}")


def _should_pull(repo_dir: str) -> bool:
    return time.time() - _get_last_pull_time(repo_dir) >= _get_pull_interval()


# --- Async git operations ----------------------------------------------------

def _commit_all_changes(repo: "Repo", repo_dir: str, silent: bool):
    """Commit all uncommitted changes in the repository.

    NOTE: commits *every* dirty file in the repo, not just the file that
    triggered the sync. See `doc/autosync.txt` for the rationale.
    """
    try:
        repo.git.add(A=True)
        repo.index.commit("Auto-sync: Committing changes before pull")
        if not silent:
            _echo_message(f"Committed uncommitted changes in {os.path.basename(repo_dir)}")
    except Exception as e:
        _logger.error(f"Failed to commit changes in {repo_dir}: {e}")
        raise


def _async_pull(repo: "Repo", repo_dir: str, config: Dict[str, object]):
    """Perform git pull in a background thread."""
    operation_key = f"pull:{repo_dir}"
    silent = bool(config['silent'])

    with _lock:
        if operation_key in _active_operations:
            return
        _active_operations.add(operation_key)

    try:
        if repo.is_dirty():
            if config['auto_commit_before_pull']:
                _commit_all_changes(repo, repo_dir, silent)
            else:
                if not silent:
                    _echo_message(
                        f"Skipping pull for {os.path.basename(repo_dir)} - "
                        f"uncommitted changes present",
                        error=True)
                return

        repo.remotes.origin.pull()
        _update_last_pull_time(repo_dir)
        if not silent:
            _echo_message(f"Pulled updates for {os.path.basename(repo_dir)}")

        _message_queue.put(("SCHEDULE_RELOAD", False))

    except GitCommandError as e:
        error_msg = str(e)
        if "conflict" in error_msg.lower():
            _logger.error(f"Merge conflict during pull for {repo_dir}: {e}")
            _echo_message(
                f"Merge conflict in {repo_dir}. Please resolve manually.",
                error=True)
        elif "up to date" in error_msg.lower():
            _logger.debug(f"Repository {repo_dir} is already up to date")
        else:
            _logger.error(f"Git pull failed for {repo_dir}: {e}")
            _echo_message(f"Git pull failed for {repo_dir}: {e}", error=True)
    except Exception as e:
        _logger.error(f"Unexpected error during pull for {repo_dir}: {e}")
        _echo_message(f"Unexpected error during pull: {e}", error=True)
    finally:
        with _lock:
            _active_operations.discard(operation_key)


def _async_commit_and_push(repo: "Repo", repo_dir: str, rel_filepath: str,
                           config: Dict[str, object]):
    """Perform git commit and push in a background thread."""
    operation_key = f"push:{repo_dir}:{rel_filepath}"
    silent = bool(config['silent'])
    commit_template = str(config['commit_template'])

    with _lock:
        if operation_key in _active_operations:
            return
        _active_operations.add(operation_key)

    try:
        is_dirty = repo.is_dirty(path=rel_filepath)
        is_untracked = rel_filepath in repo.untracked_files

        if is_dirty or is_untracked:
            commit_msg = commit_template % rel_filepath
            repo.index.add([rel_filepath])
            repo.index.commit(commit_msg)
            repo.remotes.origin.push()

            if not silent:
                file_status = "new file" if is_untracked else "modified"
                _echo_message(f"Auto-synced: {rel_filepath} ({file_status})")

    except GitCommandError as e:
        _logger.error(f"Git commit/push failed for {rel_filepath}: {e}")
        _echo_message(f"Git commit/push failed for {rel_filepath}: {e}", error=True)
    except Exception as e:
        _logger.error(f"Unexpected error during commit/push for {rel_filepath}: {e}")
        _echo_message(f"Unexpected error during commit/push: {e}", error=True)
    finally:
        with _lock:
            _active_operations.discard(operation_key)


# --- Thread spawning ---------------------------------------------------------

def _spawn(target, args):
    """Spawn a daemon thread and track it for shutdown-time joining."""
    thread = threading.Thread(target=target, args=args)
    thread.daemon = True
    with _lock:
        _active_threads[:] = [t for t in _active_threads if t.is_alive()]
        _active_threads.append(thread)
    thread.start()
    return thread


def shutdown(timeout: float = 2.0):
    """Wait briefly for outstanding sync threads to finish. Main-thread only.

    Called from VimLeavePre so that an in-flight push has a chance to land
    before Vim exits and the daemon threads are killed.
    """
    with _lock:
        threads = [t for t in _active_threads if t.is_alive()]
    deadline = time.monotonic() + timeout
    for thread in threads:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        thread.join(timeout=remaining)


# --- Vim event handlers (main thread) ----------------------------------------

def on_buf_read_pre():
    if not _initialized:
        return
    try:
        filename = vim.current.buffer.name
        if not filename:
            return
        repo = _get_repo_for_file(filename)
        if not repo:
            return
        repo_dir = str(repo.working_dir)
        if _should_pull(repo_dir):
            _spawn(_async_pull, (repo, repo_dir, _snapshot_config()))
    except Exception as e:
        _logger.error(f"Error in on_buf_read_pre: {e}")
        _echo_message(f"Error in on_buf_read_pre: {e}", error=True)


def on_buf_write_post():
    if not _initialized:
        return
    try:
        filename = vim.current.buffer.name
        if not filename:
            return
        repo = _get_repo_for_file(filename)
        if not repo:
            return
        repo_dir = str(repo.working_dir)
        rel_filepath = os.path.relpath(filename, repo_dir)
        _spawn(_async_commit_and_push,
               (repo, repo_dir, rel_filepath, _snapshot_config()))
    except Exception as e:
        _logger.error(f"Error in on_buf_write_post: {e}")
        _echo_message(f"Error in on_buf_write_post: {e}", error=True)


def manual_pull():
    if not _initialized:
        _echo_message("Plugin not initialized", error=True)
        return
    try:
        filename = vim.current.buffer.name
        if not filename:
            _echo_message("No file in current buffer", error=True)
            return
        repo = _get_repo_for_file(filename)
        if not repo:
            _echo_message("File is not in a managed directory", error=True)
            return
        repo_dir = str(repo.working_dir)
        _echo_message(f"Pulling changes for {repo_dir}...")
        _spawn(_async_pull, (repo, repo_dir, _snapshot_config()))
    except Exception as e:
        _logger.error(f"Error in manual_pull: {e}")
        _echo_message(f"Error in manual_pull: {e}", error=True)


def manual_push():
    if not _initialized:
        _echo_message("Plugin not initialized", error=True)
        return
    try:
        filename = vim.current.buffer.name
        if not filename:
            _echo_message("No file in current buffer", error=True)
            return
        repo = _get_repo_for_file(filename)
        if not repo:
            _echo_message("File is not in a managed directory", error=True)
            return
        repo_dir = str(repo.working_dir)
        rel_filepath = os.path.relpath(filename, repo_dir)
        _echo_message(f"Committing and pushing {rel_filepath}...")
        _spawn(_async_commit_and_push,
               (repo, repo_dir, rel_filepath, _snapshot_config()))
    except Exception as e:
        _logger.error(f"Error in manual_push: {e}")
        _echo_message(f"Error in manual_push: {e}", error=True)
