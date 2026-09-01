"""Squarified treemap layout algorithm (Bruls, Huizing, van Wijk, 1999).

Pure Python, no dependencies. Takes a list of (item, size) and a rectangle,
returns a list of (item, (x, y, w, h)).
"""
from __future__ import annotations


def squarify(sizes: list[float], x: float, y: float, w: float, h: float) -> list[tuple[float, float, float, float]]:
    """Return a rectangle (x, y, w, h) for each size in `sizes`.

    `sizes` must be sorted descending and contain only positive values.
    """
    if not sizes:
        return []
    total = sum(sizes)
    if total <= 0:
        return []

    # scale sizes to the rectangle's area
    area = w * h
    scaled = [s / total * area for s in sizes]

    rects: list[tuple[float, float, float, float]] = []
    remaining = list(scaled)
    rx, ry, rw, rh = x, y, w, h

    while remaining:
        side = min(rw, rh)
        row, rest = _best_row(remaining, side)
        row_rects, rx, ry, rw, rh = _layout_row(row, rx, ry, rw, rh)
        rects.extend(row_rects)
        remaining = rest

    return rects


def _worst_ratio(row: list[float], side: float) -> float:
    s = sum(row)
    if s == 0:
        return float("inf")
    row_max = max(row)
    row_min = min(row)
    side2 = side * side
    return max((side2 * row_max) / (s * s), (s * s) / (side2 * row_min))


def _best_row(sizes: list[float], side: float):
    row = [sizes[0]]
    for i in range(1, len(sizes)):
        candidate = row + [sizes[i]]
        if _worst_ratio(candidate, side) <= _worst_ratio(row, side):
            row = candidate
        else:
            break
    return row, sizes[len(row):]


def _layout_row(row: list[float], x: float, y: float, w: float, h: float):
    s = sum(row)
    rects = []
    if w >= h:
        # lay out row as a vertical strip on the left, width = s / h
        strip_w = s / h if h > 0 else 0
        cy = y
        for size in row:
            rh = size / strip_w if strip_w > 0 else 0
            rects.append((x, cy, strip_w, rh))
            cy += rh
        return rects, x + strip_w, y, w - strip_w, h
    else:
        strip_h = s / w if w > 0 else 0
        cx = x
        for size in row:
            rw = size / strip_h if strip_h > 0 else 0
            rects.append((cx, y, rw, strip_h))
            cx += rw
        return rects, x, y + strip_h, w, h - strip_h
