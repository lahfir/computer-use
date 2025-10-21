"""
Element detection result models.
"""

from typing import Tuple, Optional, Literal
from pydantic import BaseModel, Field


class DetectedElement(BaseModel):
    """
    Represents a detected UI element from CV/OCR.
    """

    element_type: Literal["text", "visual"] = Field(
        description="Type of element (text or visual)"
    )
    label: Optional[str] = Field(default=None, description="Text label of the element")
    role: Optional[str] = Field(default=None, description="Accessibility role")
    bounds: Tuple[int, int, int, int] = Field(
        description="Bounding box (x, y, width, height)"
    )
    center: Tuple[int, int] = Field(description="Center coordinates (x, y)")
    confidence: float = Field(description="Detection confidence (0-1)")
    detection_method: Literal["ocr", "cv", "accessibility"] = Field(
        description="Method used for detection"
    )
