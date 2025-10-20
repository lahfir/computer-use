"""
Vision model direct coordinate extraction as last resort.
"""

from typing import Optional
from PIL import Image
import base64
import io


class VisionCoordinateTool:
    """
    Last resort: Extract coordinates directly from vision LLM.
    Lower accuracy but works on any visual interface.
    """

    def __init__(self, llm_client=None):
        """
        Initialize vision coordinate tool.

        Args:
            llm_client: Vision-capable LLM client
        """
        self.llm_client = llm_client

    async def get_coordinates(
        self, screenshot: Image.Image, semantic_target: dict, validator=None
    ) -> Optional[dict]:
        """
        Get coordinates from vision model with validation.

        Args:
            screenshot: Screenshot image
            semantic_target: Semantic description of target
            validator: CoordinateValidator instance

        Returns:
            Element dictionary with coordinates or None
        """
        if not self.llm_client:
            return None

        image_base64 = self._image_to_base64(screenshot)

        description = semantic_target.get("description", "")
        location_hint = semantic_target.get("location_hint", "")

        prompt = f"""
Analyze this screenshot and locate the following UI element:

Element: {description}
Location hint: {location_hint}

Return the exact center coordinates where this element can be clicked.
The image size is {screenshot.width}x{screenshot.height} pixels.

Respond with coordinates in the format: x,y
For example: 450,300
"""

        try:
            response = await self._query_vision_model(prompt, image_base64)

            x, y = self._parse_coordinates(response)

            if validator:
                is_valid, error = validator.validate_coordinates(x, y, strict=False)
                if not is_valid:
                    print(f"Coordinate validation failed: {error}")
                    return None

            bounds = (x - 20, y - 20, 40, 40)

            return {
                "element_type": "vision",
                "label": description,
                "role": None,
                "bounds": bounds,
                "center": (x, y),
                "confidence": 0.7,
                "detection_method": "vision",
            }

        except Exception as e:
            print(f"Vision coordinate extraction failed: {e}")
            return None

    def _image_to_base64(self, image: Image.Image) -> str:
        """
        Convert PIL Image to base64 string.
        """
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode("utf-8")

    async def _query_vision_model(self, prompt: str, image_base64: str) -> str:
        """
        Query vision model with image and prompt.

        This is a placeholder. In production, integrate with
        actual LLM API (OpenAI GPT-4V, Claude, etc.)
        """
        if self.llm_client:
            return "500,300"

        return "500,300"

    def _parse_coordinates(self, response: str) -> tuple:
        """
        Parse coordinate response from vision model.

        Args:
            response: Model response string

        Returns:
            Tuple of (x, y) coordinates
        """
        cleaned = response.strip()

        if "," in cleaned:
            parts = cleaned.split(",")
            x = int(parts[0].strip())
            y = int(parts[1].strip())
            return (x, y)

        raise ValueError(f"Could not parse coordinates from: {response}")
