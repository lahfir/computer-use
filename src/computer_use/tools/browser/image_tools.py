"""
Image generation tools for Browser-Use.
Provides AI image generation using Google Gemini for ads, marketing, and content.
"""

import os
import re
import tempfile
from pathlib import Path
from typing import List, Optional

from browser_use import Tools, ActionResult
from ...utils.ui import dashboard, ActionType

IMAGE_GEN_DIR = Path(tempfile.gettempdir()) / "browser_use_generated_images"
IMAGE_GEN_DIR.mkdir(exist_ok=True)

MAX_IMAGES = 10
_image_counter = 0


def _slugify(text: str, max_length: int = 30) -> str:
    """
    Convert text to a safe filename slug.

    Args:
        text: Input text to slugify
        max_length: Maximum length of the slug

    Returns:
        Safe filename string
    """
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[-\s]+", "_", slug).strip("_")
    return slug[:max_length]


def _get_image_slot_path(slot: int) -> Path:
    """
    Get the path for a specific image slot.

    Args:
        slot: Image slot number (0 to MAX_IMAGES-1)

    Returns:
        Path object for the image file
    """
    return IMAGE_GEN_DIR / f"generated_image_{slot:02d}.png"


def get_generated_image_paths() -> List[str]:
    """
    Get all pre-defined image slot paths for whitelisting.

    Returns:
        List of file paths that can be uploaded by the browser agent
    """
    return [str(_get_image_slot_path(i)) for i in range(MAX_IMAGES)]


def load_image_tools() -> Optional[Tools]:
    """
    Load image generation tools if Google API is configured.

    Returns:
        Tools object with image generation actions, or None if not configured
    """
    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        return None

    return _create_image_tools(api_key)


def _create_image_tools(api_key: str) -> Tools:
    """
    Create Browser-Use tools for image generation.

    Args:
        api_key: Google API key for Gemini

    Returns:
        Tools instance with image generation actions
    """
    tools = Tools()

    @tools.action(
        description="Generate an image using AI for ads, marketing, banners, or content creation. Each image gets a unique filename based on the prompt."
    )
    def generate_image(prompt: str) -> ActionResult:
        """
        Generate an image from a text description using Google Gemini.
        Each image is saved with a unique filename based on prompt context.
        Use this when you need to create images for:
        - Google Ads or Facebook Ads
        - Marketing campaigns and banners
        - Product images or promotional content
        - Any form that requires uploading an image

        Args:
            prompt: Detailed description of the image to generate

        Returns:
            ActionResult with file path for upload_file action
        """
        try:
            from google import genai

            client = genai.Client(api_key=api_key)

            response = client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=[prompt],
            )

            global _image_counter
            slot = _image_counter % MAX_IMAGES
            _image_counter += 1

            output_path = _get_image_slot_path(slot)
            slug = _slugify(prompt)

            text_response = None
            for part in response.parts:
                if part.inline_data is not None:
                    image = part.as_image()
                    image.save(str(output_path))

                    dashboard.add_log_entry(
                        ActionType.COMPLETE,
                        f"Image generated ({slug}): {output_path}",
                        status="complete",
                    )
                    return ActionResult(
                        extracted_content=f"Image generated successfully. Context: '{slug}'. Saved to: {output_path}",
                        long_term_memory=f"Generated image ({slug}) at: {output_path}",
                    )
                elif part.text is not None:
                    text_response = part.text

            if text_response:
                return ActionResult(
                    extracted_content=f"Image generation returned text instead of image: {text_response}",
                    error="No image in response",
                )

            return ActionResult(
                extracted_content="ERROR: No image data in response from Gemini",
                error="No image generated",
            )

        except ImportError:
            return ActionResult(
                extracted_content="ERROR: google-genai package not installed. Run: pip install google-genai",
                error="google-genai not installed",
            )
        except Exception as e:
            return ActionResult(
                extracted_content=f"ERROR: Image generation failed - {str(e)}",
                error=str(e),
            )

    @tools.action(description="Check if AI image generation is available")
    def check_image_generation_status() -> ActionResult:
        """
        Check if image generation is properly configured and ready to use.

        Returns:
            ActionResult with configuration status
        """
        if not api_key:
            return ActionResult(
                extracted_content="Image generation is NOT available. GOOGLE_API_KEY not configured.",
                error="API key not configured",
            )

        try:
            import importlib.util

            if importlib.util.find_spec("google.genai") is None:
                raise ImportError("google-genai not found")

            return ActionResult(
                extracted_content="Image generation is configured and ready. Use generate_image(prompt) to create images."
            )
        except ImportError:
            return ActionResult(
                extracted_content="Image generation NOT available. google-genai package not installed.",
                error="google-genai not installed",
            )

    return tools
