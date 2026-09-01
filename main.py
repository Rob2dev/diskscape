"""diskmonger - a SpaceMonger-style disk usage visualizer.

Usage:
    python main.py [path]

If no path is given, a folder picker dialog opens.

Controls:
    - Click a directory rectangle to zoom into it.
    - "Back" / Backspace to go up one level.
    - Hover over a rectangle to see its full path and size in the status bar.
    - "Rescan" to re-scan the current root from disk.
"""
from __future__ import annotations

import hashlib
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from scanner import Node, scan
from treemap import squarify

MIN_RECT_SIZE = 2  # px, below this we don't bother drawing/labeling


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def color_for(node: Node) -> str:
    if node.is_dir:
        return "#3a5f8a"
    ext = os.path.splitext(node.name)[1].lower()
    if not ext:
        ext = "<none>"
    # stable hash-based color per extension so the same type is always
    # the same color across scans/sessions
    h = hashlib.md5(ext.encode()).hexdigest()
    r = 90 + int(h[0:2], 16) % 140
    g = 90 + int(h[2:4], 16) % 140
    b = 90 + int(h[4:6], 16) % 140
    return f"#{r:02x}{g:02x}{b:02x}"


class DiskMongerApp:
    def __init__(self, root: tk.Tk, start_path: str | None):
        self.root = root
        self.root.title("diskmonger")
        self.root.geometry("1100x700")

        self.stack: list[Node] = []  # navigation history (zoom path)
        self.current: Node | None = None
        self.rects: list[tuple[Node, tuple[float, float, float, float]]] = []

        self._build_ui()

        if start_path:
            self.start_scan(start_path)
        else:
            self.choose_folder()

    def _build_ui(self):
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        self.back_btn = ttk.Button(toolbar, text="< Back", command=self.go_back)
        self.back_btn.pack(side=tk.LEFT, padx=4, pady=4)

        ttk.Button(toolbar, text="Open folder...", command=self.choose_folder).pack(
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

        self.status = ttk.Label(self.root, text="Ready", anchor="w")
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        self.root.bind("<BackSpace>", lambda e: self.go_back())

    def choose_folder(self):
        path = filedialog.askdirectory(title="Choose a folder to scan")
        if path:
            self.start_scan(path)
        elif self.current is None:
            self.root.destroy()

    def start_scan(self, path: str):
        self.status.config(text=f"Scanning {path} ...")
        self.canvas.delete("all")

        def worker():
            root_node = scan(path, progress_cb=self._on_progress)
            self.root.after(0, lambda: self._on_scan_done(root_node))

        threading.Thread(target=worker, daemon=True).start()

    def _on_progress(self, path: str):
        # called from the scanner thread; keep it cheap
        self.root.after(0, lambda: self.status.config(text=f"Scanning: {path}"))

    def _on_scan_done(self, root_node: Node):
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
        if node.is_dir and node.children:
            self.stack.append(node)
            self.current = node
            self.redraw()

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

        children = self.current.sorted_children()
        sizes = [c.size for c in children if c.size > 0]
        nodes = [c for c in children if c.size > 0]
        if not sizes:
            self.canvas.create_text(
                w / 2, h / 2, text="(empty)", fill="white"
            )
            return

        placed = squarify(sizes, 0, 0, w, h)
        for node, (rx, ry, rw, rh) in zip(nodes, placed):
            if rw < MIN_RECT_SIZE or rh < MIN_RECT_SIZE:
                continue
            color = color_for(node)
            rect_id = self.canvas.create_rectangle(
                rx, ry, rx + rw, ry + rh, fill=color, outline="#111111"
            )
            self.rects.append((node, (rx, ry, rw, rh)))
            if rw > 40 and rh > 14:
                label = f"{node.name}\n{human_size(node.size)}"
                self.canvas.create_text(
                    rx + 4, ry + 4, text=label, anchor="nw", fill="white",
                    font=("TkDefaultFont", 8), width=max(rw - 8, 10),
                )

    def _node_at(self, x: float, y: float) -> Node | None:
        for node, (rx, ry, rw, rh) in self.rects:
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
            self.status.config(text=f"[{kind}] {node.path}  -  {human_size(node.size)}")


def main():
    start_path = sys.argv[1] if len(sys.argv) > 1 else None
    root = tk.Tk()
    DiskMongerApp(root, start_path)
    root.mainloop()


if __name__ == "__main__":
    main()
