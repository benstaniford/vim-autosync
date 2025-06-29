" vim-autosync - Auto-sync folders to git as you edit files in vim
" Author: Ben Staniford
" Version: 1.0

if exists('g:loaded_autosync')
    finish
endif
let g:loaded_autosync = 1

" Save cpoptions and set to vim defaults
let s:save_cpo = &cpo
set cpo&vim

" Default configuration
if !exists('g:autosync_dirs')
    let g:autosync_dirs = []
endif

if !exists('g:autosync_pull_interval')
    let g:autosync_pull_interval = 60
endif

if !exists('g:autosync_enabled')
    let g:autosync_enabled = 1
endif

if !exists('g:autosync_commit_message_template')
    let g:autosync_commit_message_template = 'Auto-sync: Updated %s'
endif

if !exists('g:autosync_silent')
    let g:autosync_silent = 0
endif

if !exists('g:autosync_debug')
    let g:autosync_debug = 0
endif

" Initialize Python module
if has('python3')
    py3 import sys
    py3 import vim
    let s:plugin_dir = expand('<sfile>:p:h:h')
    py3 sys.path.insert(0, vim.eval('s:plugin_dir') + '/python3')
    py3 import autosync_core
    py3 autosync_core.initialize()
else
    echoerr 'vim-autosync requires Python 3 support'
    finish
endif

" Commands
command! AutoSyncEnable call autosync#enable()
command! AutoSyncDisable call autosync#disable()
command! AutoSyncToggle call autosync#toggle()
command! AutoSyncStatus call autosync#status()
command! AutoSyncPull call autosync#pull_current()
command! AutoSyncPush call autosync#push_current()
command! AutoSyncSetup call autosync#setup()

" Setup autocommands
augroup AutoSync
    autocmd!
    if g:autosync_enabled
        autocmd BufReadPre * call autosync#on_buf_read_pre()
        autocmd BufWritePost * call autosync#on_buf_write_post()
    endif
augroup END

" Restore cpoptions
let &cpo = s:save_cpo
unlet s:save_cpo
