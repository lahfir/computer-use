"""
Element detector combining semantic guidance with CV/OCR.
"""

from typing import Optional, Dict, Any, List, Tuple
from PIL import Image
from .ocr_tool import OCRTool
from .template_matcher import TemplateMatcher
from ...schemas.element_result import DetectedElement


class ElementDetector:
    """
    Semantic to CV pipeline for accurate element location.
    Uses vision model guidance to direct CV/OCR tools.
    """

    def __init__(self, ocr_tool: Optional[OCRTool] = None):
        """
        Initialize element detector.

        Args:
            ocr_tool: Optional pre-initialized OCRTool to avoid double initialization
        """
        self.ocr_tool = ocr_tool if ocr_tool is not None else OCRTool()
        self.template_matcher = TemplateMatcher()

    async def locate_element(
        self,
        screenshot: Image.Image,
        semantic_target: Dict[str, Any],
        ocr_tool: Optional[OCRTool] = None,
        template_matcher: Optional[TemplateMatcher] = None,
    ) -> Optional[DetectedElement]:
        """
        Locate an element using semantic description + CV/OCR.

        Args:
            screenshot: Screenshot image
            semantic_target: Semantic description from vision LLM
            ocr_tool: OCR tool instance (optional)
            template_matcher: Template matcher instance (optional)

        Returns:
            DetectedElement with coordinates or None
        """
        ocr = ocr_tool or self.ocr_tool
        matcher = template_matcher or self.template_matcher

        text_content = semantic_target.get("text_content")
        if text_content:
            results = ocr.find_text(screenshot, text_content, fuzzy=True)

            if results:
                best_match = max(results, key=lambda r: r.confidence)

                if best_match.confidence > 0.6:
                    return DetectedElement(
                        element_type="text",
                        label=best_match.text,
                        role=None,
                        bounds=best_match.bounds,
                        center=best_match.center,
                        confidence=best_match.confidence,
                        detection_method="ocr",
                    )

        color_hint = semantic_target.get("color_hint")
        if color_hint:
            color_ranges = self._parse_color_hint(color_hint)

            for color_range in color_ranges:
                elements = matcher.find_by_color(screenshot, color_range, min_area=100)

                if elements:
                    best = max(elements, key=lambda e: e["confidence"])

                    return DetectedElement(
                        element_type="visual",
                        label=None,
                        role=None,
                        bounds=best["bounds"],
                        center=best["center"],
                        confidence=best["confidence"],
                        detection_method="cv",
                    )

        return None

    def _parse_color_hint(
        self, color_hint: str
    ) -> List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]:
        """
        Parse color hint string into HSV ranges.

        Args:
            color_hint: Color description (red, blue, green, etc.)

        Returns:
            List of HSV color ranges
        """
        color_hint_lower = color_hint.lower()

        color_map = {
            "red": [
                ((0, 100, 100), (10, 255, 255)),
                ((170, 100, 100), (180, 255, 255)),
            ],
            "blue": [((100, 100, 100), (130, 255, 255))],
            "green": [((40, 100, 100), (80, 255, 255))],
            "yellow": [((20, 100, 100), (40, 255, 255))],
            "orange": [((10, 100, 100), (20, 255, 255))],
            "purple": [((130, 100, 100), (170, 255, 255))],
        }

        for color_name, ranges in color_map.items():
            if color_name in color_hint_lower:
                return ranges

        return []
