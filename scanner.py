"""Recursive disk usage scanner.

Builds a tree of Node objects, each holding a size (bytes) and children.
Designed to be resilient to permission errors and broken symlinks.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Node:
    name: str
    path: str
    is_dir: bool
    size: int = 0
    children: list["Node"] = field(default_factory=list)

    def sorted_children(self) -> list["Node"]:
        return sorted(self.children, key=lambda n: n.size, reverse=True)


def scan(path: str, progress_cb=None) -> Node:
    """Scan `path` recursively and return the root Node.

    progress_cb(path: str) is called for every directory entered, so a UI
    can show "scanning: ..." feedback during a long scan.
    """
    path = os.path.abspath(path)
    name = os.path.basename(path) or path
    root = Node(name=name, path=path, is_dir=True)
    _scan_dir(root, progress_cb)
    return root


def _scan_dir(node: Node, progress_cb) -> None:
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
                child = Node(name=entry.name, path=entry.path, is_dir=True)
                _scan_dir(child, progress_cb)
                node.children.append(child)
                node.size += child.size
            elif entry.is_file(follow_symlinks=False):
                try:
                    size = entry.stat(follow_symlinks=False).st_size
                except OSError:
                    size = 0
                child = Node(name=entry.name, path=entry.path, is_dir=False, size=size)
                node.children.append(child)
                node.size += size
        except (PermissionError, FileNotFoundError, OSError):
            continue
