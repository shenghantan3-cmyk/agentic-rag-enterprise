from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def h(self) -> float:
        return max(0.0, self.y1 - self.y0)


@dataclass(frozen=True)
class TextBox:
    text: str
    bbox: BBox


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    mid = len(vs) // 2
    if len(vs) % 2 == 1:
        return float(vs[mid])
    return float((vs[mid - 1] + vs[mid]) / 2.0)


def group_rows(boxes: Iterable[TextBox], *, y_tol: float) -> list[list[TextBox]]:
    """Group text boxes into rows by y-center."""
    rows: list[list[TextBox]] = []
    for b in sorted(boxes, key=lambda tb: tb.bbox.cy):
        if not rows:
            rows.append([b])
            continue
        last = rows[-1]
        last_y = _median([x.bbox.cy for x in last])
        if abs(b.bbox.cy - last_y) <= y_tol:
            last.append(b)
        else:
            rows.append([b])

    for r in rows:
        r.sort(key=lambda tb: tb.bbox.cx)
    return rows


def detect_table_layout(
    boxes: list[TextBox],
    *,
    min_rows: int = 3,
    min_cols: int = 3,
) -> bool:
    """Heuristic table detector.

    We consider a page "table-like" when:
    - it has at least `min_rows` rows (y-grouped text lines)
    - and at least `min_rows` of those rows contain >= `min_cols` boxes

    This is intentionally simple and fully offline-testable.
    """
    if len(boxes) < min_rows * min_cols:
        return False

    heights = [b.bbox.h for b in boxes if b.bbox.h > 0]
    med_h = _median(heights) or 10.0
    y_tol = max(8.0, med_h * 0.6)

    rows = group_rows(boxes, y_tol=y_tol)
    if len(rows) < min_rows:
        return False

    rich_rows = [r for r in rows if len(r) >= min_cols]
    return len(rich_rows) >= min_rows
