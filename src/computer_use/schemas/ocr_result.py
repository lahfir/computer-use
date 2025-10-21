"""
Type-safe schemas for OCR results.
"""

from typing import Tuple, Optional
from pydantic import BaseModel, Field


class OCRResult(BaseModel):
    """
    Structured OCR recognition result with bounding box and confidence.
    """

    text: str = Field(description="Recognized text content")
    bounds: Tuple[int, int, int, int] = Field(
        description="Bounding box as (x, y, width, height)"
    )
    center: Tuple[int, int] = Field(description="Center coordinates (x, y)")
    confidence: float = Field(
        description="Recognition confidence score between 0 and 1"
    )
    detection_method: Optional[str] = Field(
        default=None, description="Detection method used (ocr, vision, etc.)"
    )


class GPUInfo(BaseModel):
    """
    GPU availability and configuration information.
    """

    available: bool = Field(description="Whether GPU is available")
    type: Optional[str] = Field(
        default=None, description="GPU type (CUDA, Metal/MPS, etc.)"
    )
    device_count: int = Field(description="Number of GPU devices available", default=0)
