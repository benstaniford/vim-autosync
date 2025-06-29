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
        py3 autosync_core.on_buf_read_pre()
    endif
endfunction

function! autosync#on_buf_write_post()
    if !g:autosync_enabled
        return
    endif
    
    if has('python3')
        py3 autosync_core.on_buf_write_post()
    endif
endfunction

function! autosync#pull_current()
    if has('python3')
        py3 autosync_core.manual_pull()
    endif
endfunction

function! autosync#push_current()
    if has('python3')
        py3 autosync_core.manual_push()
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
