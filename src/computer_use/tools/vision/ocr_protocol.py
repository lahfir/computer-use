"""
Protocol definition for OCR engines.
Ensures type safety and consistent interface across all OCR implementations.
"""

from typing import Protocol, List, Optional, Tuple
from PIL import Image
from ...schemas.ocr_result import OCRResult


class OCREngine(Protocol):
    """
    Protocol defining the interface that all OCR engines must implement.
    Ensures type safety and compatibility across different OCR backends.
    """

    def is_available(self) -> bool:
        """
        Check if the OCR engine is available and properly initialized.

        Returns:
            True if engine is available and ready to use
        """
        ...

    def recognize_text(
        self,
        image: Image.Image,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> List[OCRResult]:
        """
        Recognize text in image with bounding boxes and confidence scores.

        Args:
            image: PIL Image to process
            region: Optional region to crop (x, y, width, height)

        Returns:
            List of OCRResult objects with text, bounding boxes, and confidence
        """
        ...
