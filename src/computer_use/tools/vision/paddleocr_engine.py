"""
PaddleOCR engine for fast OCR on Windows/Linux.
Supports GPU acceleration and CPU fallback.
"""

from typing import List, Optional, Tuple
from PIL import Image
import numpy as np
from ...schemas.ocr_result import OCRResult


class PaddleOCREngine:
    """
    Fast OCR using PaddleOCR with GPU/CPU support.
    Significantly faster than EasyOCR while maintaining accuracy.
    """

    def __init__(self, use_gpu: bool = None):
        """
        Initialize PaddleOCR engine.

        Args:
            use_gpu: Whether to use GPU (ignored, auto-detected by PaddleOCR).
        """
        self.ocr = None
        self._initialize_paddle()

    def _detect_gpu(self) -> bool:
        """
        Detect if GPU is available for PaddleOCR.

        Returns:
            True if GPU is available
        """
        try:
            import paddle

            return (
                paddle.device.is_compiled_with_cuda()
                and paddle.device.cuda.device_count() > 0
            )
        except (ImportError, Exception):
            return False

    def _initialize_paddle(self):
        """
        Initialize PaddleOCR with appropriate settings.
        """
        try:
            from paddleocr import PaddleOCR

            self.ocr = PaddleOCR(
                use_textline_orientation=True,
                lang="en",
            )
        except ImportError:
            print(
                "PaddleOCR not available. Install with: pip install paddleocr paddlepaddle"
            )
            self.ocr = None
        except Exception as e:
            print(f"Failed to initialize PaddleOCR: {e}")
            self.ocr = None

    def is_available(self) -> bool:
        """
        Check if PaddleOCR is available.

        Returns:
            True if PaddleOCR is available
        """
        return self.ocr is not None

    def recognize_text(
        self,
        image: Image.Image,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> List[OCRResult]:
        """
        Recognize text in image using PaddleOCR.

        Args:
            image: PIL Image to process
            region: Optional region to crop (x, y, width, height)

        Returns:
            List of OCRResult objects with text, bounding boxes, and confidence
        """
        if not self.ocr:
            return []

        if region:
            x, y, w, h = region
            image = image.crop((x, y, x + w, y + h))
            offset_x, offset_y = x, y
        else:
            offset_x, offset_y = 0, 0

        img_array = np.array(image)

        try:
            result = self.ocr.predict(img_array)

            if not result or len(result) == 0:
                return []

            page_result = result[0] if isinstance(result, list) else result
            if not page_result or len(page_result) == 0:
                return []

            results = []

            for line in page_result:
                bbox = line[0]
                text_info = line[1]
                text = text_info[0]
                confidence = float(text_info[1])

                x_coords = [point[0] for point in bbox]
                y_coords = [point[1] for point in bbox]

                x_min = int(min(x_coords)) + offset_x
                y_min = int(min(y_coords)) + offset_y
                x_max = int(max(x_coords)) + offset_x
                y_max = int(max(y_coords)) + offset_y

                width = x_max - x_min
                height = y_max - y_min

                center_x = x_min + width // 2
                center_y = y_min + height // 2

                results.append(
                    OCRResult(
                        text=text,
                        bounds=(x_min, y_min, width, height),
                        center=(center_x, center_y),
                        confidence=confidence,
                    )
                )

            return results

        except Exception:
            return []
