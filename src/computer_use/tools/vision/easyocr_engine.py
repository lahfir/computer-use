"""
EasyOCR engine wrapper as fallback option.
Maintains compatibility with legacy systems.
"""

from typing import List, Optional, Tuple
from PIL import Image
import numpy as np
from ...schemas.ocr_result import OCRResult


class EasyOCREngine:
    """
    EasyOCR wrapper for fallback compatibility.
    Slower but widely compatible.
    """

    def __init__(self):
        """
        Initialize EasyOCR engine.
        """
        self.reader = None
        self._initialize_reader()

    def _initialize_reader(self):
        """
        Initialize EasyOCR reader.
        """
        try:
            import warnings
            import logging
            from contextlib import redirect_stdout, redirect_stderr
            from io import StringIO

            warnings.filterwarnings("ignore")
            logging.getLogger("easyocr").setLevel(logging.ERROR)

            f = StringIO()
            with redirect_stdout(f), redirect_stderr(f):
                import easyocr

                self.reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        except ImportError:
            self.reader = None

    def is_available(self) -> bool:
        """
        Check if EasyOCR is available.

        Returns:
            True if EasyOCR is available
        """
        return self.reader is not None

    def recognize_text(
        self,
        image: Image.Image,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> List[OCRResult]:
        """
        Recognize text in image using EasyOCR.

        Args:
            image: PIL Image to process
            region: Optional region to crop (x, y, width, height)

        Returns:
            List of OCRResult objects with text, bounding boxes, and confidence
        """
        if self.reader is None:
            return []

        if region:
            x, y, w, h = region
            image = image.crop((x, y, x + w, y + h))
            offset_x, offset_y = x, y
        else:
            offset_x, offset_y = 0, 0

        img_array = np.array(image)

        try:
            results_raw = self.reader.readtext(img_array)
        except Exception:
            return []

        results = []

        for bbox, text, confidence in results_raw:
            top_left = bbox[0]
            bottom_right = bbox[2]

            x = int(top_left[0]) + offset_x
            y = int(top_left[1]) + offset_y
            width = int(bottom_right[0] - top_left[0])
            height = int(bottom_right[1] - top_left[1])

            center_x = x + width // 2
            center_y = y + height // 2

            results.append(
                OCRResult(
                    text=text,
                    bounds=(x, y, width, height),
                    center=(center_x, center_y),
                    confidence=confidence,
                )
            )

        return results
