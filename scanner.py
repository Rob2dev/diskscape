"""Recursive disk usage scanner, parallelized with a thread pool.

Builds a tree of Node objects, each holding a size (bytes) and children.
Directory listings are I/O bound (syscalls release the GIL), so a bounded
pool of worker threads pulling from a shared queue scans many directories
concurrently instead of one at a time.

Design notes:
    - A shared queue.Queue holds directories still to be listed.
    - N worker threads pull from it; each lists one directory, creates
      child Nodes, immediately queues subdirectories for other workers,
      and adds file sizes to the node and all its ancestors.
    - This avoids the deadlock risk of recursively submitting work to a
      ThreadPoolExecutor and blocking on .result(): workers never wait on
      each other, they only ever pull independent, already-known work
      items from the queue.
"""
from __future__ import annotations

import os
import queue
import threading
from dataclasses import dataclass, field

DEFAULT_WORKERS = 16
_SENTINEL = object()


@dataclass
class Node:
    name: str
    path: str
    is_dir: bool
    size: int = 0
    children: list["Node"] = field(default_factory=list)
    parent: "Node | None" = field(default=None, repr=False, compare=False)

    def sorted_children(self) -> list["Node"]:
        return sorted(self.children, key=lambda n: n.size, reverse=True)


def scan(path: str, progress_cb=None, max_workers: int = DEFAULT_WORKERS, root_holder: dict | None = None) -> Node:
    """Scan `path` recursively and return the root Node.

    progress_cb(path: str) is called whenever a directory starts being
    listed (from a worker thread), so a UI can show "scanning: ..."
    feedback during a long scan.

    max_workers controls how many directories are listed in parallel.

    root_holder, if given, is a dict that gets root_holder['node'] set to
    the (still-being-populated) root Node immediately, before any
    scanning happens. This lets a caller running scan() in a background
    thread peek at node.size from another thread to show byte-progress
    while the scan is still running, without waiting for it to finish.
    node.size is updated under a lock but read here without one - fine
    for an approximate, frequently-refreshed progress display.
    """
    path = os.path.abspath(path)
    name = os.path.basename(path) or path
    root = Node(name=name, path=path, is_dir=True)
    if root_holder is not None:
        root_holder["node"] = root

    work: "queue.Queue" = queue.Queue()
    work.put(root)
    size_lock = threading.Lock()

    def add_size_upwards(node: Node, n: int) -> None:
        with size_lock:
            cur: Node | None = node
            while cur is not None:
                cur.size += n
                cur = cur.parent

    def process_dir(node: Node) -> None:
        if progress_cb:
            progress_cb(node.path)
        try:
            entries = list(os.scandir(node.path))
        except (PermissionError, FileNotFoundError, NotADirectoryError, OSError):
            return

        for entry in entries:
            try:
                if entry.is_symlink():
                    continue  # avoid double-counting / infinite loops
                if entry.is_dir(follow_symlinks=False):
                    child = Node(name=entry.name, path=entry.path, is_dir=True, parent=node)
                    with size_lock:
                        node.children.append(child)
                    work.put(child)
                elif entry.is_file(follow_symlinks=False):
                    try:
                        size = entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        size = 0
                    child = Node(name=entry.name, path=entry.path, is_dir=False, size=size, parent=node)
                    with size_lock:
                        node.children.append(child)
                    add_size_upwards(node, size)
            except (PermissionError, FileNotFoundError, OSError):
                continue

    def worker() -> None:
        while True:
            item = work.get()
            if item is _SENTINEL:
                work.task_done()
                return
            try:
                process_dir(item)
            finally:
                work.task_done()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max_workers)]
    for t in threads:
        t.start()

    work.join()  # wait until every queued directory has been processed

    for _ in threads:
        work.put(_SENTINEL)
    for t in threads:
        t.join()

    return root
