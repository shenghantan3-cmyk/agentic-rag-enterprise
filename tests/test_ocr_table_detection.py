from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Import the OCR microservice's table detection module without requiring it to be
# installed as a package (the folder name contains a hyphen).
ROOT = Path(__file__).resolve().parents[1]
OCR_APP = ROOT / "deploy" / "enterprise" / "ocr-service" / "app"
sys.path.insert(0, str(OCR_APP))

from table_detection import BBox, TextBox, detect_table_layout  # noqa: E402


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
