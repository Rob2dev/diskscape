"""Live folder watching via the `watchdog` package, with debouncing.

`watchdog` is an optional dependency: importing this module never raises
even when it's missing (HAS_WATCHDOG is False in that case), so the rest
of the app runs fine without it - only the "Watch this folder" feature
is unavailable.

A single change event from a big operation (extracting an archive,
copying a folder) fires dozens/hundreds of filesystem events in quick
succession. DirWatcher coalesces them: `change_cb` is called at most
once per DEBOUNCE_SECONDS of quiet, not once per event, so a caller
doing a full re-scan on each callback doesn't scan the same subtree
dozens of times in a row.
"""
from __future__ import annotations

import threading

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    Observer = None  # type: ignore[assignment,misc]
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    HAS_WATCHDOG = False

DEBOUNCE_SECONDS = 1.0


class _DebouncedHandler(FileSystemEventHandler):
    def __init__(self, change_cb):
        super().__init__()
        self._change_cb = change_cb
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def on_any_event(self, event):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self):
        with self._lock:
            self._timer = None
        self._change_cb()

    def stop(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None


class DirWatcher:
    """Watches one directory tree recursively and calls `change_cb()`
    (no arguments, from a background thread) after activity settles.

    Only meaningful when HAS_WATCHDOG is True; raises RuntimeError from
    start() otherwise so a caller can't silently no-op.
    """

    def __init__(self, path: str, change_cb):
        if not HAS_WATCHDOG:
            raise RuntimeError("watchdog is not installed")
        self.path = path
        self._handler = _DebouncedHandler(change_cb)
        self._observer = Observer()

    def start(self):
        self._observer.schedule(self._handler, self.path, recursive=True)
        self._observer.start()

    def stop(self):
        self._handler.stop()
        self._observer.stop()
        self._observer.join(timeout=2)
