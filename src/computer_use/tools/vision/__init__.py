"""
Tier 2: Computer vision and OCR tools for element detection.
"""

from .ocr_tool import OCRTool
from .template_matcher import TemplateMatcher
from .element_detector import ElementDetector
from .ocr_protocol import OCREngine
from .ocr_factory import create_ocr_engine, detect_gpu_availability

__all__ = [
    "OCRTool",
    "TemplateMatcher",
    "ElementDetector",
    "OCREngine",
    "create_ocr_engine",
    "detect_gpu_availability",
]
