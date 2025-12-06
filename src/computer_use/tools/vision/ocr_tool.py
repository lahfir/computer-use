"""
OCR tool for text detection with precise coordinates.
"""

from typing import List, Optional, Tuple
from PIL import Image
from .ocr_factory import create_ocr_engine, get_all_available_ocr_engines
from .ocr_protocol import OCREngine
from ...schemas.ocr_result import OCRResult


class OCRTool:
    """
    Text detection with precise bounding box coordinates.
    Uses platform-optimized OCR engines with automatic fallback.
    """

    def __init__(self, use_gpu: Optional[bool] = None):
        """
        Initialize OCR tool with optimal engine for platform.

        Args:
            use_gpu: Whether to use GPU. If None, auto-detect.
        """
        self.engine: Optional[OCREngine] = None
        self.fallback_engines: List[OCREngine] = []
        self._initialize_engine(use_gpu)

    def _initialize_engine(self, use_gpu: Optional[bool]) -> None:
        """
        Initialize platform-optimized OCR engine and fallbacks.

        Args:
            use_gpu: Whether to use GPU
        """
        self.engine = create_ocr_engine(use_gpu=use_gpu)
        self.fallback_engines = get_all_available_ocr_engines(use_gpu=use_gpu)

    def find_text(
        self,
        screenshot: Image.Image,
        target_text: str,
        region: Optional[Tuple[int, int, int, int]] = None,
        fuzzy: bool = True,
    ) -> List[OCRResult]:
        """
        Find text in screenshot and return exact bounding boxes.
        Automatically tries fallback engines if primary fails.

        Args:
            screenshot: PIL Image to search
            target_text: Text to find
            region: Optional region to search (x, y, width, height)
            fuzzy: Whether to allow partial matches

        Returns:
            List of OCRResult objects with text and bounding boxes
        """
        if not self.fallback_engines:
            return []

        for engine in self.fallback_engines:
            try:
                results = engine.recognize_text(screenshot, region=region)

                if not results or len(results) == 0:
                    continue

                matches = []
                target_lower = target_text.lower()

                for result in results:
                    text = result.text
                    text_lower = text.lower()
                    confidence = result.confidence

                    if fuzzy:
                        if len(text_lower) < 3:
                            is_match = text_lower == target_lower
                        else:
                            is_match = (
                                target_lower in text_lower or text_lower in target_lower
                            )
                    else:
                        is_match = text_lower == target_lower

                    if is_match and confidence > 0.5:
                        matches.append(
                            OCRResult(
                                text=text,
                                bounds=result.bounds,
                                center=result.center,
                                confidence=confidence,
                                detection_method="ocr",
                            )
                        )

                if matches:
                    return matches

            except Exception:
                continue

        return []

    def extract_all_text(self, screenshot: Image.Image) -> List[OCRResult]:
        """
        Extract all text from screenshot with coordinates.
        Automatically tries fallback engines if primary fails.

        Args:
            screenshot: PIL Image to analyze

        Returns:
            List of all detected OCRResult objects with coordinates
        """
        if not self.fallback_engines:
            return []

        for engine in self.fallback_engines:
            try:
                results = engine.recognize_text(screenshot, region=None)

                if not results or len(results) == 0:
                    continue

                extracted = [result for result in results if result.confidence > 0.3]

                if extracted:
                    return extracted

            except Exception:
                continue

        return []
