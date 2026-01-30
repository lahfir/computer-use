"""
Provider-agnostic image analysis tool for CrewAI.
Works with OpenAI, Anthropic, and Google Gemini vision models.
"""

import base64
import os

from crewai.tools import BaseTool
from pydantic import Field


class AnalyzeImageTool(BaseTool):
    """
    Analyze an image using vision-capable LLM.
    Works with OpenAI, Anthropic, and Google Gemini.
    """

    name: str = "analyze_image"
    description: str = (
        "Analyze an image and describe its contents. "
        "Pass the image file path to get a detailed description."
    )
    image_path: str = Field(
        default="",
        description="Path to the image file to analyze",
    )

    def _run(self, image_path: str = "") -> str:
        """
        Analyze an image and return a description.

        Args:
            image_path: Path to the image file

        Returns:
            Description of the image contents
        """
        if not image_path:
            return "Error: No image path provided"

        if not os.path.exists(image_path):
            return f"Error: Image file not found: {image_path}"

        try:
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            provider = os.getenv("VISION_LLM_PROVIDER") or os.getenv(
                "LLM_PROVIDER", "openai"
            )

            if provider == "google":
                return self._analyze_with_gemini(image_data, image_path)
            elif provider == "anthropic":
                return self._analyze_with_anthropic(image_data, image_path)
            else:
                return self._analyze_with_openai(image_data, image_path)

        except Exception as e:
            return f"Error analyzing image: {str(e)}"

    def _analyze_with_gemini(self, image_data: str, image_path: str) -> str:
        """Analyze image using Google Gemini."""
        from google import genai
        from google.genai import types

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            return "Error: GOOGLE_API_KEY or GEMINI_API_KEY not found"

        model_name = os.getenv("VISION_LLM_MODEL") or os.getenv(
            "LLM_MODEL", "gemini-2.0-flash-exp"
        )
        if model_name.startswith("gemini/"):
            model_name = model_name[7:]

        mime_type = self._get_mime_type(image_path)

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
                ),
                "Describe this image in detail. What do you see? "
                "Include any text, UI elements, and notable features.",
            ],
        )

        return response.text

    def _get_mime_type(self, image_path: str) -> str:
        """Get MIME type based on file extension."""
        ext = os.path.splitext(image_path)[1].lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        return mime_types.get(ext, "image/png")

    def _analyze_with_anthropic(self, image_data: str, image_path: str) -> str:
        """Analyze image using Anthropic Claude."""
        from anthropic import Anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return "Error: ANTHROPIC_API_KEY not found"

        client = Anthropic(api_key=api_key)

        model_name = os.getenv("VISION_LLM_MODEL") or "claude-3-5-sonnet-20241022"
        mime_type = self._get_mime_type(image_path)

        response = client.messages.create(
            model=model_name,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Describe this image in detail. What do you see? "
                            "Include any text, UI elements, and notable features.",
                        },
                    ],
                }
            ],
        )

        return response.content[0].text

    def _analyze_with_openai(self, image_data: str, image_path: str) -> str:
        """Analyze image using OpenAI GPT-4 Vision."""
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "Error: OPENAI_API_KEY not found"

        client = OpenAI(api_key=api_key)

        model_name = os.getenv("VISION_LLM_MODEL") or "gpt-4o"
        mime_type = self._get_mime_type(image_path)

        response = client.responses.create(
            model=model_name,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Describe this image in detail. What do you see? "
                            "Include any text, UI elements, and notable features.",
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{mime_type};base64,{image_data}",
                        },
                    ],
                }
            ],
        )

        return response.output_text
