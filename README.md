# vim-autosync

A fully asynchronous Vim plugin that automatically syncs your files to Git repositories as you edit them. Perfect for maintaining wikis, notes, or any other files that you want to keep synchronized across devices.

## Features

- **Asynchronous operations**: Git pull/push operations run in background threads, so your editing is never blocked
- **Configurable directories**: Manage multiple directories with different Git repositories
- **Smart pulling**: Only pulls from remote when a configurable interval has passed
- **Auto-commit and push**: Automatically commits and pushes changes when you save files
- **Manual controls**: Commands to manually trigger pull/push operations
- **Flexible configuration**: Customize commit messages, intervals, and behavior

## Requirements

- Vim with Python 3 support (`+python3`)
- GitPython library: `pip install GitPython`
- Git repositories must already be initialized and configured with remotes

## Installation

### Using Vim 8+ native package management:

```bash
mkdir -p ~/.vim/pack/plugins/opt
cd ~/.vim/pack/plugins/opt
git clone https://github.com/yourusername/vim-autosync.git
```

Add to your `.vimrc`:
```vim
packadd vim-autosync
```

### Using a plugin manager:

#### vim-plug:
```vim
Plug 'yourusername/vim-autosync', { 'on': [] }
```

#### Vundle:
```vim
Plugin 'yourusername/vim-autosync'
```

## Configuration

Add the following to your `.vimrc` file:

### Basic Configuration

```vim
" Required: Specify directories to manage
let g:autosync_dirs = ['~/Wiki', '~/Notes', '~/Documents/MyProject']

" Optional: Enable the plugin (default: 1)
let g:autosync_enabled = 1
```

### Advanced Configuration

```vim
" Pull interval in seconds (default: 60)
let g:autosync_pull_interval = 120

" Commit message template (default: 'Auto-sync: Updated %s')
let g:autosync_commit_message_template = 'Auto-update: %s modified'

" Silent mode - suppress status messages (default: 0)
let g:autosync_silent = 0
```

### Complete Example Configuration

```vim
" Enable vim-autosync
packadd vim-autosync

" Configure directories to manage
let g:autosync_dirs = [
  \ '~/Wiki',
  \ '~/Notes',
  \ '~/Documents/Research'
  \ ]

" Set pull interval to 2 minutes
let g:autosync_pull_interval = 120

" Custom commit message template
let g:autosync_commit_message_template = '[AUTO] Updated %s'

" Keep it quiet
let g:autosync_silent = 1
```

## Usage

Once configured, the plugin works automatically:

- **On file read**: Automatically pulls changes from remote if the pull interval has passed
- **On file save**: Automatically commits and pushes the saved file

### Manual Commands

- `:AutoSyncStatus` - Show current plugin status and configuration
- `:AutoSyncPull` - Manually pull changes for the current file's repository
- `:AutoSyncPush` - Manually commit and push the current file
- `:AutoSyncEnable` - Enable the plugin
- `:AutoSyncDisable` - Disable the plugin
- `:AutoSyncToggle` - Toggle the plugin on/off
- `:AutoSyncSetup` - Show setup instructions

## How It Works

1. **Directory Detection**: When you open or save a file, the plugin checks if it's within any of your configured `g:autosync_dirs`

2. **Automatic Pulling**: On `BufReadPre`, if enough time has passed since the last pull (based on `g:autosync_pull_interval`), the plugin pulls changes from the remote repository in a background thread

3. **Automatic Pushing**: On `BufWritePost`, the plugin commits the saved file and pushes it to the remote repository in a background thread

4. **Timestamp Tracking**: The plugin maintains `.last_pull_timestamp` files in each managed directory to track when pulls were last performed

## Configuration Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `g:autosync_dirs` | List | `[]` | List of directories to manage (supports `~` expansion) |
| `g:autosync_enabled` | Boolean | `1` | Enable/disable the plugin |
| `g:autosync_pull_interval` | Number | `60` | Seconds between automatic pulls |
| `g:autosync_commit_message_template` | String | `'Auto-sync: Updated %s'` | Template for commit messages (`%s` is replaced with relative file path) |
| `g:autosync_silent` | Boolean | `0` | Suppress status messages |
| `g:autosync_debug` | Boolean | `0` | Enable debug logging (shows detailed operation info) |

## Troubleshooting

### Plugin doesn't work
- Ensure Vim has Python 3 support: `:echo has('python3')`
- Install GitPython: `pip install GitPython`
- Check that your directories are Git repositories with configured remotes
- Enable debug mode to see what's happening: `let g:autosync_debug = 1`

### Seeing log messages at startup
- This is normal if you have `g:autosync_debug = 1` enabled
- To suppress all messages, set `let g:autosync_silent = 1`
- To disable debug logging, set `let g:autosync_debug = 0` (default)

### Git operations fail
- Ensure Git repositories are properly initialized
- Check that remote repositories are accessible
- Verify you have push permissions to the remote repository

### Performance issues
- Increase `g:autosync_pull_interval` to reduce pull frequency
- Enable `g:autosync_silent` to reduce message overhead

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Changelog

### v1.0.0
- Initial release
- Asynchronous git operations
- Configurable directories and intervals
- Manual commands for pull/push operations
- Comprehensive documentation
