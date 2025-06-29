" vim-autosync example configuration
" Add this to your .vimrc file

" Load the plugin (if using vim's native package management)
packadd vim-autosync

" Basic configuration - specify directories to manage
let g:autosync_dirs = [
  \ '~/Wiki',
  \ '~/Notes'
  \ ]

" Optional: Advanced configuration
" let g:autosync_pull_interval = 120  " Pull every 2 minutes instead of 1
" let g:autosync_commit_message_template = '[AUTO] Updated %s'
" let g:autosync_silent = 1  " Suppress status messages

" Optional: Disable by default and enable manually
" let g:autosync_enabled = 0

" Optional: Key mappings for manual operations
" nnoremap <leader>asp :AutoSyncPull<CR>
" nnoremap <leader>asP :AutoSyncPush<CR>
" nnoremap <leader>ast :AutoSyncToggle<CR>
" nnoremap <leader>ass :AutoSyncStatus<CR>
