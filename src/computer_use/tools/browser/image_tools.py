"""
Image generation tools for Browser-Use.
Provides AI image generation using Google Gemini for ads, marketing, and content.
Uses task-specific folders to isolate images per browser task.
"""

import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from browser_use import Tools, ActionResult
from ...utils.ui import dashboard, ActionType

MAX_IMAGES_PER_TASK = 10


class ImageTaskManager:
    """
    Manages task-specific image generation directories.
    Each browser task gets its own isolated folder for generated images.
    """

    _current_task_id: Optional[str] = None
    _current_task_dir: Optional[Path] = None
    _image_counter: int = 0

    @classmethod
    def start_new_task(cls, task_id: Optional[str] = None) -> str:
        """
        Initialize a new task-specific image directory.

        Args:
            task_id: Optional custom task ID. If not provided, generates one.

        Returns:
            The task ID for the new session.
        """
        if task_id is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_suffix = uuid.uuid4().hex[:8]
            task_id = f"task_{timestamp}_{unique_suffix}"

        base_dir = Path(tempfile.gettempdir()) / "browser_use_images"
        base_dir.mkdir(exist_ok=True)

        cls._current_task_id = task_id
        cls._current_task_dir = base_dir / task_id
        cls._current_task_dir.mkdir(exist_ok=True)
        cls._image_counter = 0

        return task_id

    @classmethod
    def get_current_task_dir(cls) -> Path:
        """
        Get the current task's image directory.
        Creates a new task if none exists.

        Returns:
            Path to the current task's image directory.
        """
        if cls._current_task_dir is None:
            cls.start_new_task()
        return cls._current_task_dir

    @classmethod
    def get_current_task_id(cls) -> Optional[str]:
        """
        Get the current task ID.

        Returns:
            Current task ID or None if no task is active.
        """
        return cls._current_task_id

    @classmethod
    def get_image_path(cls, slot: int) -> Path:
        """
        Get the path for a specific image slot in the current task.

        Args:
            slot: Image slot number (0 to MAX_IMAGES_PER_TASK-1)

        Returns:
            Path object for the image file.
        """
        return cls.get_current_task_dir() / f"generated_image_{slot:02d}.png"

    @classmethod
    def get_next_image_path(cls) -> Path:
        """
        Get the next available image path and increment counter.

        Returns:
            Path for the next image file.
        """
        slot = cls._image_counter % MAX_IMAGES_PER_TASK
        cls._image_counter += 1
        return cls.get_image_path(slot)

    @classmethod
    def get_all_image_paths(cls) -> List[str]:
        """
        Get all possible image paths for the current task (for whitelisting).
        These paths may or may not exist - they're just allowed upload paths.

        Returns:
            List of file paths that CAN be uploaded by the browser agent.
        """
        task_dir = cls.get_current_task_dir()
        return [
            str(task_dir / f"generated_image_{i:02d}.png")
            for i in range(MAX_IMAGES_PER_TASK)
        ]

    @classmethod
    def get_existing_image_paths(cls) -> List[str]:
        """
        Get only the image paths that actually exist for the current task.

        Returns:
            List of file paths for images that have been generated.
        """
        task_dir = cls.get_current_task_dir()
        existing = []
        for i in range(MAX_IMAGES_PER_TASK):
            img_path = task_dir / f"generated_image_{i:02d}.png"
            if img_path.exists():
                existing.append(str(img_path))
        return existing

    @classmethod
    def get_image_count(cls) -> int:
        """
        Get the count of images generated in the current task.

        Returns:
            Number of generated images.
        """
        return len(cls.get_existing_image_paths())

    @classmethod
    def end_task(cls) -> None:
        """
        End the current task session.
        Clears the current task reference but keeps files for the task duration.
        """
        cls._current_task_id = None
        cls._current_task_dir = None
        cls._image_counter = 0


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


def get_generated_image_paths() -> List[str]:
    """
    Get all pre-defined image slot paths for the current task.
    Used to whitelist files for browser upload.

    Returns:
        List of file paths that can be uploaded by the browser agent.
    """
    return ImageTaskManager.get_all_image_paths()


def initialize_task_images(task_id: Optional[str] = None) -> str:
    """
    Initialize image generation for a new browser task.
    Call this at the start of each browser task.

    Args:
        task_id: Optional custom task ID.

    Returns:
        The task ID for the new session.
    """
    return ImageTaskManager.start_new_task(task_id)


def cleanup_task_images() -> None:
    """
    Clean up after a browser task completes.
    Call this when the browser task ends.
    """
    ImageTaskManager.end_task()


def load_image_tools() -> Optional[Tools]:
    """
    Load image generation tools if Google API is configured.

    Returns:
        Tools object with image generation actions, or None if not configured.
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
        description="Generate an image using AI for ads, marketing, banners, or content creation. Each image gets a unique filename in the current task's folder."
    )
    def generate_image(prompt: str) -> ActionResult:
        """
        Generate an image from a text description using Google Gemini.
        Each image is saved in the current task's dedicated folder.
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

            output_path = ImageTaskManager.get_next_image_path()
            slug = _slugify(prompt)

            text_response = None
            for part in response.parts:
                if part.inline_data is not None:
                    image = part.as_image()
                    image.save(str(output_path))

                    task_id = ImageTaskManager.get_current_task_id() or "unknown"
                    dashboard.add_log_entry(
                        ActionType.COMPLETE,
                        f"Image generated ({slug}) [task: {task_id}]: {output_path}",
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

    @tools.action(
        description="Check if AI image generation is available and show the current task's image folder"
    )
    def check_image_generation_status() -> ActionResult:
        """
        Check if image generation is properly configured and ready to use.
        Shows the current task folder where images will be saved.

        Returns:
            ActionResult with configuration status and task folder info.
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

            task_dir = ImageTaskManager.get_current_task_dir()
            task_id = ImageTaskManager.get_current_task_id()
            return ActionResult(
                extracted_content=f"Image generation is configured and ready. Task ID: {task_id}. Images will be saved to: {task_dir}. Use generate_image(prompt) to create images."
            )
        except ImportError:
            return ActionResult(
                extracted_content="Image generation NOT available. google-genai package not installed.",
                error="google-genai not installed",
            )

    @tools.action(description="List all generated images in the current task folder")
    def list_generated_images() -> ActionResult:
        """
        List all images that have been generated for the current task.
        Useful to see what images are available for upload.

        Returns:
            ActionResult with list of generated image paths.
        """
        task_dir = ImageTaskManager.get_current_task_dir()
        task_id = ImageTaskManager.get_current_task_id()

        existing_images = []
        for i in range(MAX_IMAGES_PER_TASK):
            img_path = task_dir / f"generated_image_{i:02d}.png"
            if img_path.exists():
                existing_images.append(str(img_path))

        if existing_images:
            return ActionResult(
                extracted_content=f"Task '{task_id}' has {len(existing_images)} generated image(s):\n"
                + "\n".join(existing_images)
            )
        return ActionResult(
            extracted_content=f"No images have been generated yet for task '{task_id}'. Use generate_image(prompt) to create images."
        )

    return tools
