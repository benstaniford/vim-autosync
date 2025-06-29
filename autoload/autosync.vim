" vim-autosync autoload functions

function! autosync#enable()
    let g:autosync_enabled = 1
    call s:setup_autocommands()
    if !g:autosync_silent
        echo 'AutoSync enabled'
    endif
endfunction

function! autosync#disable()
    let g:autosync_enabled = 0
    augroup AutoSync
        autocmd!
    augroup END
    if !g:autosync_silent
        echo 'AutoSync disabled'
    endif
endfunction

function! autosync#toggle()
    if g:autosync_enabled
        call autosync#disable()
    else
        call autosync#enable()
    endif
endfunction

function! autosync#status()
    echo 'AutoSync is ' . (g:autosync_enabled ? 'enabled' : 'disabled')
    echo 'Managed directories: ' . string(g:autosync_dirs)
    echo 'Pull interval: ' . g:autosync_pull_interval . ' seconds'
endfunction

function! autosync#setup()
    echo 'AutoSync Setup:'
    echo 'Add directories to sync in your vimrc:'
    echo "let g:autosync_dirs = ['~/Wiki', '~/Notes']"
    echo ''
    echo 'Available configuration options:'
    echo 'g:autosync_dirs - List of directories to manage'
    echo 'g:autosync_pull_interval - Seconds between pulls (default: 60)'
    echo 'g:autosync_enabled - Enable/disable plugin (default: 1)'
    echo 'g:autosync_commit_message_template - Template for commit messages'
    echo 'g:autosync_silent - Suppress status messages (default: 0)'
endfunction

function! autosync#on_buf_read_pre()
    if !g:autosync_enabled
        return
    endif
    
    if has('python3')
        try
            call s:ensure_python_module()
            py3 autosync_core.on_buf_read_pre()
        catch
            " Silently fail for read operations to avoid interrupting workflow
            if g:autosync_debug
                echoerr 'AutoSync error in on_buf_read_pre: ' . v:exception
            endif
        endtry
    endif
endfunction

function! autosync#on_buf_write_post()
    if !g:autosync_enabled
        return
    endif
    
    if has('python3')
        try
            call s:ensure_python_module()
            py3 autosync_core.on_buf_write_post()
        catch
            " Show errors for write operations since they're more critical
            echoerr 'AutoSync error in on_buf_write_post: ' . v:exception
        endtry
    endif
endfunction

function! autosync#pull_current()
    if has('python3')
        try
            call s:ensure_python_module()
            py3 autosync_core.manual_pull()
        catch
            echoerr 'AutoSync error in pull_current: ' . v:exception
        endtry
    endif
endfunction

function! autosync#push_current()
    if has('python3')
        try
            call s:ensure_python_module()
            py3 autosync_core.manual_push()
        catch
            echoerr 'AutoSync error in push_current: ' . v:exception
        endtry
    endif
endfunction

function! s:setup_autocommands()
    augroup AutoSync
        autocmd!
        if g:autosync_enabled
            autocmd BufReadPre * call autosync#on_buf_read_pre()
            autocmd BufWritePost * call autosync#on_buf_write_post()
        endif
    augroup END
endfunction

function! autosync#check_buffer_reload()
    " Check if current buffer needs to be reloaded after a pull
    " This is called via timer after async pull operations
    if !exists('b:autosync_check_reload') || b:autosync_check_reload
        checktime
        let b:autosync_check_reload = 0
    endif
endfunction

function! autosync#diagnose()
    echo 'AutoSync Diagnostic Information:'
    echo '================================'
    echo 'Vim Python support: ' . (has('python3') ? 'Available' : 'Not available')
    
    if has('python3')
        py3 << EOF
import sys
import vim
import os

vim.command("echo 'Python version: ' . '{}.{}.{}'.format(*sys.version_info[:3])".format(*sys.version_info[:3]))
vim.command("echo 'Python executable: ' . '{}'".format(sys.executable))

# Check if GitPython is available
try:
    import git
    vim.command("echo 'GitPython: Available (version: {})'".format(git.__version__))
except ImportError as e:
    vim.command("echo 'GitPython: Not available - {}'".format(str(e)))

# Check plugin path
plugin_dir = vim.eval("expand('<sfile>:p:h:h')")
python_dir = os.path.join(plugin_dir, 'python3')
vim.command("echo 'Plugin Python directory: {}'".format(python_dir))
vim.command("echo 'Python directory exists: {}'".format(os.path.exists(python_dir)))

# Check if autosync_core can be imported
try:
    if python_dir not in sys.path:
        sys.path.insert(0, python_dir)
    import autosync_core
    vim.command("echo 'autosync_core: Successfully imported'")
    vim.command("echo 'autosync_core initialized: {}'".format(getattr(autosync_core, '_initialized', False)))
except Exception as e:
    vim.command("echo 'autosync_core: Import failed - {}'".format(str(e)))
EOF
    else
        echo 'Python3 not available in this Vim build'
    endif
    
    echo ''
    echo 'Configuration:'
    echo 'Managed directories: ' . string(g:autosync_dirs)
    echo 'Pull interval: ' . g:autosync_pull_interval . ' seconds'
    echo 'Enabled: ' . (g:autosync_enabled ? 'Yes' : 'No')
    echo 'Silent mode: ' . (g:autosync_silent ? 'Yes' : 'No')
    echo 'Debug mode: ' . (exists('g:autosync_debug') ? (g:autosync_debug ? 'Yes' : 'No') : 'No')
endfunction

function! s:ensure_python_module()
    " Ensure the Python module is available
    py3 << EOF
try:
    autosync_core
    # Check if module is properly initialized
    if not hasattr(autosync_core, '_initialized') or not autosync_core._initialized:
        autosync_core.initialize()
except NameError:
    import sys
    import vim
    plugin_dir = vim.eval("expand('<sfile>:p:h:h')")
    if plugin_dir + '/python3' not in sys.path:
        sys.path.insert(0, plugin_dir + '/python3')
    try:
        import autosync_core
        autosync_core.initialize()
    except ImportError as e:
        vim.command(f"echoerr 'Failed to import autosync_core: {e}'")
        vim.command("echoerr 'Make sure GitPython is installed for the Python version used by Vim'")
        vim.command("echoerr 'Try: python3 -m pip install GitPython'")
    except Exception as e:
        vim.command(f"echoerr 'Error initializing autosync_core: {e}'")
EOF
endfunction
