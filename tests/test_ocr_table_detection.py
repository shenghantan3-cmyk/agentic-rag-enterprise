from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

# Import the OCR microservice's table detection module without requiring it to be
# installed as a package (the folder name contains a hyphen).
#
# IMPORTANT: Avoid mutating sys.path (e.g. inserting the OCR app dir at index 0),
# because it can shadow the repo's `project/config.py` with the OCR service's
# `app/config.py` and break unrelated tests.
ROOT = Path(__file__).resolve().parents[1]
OCR_APP = ROOT / "deploy" / "enterprise" / "ocr-service" / "app"

_spec = importlib.util.spec_from_file_location(
    "ocr_service_table_detection", OCR_APP / "table_detection.py"
)
assert _spec and _spec.loader
_table_detection = importlib.util.module_from_spec(_spec)
# dataclasses requires module to be present in sys.modules during execution
sys.modules[_spec.name] = _table_detection
_spec.loader.exec_module(_table_detection)  # type: ignore[attr-defined]

BBox = _table_detection.BBox
TextBox = _table_detection.TextBox
detect_table_layout = _table_detection.detect_table_layout


class TestTableDetection(unittest.TestCase):
    def test_detect_table_layout_true(self) -> None:
        # 3 rows x 3 cols grid
        boxes: list[TextBox] = []
        for r in range(3):
            for c in range(3):
                x0 = 10 + c * 100
                y0 = 10 + r * 30
                boxes.append(TextBox(text=f"R{r}C{c}", bbox=BBox(x0, y0, x0 + 50, y0 + 15)))

        self.assertTrue(detect_table_layout(boxes))

    def test_detect_table_layout_false_sparse(self) -> None:
        boxes = [
            TextBox("hello", BBox(10, 10, 100, 25)),
            TextBox("world", BBox(10, 40, 100, 55)),
            TextBox("!", BBox(10, 70, 20, 85)),
        ]
        self.assertFalse(detect_table_layout(boxes))

    def test_detect_table_layout_false_two_columns(self) -> None:
        # Looks like 2-column article layout, not a table.
        boxes: list[TextBox] = []
        for r in range(6):
            # left column
            boxes.append(TextBox(text=f"L{r}", bbox=BBox(10, 10 + r * 20, 200, 25 + r * 20)))
            # right column
            boxes.append(TextBox(text=f"R{r}", bbox=BBox(320, 10 + r * 20, 520, 25 + r * 20)))

        self.assertFalse(detect_table_layout(boxes, min_cols=3))


if __name__ == "__main__":
    unittest.main()
