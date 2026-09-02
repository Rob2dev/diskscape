# diskscape

A small disk usage visualizer in Python: a treemap that shows where
your disk space is going.

## Features

- Pick a disk/drive from a list at startup (drive letters on Windows,
  mount points on Linux/macOS) - no folder browser
- Parallel scan: multiple directories read concurrently via a
  thread pool (I/O-bound syscalls release the GIL, so this helps
  mainly on network drives or slow disks)
- Live preview while scanning: the canvas is rebuilt every 500ms
  from whatever is known so far. Directories that haven't finished
  scanning yet show a grey block with "?" instead of a size, so you
  see structure appear immediately instead of staring at an empty bar
- Progress bar with percentage and ETA during the scan. For a
  whole-disk scan it uses the known "used" total (via disk_usage) as
  the denominator; for a plain path with no known total it shows an
  indeterminate bar with elapsed time and bytes scanned
- Nested treemap, SpaceMonger/WinDirStat-style: subfolders are drawn
  up to 5 levels deep inside their parent folder (as long as there's
  room), each with its own name/size caption
- Every visible block - file or folder, at any level - is clickable:
  click to zoom in (with a short grow animation), Backspace / "Back"
  to shrink back to the parent folder
- Label text color adapts to the block's fill color (dark text on
  light/yellow fills, light text on dark fills) so captions stay
  readable regardless of hue
- Color coding: folders get a fixed shade of blue per nesting depth
  (like SpaceMonger), files get a saturated color spread across the
  full color wheel per extension (stable per type)
- Hovering shows the full path + size in the status bar, draws a bright
  outline around the folder block under the cursor for clear visual
  feedback, and after a short delay shows a tooltip popup with name,
  path, type, size and item count (for folders)
- Right-click a block for a context menu: open / zoom in, open
  containing folder, copy path/name/size, hide, watch/stop watching
- "Hide" a block via the context menu to declutter a view; "Show all"
  in the toolbar brings back everything hidden in the current tree
- "Find folder" search box in the toolbar: case-insensitive substring
  match over folder names, Enter / "Find next" cycles through matches
  and jumps the view straight to each one
- "Watch this folder" (context menu, on a directory): live-monitors
  that folder for filesystem changes (requires the optional
  `watchdog` package) and automatically re-scans + redraws just that
  subtree in place after activity settles, without resetting your
  current zoom/navigation. Only one folder can be watched at a time;
  the toolbar shows a green "watching: <name>" indicator while active
- "Rescan" to re-scan the whole current root from disk
- Canvas resize (e.g. maximizing the window) is debounced so a burst
  of resize events triggers one redraw, not several

## Requirements

- Python 3.9+
- Tkinter (bundled with Python on Windows/macOS; on Linux sometimes a
  separate package: `sudo apt install python3-tk`)

No pip dependencies required for core functionality. Optional:

- `watchdog` - only needed for the "Watch this folder" live-monitoring
  feature (`pip install watchdog`). Without it, everything else works
  normally; the watch menu item just explains it needs the package.

## Usage

```bash
python main.py                # opens a disk picker
python main.py /path/to/dir   # scans that path directly (optional, e.g. for scripting)
python main.py C:\            # Windows: scan a drive directly
```

## Files

- `disks.py` - disk/drive detection (Windows drive letters, Linux/macOS mount points via /proc/mounts)
- `scanner.py` - recursive disk scan into a Node tree
- `treemap.py` - squarified treemap layout algorithm (pure Python)
- `watcher.py` - optional live folder watching via `watchdog`, with debouncing
- `main.py` - Tkinter GUI that ties everything together

## Known limitations

- Symlinks are skipped (avoids double-counting / infinite loops)
- Very small files/folders (< 2px in the layout) are not drawn
- No delete functionality (by design: this is a viewer, not a cleaner)
- Only one folder can be watched at a time
- On Linux, watching a very large tree can hit the OS's inotify watch
  limit (`fs.inotify.max_user_watches`); watch a subfolder rather than
  an entire large disk if you hit this
