# diskscape

A small, dependency-free disk usage visualizer in Python: a treemap
that shows where your disk space is going.

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
- Color coding: folders get a fixed shade of blue per nesting depth
  (like SpaceMonger), files get a saturated color spread across the
  full color wheel per extension (stable per type)
- Hovering shows the full path + size in the status bar
- "Rescan" to re-scan after changes on disk

## Requirements

- Python 3.9+
- Tkinter (bundled with Python on Windows/macOS; on Linux sometimes a
  separate package: `sudo apt install python3-tk`)

No pip dependencies required.

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
- `main.py` - Tkinter GUI that ties the disk picker + scanner + treemap together

## Known limitations

- Symlinks are skipped (avoids double-counting / infinite loops)
- Very small files/folders (< 2px in the layout) are not drawn
- No delete functionality (by design: this is a viewer, not a cleaner)
