"""diskscape - a disk usage treemap visualizer.

Usage:
    python main.py [path]

If no path is given, a disk/drive picker dialog opens listing the
available disks (drive letters on Windows, mount points on Linux/macOS)
so you scan a whole disk rather than browsing to a folder.

Rendering:
    - Nested treemap, SpaceMonger/WinDirStat-style: subfolders are drawn
      inside their parent's rectangle down to MAX_NEST_DEPTH levels (as
      long as there's room), each with its own caption header.
    - Every visible block (file or folder, at any nesting depth) gets a
      caption with its name and size when there's room to show one.
    - While a scan is running, the tree is redrawn from partial data
      every PREVIEW_REDRAW_MS milliseconds so structure appears
      progressively instead of only after the whole disk is done.
      Directories whose own listing isn't finished yet show "?" instead
      of a size and get a hatched fill.

Controls:
    - Click any block (file or folder, at any depth) - directories zoom
      in, replacing the view with that folder's contents.
    - "Back" / Backspace to go up one level.
    - Hover over a block to see its full path and size in the status bar.
    - "Rescan" to re-scan the current root from disk.
"""
from __future__ import annotations

import colorsys
import hashlib
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk

import scanner
from disks import Disk, list_disks
from scanner import Node, scan
from treemap import squarify

MIN_RECT_SIZE = 2       # px, below this we don't bother drawing at all
HEADER_H = 15           # px, height of a block's caption strip
NEST_MARGIN = 2         # px, inset between a parent block and its nested children
MIN_NEST_W = 50         # px, minimum block width to bother nesting children inside it
MIN_NEST_H = 34         # px, minimum block height to bother nesting children inside it
MAX_NEST_DEPTH = 4      # how many folder levels get drawn nested in one view

PROGRESS_POLL_MS = 250       # numeric progress bar / ETA refresh rate
PREVIEW_REDRAW_MS = 500      # full canvas redraw rate while a scan is running

# Depth-based shading for directory blocks (SpaceMonger/WinDirStat-style:
# folders get a distinct, consistent hue independent of their name so the
# nesting structure reads at a glance; each level a bit lighter).
DIR_DEPTH_COLORS = [
    "#2f4f76",  # depth 0
    "#3d6690",  # depth 1
    "#4c7dab",  # depth 2
    "#5c95c6",  # depth 3
    "#71addb",  # depth 4+
]
UNSCANNED_DIR_COLOR = "#555555"


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def human_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, s = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {s}s"
    hours, m = divmod(minutes, 60)
    return f"{hours}h {m}m"


def color_for_file(name: str) -> str:
    """A distinct, saturated color per file extension.

    Hue is derived from a hash of the extension and spread across the
    full color wheel (via HSV) so different types are easy to tell apart
    at a glance - much more varied than picking each RGB channel
    independently from a hash, which tends to produce muddy, similar
    grey-blues.
    """
    ext = os.path.splitext(name)[1].lower() or "<none>"
    h = hashlib.md5(ext.encode()).hexdigest()
    hue = (int(h[:4], 16) % 360) / 360.0
    sat = 0.55 + (int(h[4:6], 16) % 30) / 100.0    # 0.55-0.85
    val = 0.65 + (int(h[6:8], 16) % 25) / 100.0    # 0.65-0.90
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def color_for_dir(depth: int, scanned: bool) -> str:
    if not scanned:
        return UNSCANNED_DIR_COLOR
    idx = min(depth, len(DIR_DEPTH_COLORS) - 1)
    return DIR_DEPTH_COLORS[idx]


def color_for(node: Node, depth: int = 0) -> str:
    if node.is_dir:
        return color_for_dir(depth, node.scanned)
    return color_for_file(node.name)


def sizes_with_placeholders(children: list[Node]) -> list[float]:
    """Layout sizes for `children`, substituting a nominal size for
    directories that have no data yet (not scanned, size==0) so they
    still get a visible sliver in the treemap during a live preview
    instead of vanishing (squarify can't place zero-size items).
    """
    known = [c.size for c in children if c.size > 0]
    nominal = (sum(known) / len(known) * 0.15) if known else 64 * 1024
    return [c.size if c.size > 0 else nominal for c in children]


PROGRESS_POLL_MS = PROGRESS_POLL_MS  # keep name stable for readability below


class DiskscapeApp:
    def __init__(self, root: tk.Tk, start_path: str | None):
        self.root = root
        self.root.title("diskscape")
        self.root.geometry("1100x700")

        self.stack: list[Node] = []  # navigation history (zoom path)
        self.current: Node | None = None
        self.rects: list[tuple[Node, tuple[float, float, float, float]]] = []

        self._progress_lock = threading.Lock()
        self._latest_progress_path = ""
        self._progress_scheduled = False
        self._scan_poll_job: str | None = None
        self._preview_job: str | None = None
        self._scan_root_holder: dict = {}
        self._scan_expected_total: int | None = None
        self._scan_start_time: float = 0.0
        self._scanning = False

        self._build_ui()

        if start_path:
            self.start_scan(start_path)
        else:
            self.choose_disk()

    def _build_ui(self):
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        self.back_btn = ttk.Button(toolbar, text="< Back", command=self.go_back)
        self.back_btn.pack(side=tk.LEFT, padx=4, pady=4)

        ttk.Button(toolbar, text="Choose disk...", command=self.choose_disk).pack(
            side=tk.LEFT, padx=4, pady=4
        )
        ttk.Button(toolbar, text="Rescan", command=self.rescan).pack(
            side=tk.LEFT, padx=4, pady=4
        )

        self.path_label = ttk.Label(toolbar, text="")
        self.path_label.pack(side=tk.LEFT, padx=10)

        self.canvas = tk.Canvas(self.root, bg="#1e1e1e", highlightthickness=0)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_hover)

        self.progress_frame = ttk.Frame(self.root)
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, orient=tk.HORIZONTAL, mode="determinate", maximum=100
        )
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8), pady=4)
        self.progress_text = ttk.Label(self.progress_frame, text="", width=42, anchor="w")
        self.progress_text.pack(side=tk.LEFT, padx=(0, 8))
        # progress_frame is hidden until a scan starts; packed/unpacked in
        # _start_progress_ui / _stop_progress_ui

        self.status = ttk.Label(self.root, text="Ready", anchor="w")
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        self.root.bind("<BackSpace>", lambda e: self.go_back())

    def choose_disk(self):
        disks = list_disks()
        if not disks:
            self.status.config(text="No disks detected.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Choose a disk to scan")
        dialog.geometry("420x320")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Select a disk:").pack(anchor="w", padx=8, pady=(8, 0))

        listbox = tk.Listbox(dialog, activestyle="dotbox")
        listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        for d in disks:
            pct = (d.used / d.total * 100) if d.total else 0
            listbox.insert(
                tk.END,
                f"{d.name}   {human_size(d.used)} / {human_size(d.total)} used ({pct:.0f}%)",
            )
        if disks:
            listbox.selection_set(0)

        def confirm(event=None):
            sel = listbox.curselection()
            if not sel:
                return
            chosen = disks[sel[0]]
            dialog.destroy()
            self.start_scan(chosen.path)

        def cancel():
            dialog.destroy()
            if self.current is None:
                self.root.destroy()

        listbox.bind("<Double-Button-1>", confirm)
        listbox.bind("<Return>", confirm)

        btns = ttk.Frame(dialog)
        btns.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(btns, text="Scan", command=confirm).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Cancel", command=cancel).pack(side=tk.RIGHT, padx=(0, 6))

        dialog.protocol("WM_DELETE_WINDOW", cancel)
        listbox.focus_set()

    # ---- scanning -----------------------------------------------------

    def start_scan(self, path: str):
        # If we know how much data this path represents (e.g. it's a
        # whole disk we just listed via list_disks()), use that as the
        # denominator for a determinate progress bar + ETA. Otherwise
        # fall back to an indeterminate "busy" bar with just elapsed time.
        expected_total = self._expected_total_for(path)

        self.status.config(text=f"Scanning {path} ...")
        self.canvas.delete("all")
        self._scanning = True
        self._scan_root_holder = {}
        self._start_progress_ui(expected_total)
        self._schedule_preview_redraw()

        def worker():
            root_node = scan(
                path, progress_cb=self._on_progress, root_holder=self._scan_root_holder
            )
            self.root.after(0, lambda: self._on_scan_done(root_node))

        threading.Thread(target=worker, daemon=True).start()

    def _expected_total_for(self, path: str) -> int | None:
        try:
            for d in list_disks():
                if os.path.abspath(d.path) == os.path.abspath(path):
                    return d.used
        except OSError:
            pass
        return None

    def _schedule_preview_redraw(self):
        self._preview_job = self.root.after(PREVIEW_REDRAW_MS, self._preview_tick)

    def _preview_tick(self):
        if not self._scanning:
            return
        node = self._scan_root_holder.get("node")
        if node is not None:
            self.current = node
            self.stack = [node]
            self.redraw()
        self._schedule_preview_redraw()

    def _start_progress_ui(self, expected_total: int | None):
        self._scan_expected_total = expected_total
        self._scan_start_time = time.monotonic()
        self.progress_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self.status)

        if expected_total:
            self.progress_bar.config(mode="determinate", maximum=100, value=0)
            self.progress_text.config(text=f"0% - {human_size(0)} / {human_size(expected_total)}")
        else:
            self.progress_bar.config(mode="indeterminate")
            self.progress_bar.start(12)
            self.progress_text.config(text="0 B scanned")

        self._schedule_progress_poll()

    def _schedule_progress_poll(self):
        self._scan_poll_job = self.root.after(PROGRESS_POLL_MS, self._poll_scan_progress)

    def _poll_scan_progress(self):
        node = self._scan_root_holder.get("node")
        scanned = node.size if node is not None else 0
        elapsed = time.monotonic() - self._scan_start_time

        if self._scan_expected_total:
            pct = min(scanned / self._scan_expected_total, 1.0) * 100
            self.progress_bar.config(value=pct)
            eta_text = ""
            if pct > 1 and elapsed > 1:
                rate = scanned / elapsed  # bytes/sec
                if rate > 0:
                    remaining = max(self._scan_expected_total - scanned, 0)
                    eta_text = f" - ETA {human_duration(remaining / rate)}"
            self.progress_text.config(
                text=(
                    f"{pct:.0f}% - {human_size(scanned)} / "
                    f"{human_size(self._scan_expected_total)}{eta_text}"
                )
            )
        else:
            self.progress_text.config(
                text=f"{human_size(scanned)} scanned - {human_duration(elapsed)} elapsed"
            )

        self._schedule_progress_poll()

    def _stop_progress_ui(self):
        if self._scan_poll_job is not None:
            self.root.after_cancel(self._scan_poll_job)
            self._scan_poll_job = None
        if self._preview_job is not None:
            self.root.after_cancel(self._preview_job)
            self._preview_job = None
        self.progress_bar.stop()
        self.progress_frame.pack_forget()

    def _on_progress(self, path: str):
        # Called concurrently from up to N scanner worker threads. Tkinter
        # itself must only be touched from the main thread, so we just
        # stash the latest path and schedule at most one pending
        # self.root.after() call to coalesce a flood of updates into a
        # single UI refresh instead of spamming the Tcl event queue.
        with self._progress_lock:
            self._latest_progress_path = path
            if self._progress_scheduled:
                return
            self._progress_scheduled = True
        self.root.after(0, self._flush_progress)

    def _flush_progress(self):
        with self._progress_lock:
            path = self._latest_progress_path
            self._progress_scheduled = False
        self.status.config(text=f"Scanning: {path}")

    def _on_scan_done(self, root_node: Node):
        self._scanning = False
        self._stop_progress_ui()
        self.stack = [root_node]
        self.current = root_node
        self.status.config(text=f"Done. {human_size(root_node.size)} total.")
        self.redraw()

    def rescan(self):
        if self.stack:
            self.start_scan(self.stack[0].path)

    def go_back(self):
        if len(self.stack) > 1:
            self.stack.pop()
            self.current = self.stack[-1]
            self.redraw()

    def zoom_into(self, node: Node):
        if node.is_dir and (node.children or not node.scanned):
            self.stack.append(node)
            self.current = node
            self.redraw()

    # ---- rendering ------------------------------------------------------

    def _children_of(self, node: Node) -> list[Node]:
        """Thread-safe-ish snapshot of a node's children.

        While a scan is running, another thread may still be appending to
        node.children, so go through scanner.snapshot_children() with the
        scan's shared lock. Once scanning is finished the tree is static
        and a plain list() copy is enough.
        """
        if self._scanning:
            lock = self._scan_root_holder.get("lock")
            if lock is not None:
                return scanner.snapshot_children(node, lock)
        return list(node.children)

    def redraw(self):
        self.canvas.delete("all")
        self.rects = []
        if self.current is None:
            return

        self.path_label.config(text=self.current.path)
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10:
            return

        self._layout_and_draw_children(self.current, 0, 0, w, h, depth=0)

    def _layout_and_draw_children(self, node: Node, x: float, y: float, w: float, h: float, depth: int):
        children = self._children_of(node)
        children = sorted(children, key=lambda c: c.size, reverse=True)
        if not children:
            if depth == 0:
                self.canvas.create_text(
                    self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2,
                    text="(empty)" if node.scanned else "(scanning...)", fill="white",
                )
            return

        sizes = sizes_with_placeholders(children)
        placed = squarify(sizes, x, y, w, h)
        for child, (rx, ry, rw, rh) in zip(children, placed):
            if rw < MIN_RECT_SIZE or rh < MIN_RECT_SIZE:
                continue
            self._draw_node(child, rx, ry, rw, rh, depth)

    def _draw_node(self, node: Node, x: float, y: float, w: float, h: float, depth: int):
        color = color_for(node, depth)
        self.canvas.create_rectangle(
            x, y, x + w, y + h, fill=color, outline="#111111"
        )
        self.rects.append((node, (x, y, w, h)))

        if w > 30 and h > 11:
            if node.is_dir and not node.scanned:
                label = f"{node.name}  ?"
            else:
                label = f"{node.name}  {human_size(node.size)}"
            self.canvas.create_text(
                x + 4, y + 2, text=label, anchor="nw", fill="white",
                font=("TkDefaultFont", 8), width=max(w - 8, 10),
            )

        if (
            node.is_dir
            and depth + 1 < MAX_NEST_DEPTH
            and w >= MIN_NEST_W
            and h >= MIN_NEST_H
        ):
            inner_x = x + NEST_MARGIN
            inner_y = y + HEADER_H
            inner_w = w - 2 * NEST_MARGIN
            inner_h = h - HEADER_H - NEST_MARGIN
            if inner_w > 4 and inner_h > 4:
                self._layout_and_draw_children(node, inner_x, inner_y, inner_w, inner_h, depth + 1)

    def _node_at(self, x: float, y: float) -> Node | None:
        # Rects are appended parent-before-child, so children (deeper
        # nesting, drawn on top) come later in the list. Walk in reverse
        # to hit the innermost/topmost block first.
        for node, (rx, ry, rw, rh) in reversed(self.rects):
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return node
        return None

    def on_click(self, event):
        node = self._node_at(event.x, event.y)
        if node:
            self.zoom_into(node)

    def on_hover(self, event):
        node = self._node_at(event.x, event.y)
        if node:
            kind = "dir" if node.is_dir else "file"
            size_text = human_size(node.size) if (node.scanned or not node.is_dir) else "? (scanning)"
            self.status.config(text=f"[{kind}] {node.path}  -  {size_text}")


def main():
    start_path = sys.argv[1] if len(sys.argv) > 1 else None
    root = tk.Tk()
    DiskscapeApp(root, start_path)
    root.mainloop()


if __name__ == "__main__":
    main()
