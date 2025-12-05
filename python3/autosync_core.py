"""
vim-autosync core module

This module handles the asynchronous git operations for the vim-autosync plugin.
"""

import vim
import os
import threading
import time
import logging
from typing import Dict, List, Optional, Set
from pathlib import Path

try:
    from git import Repo, GitCommandError
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False

# Global state
_repos: Dict[str, Repo] = {}
_last_pull_times: Dict[str, float] = {}
_active_operations: Set[str] = set()
_lock = threading.Lock()
_initialized = False

# Message queue for thread-safe UI communication
from queue import Queue
_message_queue: Queue = Queue()

# Logger setup - disable console output to avoid vim startup messages
_logger = logging.getLogger('vim-autosync')
# Only log to file if needed, not to console to avoid vim startup noise
_logger.setLevel(logging.WARNING)  # Only show warnings and errors
_logger.addHandler(logging.NullHandler())  # Prevent any default handlers


def initialize():
    """Initialize the plugin."""
    global _initialized
    if not GIT_AVAILABLE:
        error_msg = "vim-autosync requires GitPython. Install with: python3 -m pip install GitPython"
        _logger.error(error_msg)
        try:
            # Try to display error immediately if we're in main thread
            escaped_msg = error_msg.replace("'", "''")
            vim.command(f"echoerr '{escaped_msg}'")
        except:
            # If we can't display immediately, queue it
            _message_queue.put((error_msg, True))
        raise ImportError("GitPython not available")
    
    # Setup logging based on debug setting
    if _is_debug():
        _logger.setLevel(logging.DEBUG)
        # Add console handler for debug mode
        _handler = logging.StreamHandler()
        _formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        _handler.setFormatter(_formatter)
        _logger.addHandler(_handler)
        _logger.debug("vim-autosync initialized in debug mode")
    
    _initialized = True


def _get_managed_dirs() -> List[str]:
    """Get list of managed directories from Vim configuration."""
    try:
        dirs = vim.eval('g:autosync_dirs')
        return [os.path.expanduser(d) for d in dirs] if dirs else []
    except vim.error:
        return []


def _get_pull_interval() -> int:
    """Get pull interval from Vim configuration."""
    try:
        return int(vim.eval('g:autosync_pull_interval'))
    except (vim.error, ValueError):
        return 60


def _get_commit_template() -> str:
    """Get commit message template from Vim configuration."""
    try:
        return vim.eval('g:autosync_commit_message_template')
    except vim.error:
        return 'Auto-sync: Updated %s'


def _is_debug() -> bool:
    """Check if debug mode is enabled."""
    try:
        return bool(int(vim.eval('g:autosync_debug')))
    except (vim.error, ValueError):
        return False


def _is_silent() -> bool:
    """Check if silent mode is enabled."""
    try:
        return bool(int(vim.eval('g:autosync_silent')))
    except (vim.error, ValueError):
        return False


def _auto_commit_before_pull() -> bool:
    """Check if auto-commit before pull is enabled."""
    try:
        return bool(int(vim.eval('g:autosync_auto_commit_before_pull')))
    except (vim.error, ValueError):
        return True  # Default to True for backward compatibility


def _echo_message(message: str, error: bool = False):
    """Queue a message to be displayed safely from the main thread."""
    if _is_silent():
        return
    
    # Add message to queue - this is thread-safe
    _message_queue.put((message, error))


def process_queued_messages():
    """Process all queued messages from the main thread. Called via timer."""
    messages_processed = 0
    while not _message_queue.empty() and messages_processed < 10:  # Limit to prevent blocking
        try:
            message, error = _message_queue.get_nowait()
            if message == "SCHEDULE_RELOAD":
                # Special command to schedule buffer reload
                vim.command("call timer_start(100, 'autosync#check_buffer_reload')")
            else:
                # Escape single quotes to prevent vim command errors
                escaped_message = message.replace("'", "''")
                if error:
                    vim.command(f"echohl ErrorMsg | echo '{escaped_message}' | echohl None")
                else:
                    vim.command(f"echo '{escaped_message}'")
            messages_processed += 1
        except:
            # Queue is empty or vim.command failed
            break


def test_message_queue():
    """Test function to verify message queue is working."""
    _echo_message("Message queue test successful!", error=False)
    _echo_message("Error message test", error=True)


def _get_repo_for_file(filepath: str) -> Optional[Repo]:
    """Get the git repository for a given file path."""
    if not filepath:
        return None
    
    abs_path = os.path.abspath(filepath)
    managed_dirs = _get_managed_dirs()
    
    for managed_dir in managed_dirs:
        abs_managed_dir = os.path.abspath(managed_dir)
        if abs_path.startswith(abs_managed_dir):
            if abs_managed_dir not in _repos:
                try:
                    _repos[abs_managed_dir] = Repo(abs_managed_dir)
                    # Only log errors, not successful initialization
                except Exception as e:
                    _logger.error(f"Failed to initialize repo for {abs_managed_dir}: {e}")
                    _echo_message(f"Error initializing Git repository for {abs_managed_dir}: {e}", error=True)
                    continue
            
            return _repos[abs_managed_dir]
    
    return None


def _get_last_pull_file(repo_dir: str) -> str:
    """Get the path to the last pull timestamp file."""
    return os.path.join(repo_dir, '.last_pull_timestamp')


def _get_last_pull_time(repo_dir: str) -> float:
    """Get the timestamp of the last pull from the file."""
    if repo_dir not in _last_pull_times:
        last_pull_file = _get_last_pull_file(repo_dir)
        if os.path.exists(last_pull_file):
            try:
                with open(last_pull_file, 'r') as f:
                    _last_pull_times[repo_dir] = float(f.read().strip())
            except (IOError, ValueError):
                _last_pull_times[repo_dir] = 0
        else:
            _last_pull_times[repo_dir] = 0
    
    return _last_pull_times[repo_dir]


def _update_last_pull_time(repo_dir: str):
    """Update the timestamp of the last pull."""
    current_time = time.time()
    _last_pull_times[repo_dir] = current_time
    
    try:
        last_pull_file = _get_last_pull_file(repo_dir)
        with open(last_pull_file, 'w') as f:
            f.write(str(current_time))
    except IOError as e:
        _logger.error(f"Failed to update last pull time: {e}")


def _should_pull(repo_dir: str) -> bool:
    """Check if we should pull based on the interval."""
    last_pull_time = _get_last_pull_time(repo_dir)
    current_time = time.time()
    pull_interval = _get_pull_interval()
    
    return current_time - last_pull_time >= pull_interval


def _commit_all_changes(repo: Repo, repo_dir: str):
    """Commit all uncommitted changes in the repository."""
    try:
        # Add all changed files to the index
        repo.git.add(A=True)  # Equivalent to 'git add -A'
        
        # Create a commit message
        commit_template = _get_commit_template()
        # Use a generic message for bulk commits during pull
        commit_msg = "Auto-sync: Committing changes before pull"
        
        # Commit the changes
        repo.index.commit(commit_msg)
        
        if not _is_silent():
            _echo_message(f"Committed uncommitted changes in {os.path.basename(repo_dir)}")
            
    except Exception as e:
        _logger.error(f"Failed to commit changes in {repo_dir}: {e}")
        raise  # Re-raise to let the caller handle it


def _async_pull(repo: Repo, repo_dir: str):
    """Perform git pull in a background thread."""
    operation_key = f"pull:{repo_dir}"
    
    with _lock:
        if operation_key in _active_operations:
            # Don't log routine duplicate operation checks
            return
        _active_operations.add(operation_key)
    
    try:
        # Check if there are uncommitted changes and if we should auto-commit
        if repo.is_dirty():
            if _auto_commit_before_pull():
                # Commit all uncommitted changes before pulling
                _commit_all_changes(repo, repo_dir)
            else:
                # User has disabled auto-commit, so skip the pull
                if not _is_silent():
                    _echo_message(f"Skipping pull for {os.path.basename(repo_dir)} - uncommitted changes present", error=True)
                return
        
        # Now attempt the pull
        repo.remotes.origin.pull()
        _update_last_pull_time(repo_dir)
        # Only show message if not silent
        if not _is_silent():
            _echo_message(f"Pulled updates for {os.path.basename(repo_dir)}")
        
        # Schedule a buffer reload check - queue this instead of calling directly
        _message_queue.put(("SCHEDULE_RELOAD", False))
        
    except GitCommandError as e:
        error_msg = str(e)
        if "merge conflict" in error_msg.lower() or "conflict" in error_msg.lower():
            _logger.error(f"Merge conflict during pull for {repo_dir}: {e}")
            _echo_message(f"Merge conflict in {repo_dir}. Please resolve manually.", error=True)
        elif "up to date" in error_msg.lower():
            # This is actually not an error, just log it
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


def _async_commit_and_push(repo: Repo, repo_dir: str, rel_filepath: str):
    """Perform git commit and push in a background thread."""
    operation_key = f"push:{repo_dir}:{rel_filepath}"
    
    with _lock:
        if operation_key in _active_operations:
            # Don't log routine duplicate operation checks
            return
        _active_operations.add(operation_key)
    
    try:
        # Reduce log verbosity

        # Check if file has changes OR is untracked (new file)
        is_dirty = repo.is_dirty(path=rel_filepath)
        is_untracked = rel_filepath in repo.untracked_files

        if is_dirty or is_untracked:
            commit_template = _get_commit_template()
            commit_msg = commit_template % rel_filepath

            repo.index.add([rel_filepath])
            repo.index.commit(commit_msg)
            repo.remotes.origin.push()

            # Only show success message if not silent
            if not _is_silent():
                file_status = "new file" if is_untracked else "modified"
                _echo_message(f"Auto-synced: {rel_filepath} ({file_status})")
        # Don't log when there are no changes to avoid noise
            
    except GitCommandError as e:
        _logger.error(f"Git commit/push failed for {rel_filepath}: {e}")
        _echo_message(f"Git commit/push failed for {rel_filepath}: {e}", error=True)
    except Exception as e:
        _logger.error(f"Unexpected error during commit/push for {rel_filepath}: {e}")
        _echo_message(f"Unexpected error during commit/push: {e}", error=True)
    finally:
        with _lock:
            _active_operations.discard(operation_key)


def on_buf_read_pre():
    """Handle BufReadPre event."""
    if not _initialized:
        return
    
    try:
        filename = vim.current.buffer.name
        if not filename:
            return
        
        repo = _get_repo_for_file(filename)
        if not repo:
            return
        
        repo_dir = repo.working_dir
        if _should_pull(repo_dir):
            # Start pull in background thread
            thread = threading.Thread(target=_async_pull, args=(repo, repo_dir))
            thread.daemon = True
            thread.start()
            
    except Exception as e:
        _logger.error(f"Error in on_buf_read_pre: {e}")
        _echo_message(f"Error in on_buf_read_pre: {e}", error=True)


def on_buf_write_post():
    """Handle BufWritePost event."""
    if not _initialized:
        return
    
    try:
        filename = vim.current.buffer.name
        if not filename:
            return
        
        repo = _get_repo_for_file(filename)
        if not repo:
            return
        
        repo_dir = repo.working_dir
        rel_filepath = os.path.relpath(filename, repo_dir)
        
        # Start commit and push in background thread
        thread = threading.Thread(target=_async_commit_and_push, args=(repo, repo_dir, rel_filepath))
        thread.daemon = True
        thread.start()
        
    except Exception as e:
        _logger.error(f"Error in on_buf_write_post: {e}")
        _echo_message(f"Error in on_buf_write_post: {e}", error=True)


def manual_pull():
    """Manually trigger a pull for the current file's repository."""
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
        
        repo_dir = repo.working_dir
        _echo_message(f"Pulling changes for {repo_dir}...")
        
        # Force pull regardless of interval
        thread = threading.Thread(target=_async_pull, args=(repo, repo_dir))
        thread.daemon = True
        thread.start()
        
    except Exception as e:
        _logger.error(f"Error in manual_pull: {e}")
        _echo_message(f"Error in manual_pull: {e}", error=True)


def manual_push():
    """Manually trigger a push for the current file."""
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
        
        repo_dir = repo.working_dir
        rel_filepath = os.path.relpath(filename, repo_dir)
        
        _echo_message(f"Committing and pushing {rel_filepath}...")
        
        thread = threading.Thread(target=_async_commit_and_push, args=(repo, repo_dir, rel_filepath))
        thread.daemon = True
        thread.start()
        
    except Exception as e:
        _logger.error(f"Error in manual_push: {e}")
        _echo_message(f"Error in manual_push: {e}", error=True)
