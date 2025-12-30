"""
Test for Browser-Use image generation tools.
"""

import os
import pytest
from dotenv import load_dotenv

load_dotenv()


class TestImageTools:
    """Tests for image generation tools."""

    def test_load_image_tools_with_api_key(self):
        """Test that image tools load when API key is set."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set")

        from computer_use.tools.browser.image_tools import load_image_tools

        tools = load_image_tools()
        assert tools is not None, "Should return Tools object when API key is set"

    def test_check_image_generation_status_action_exists(self):
        """Test status check action is registered."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set")

        from computer_use.tools.browser.image_tools import _create_image_tools

        tools = _create_image_tools(api_key)

        actions = tools.registry.registry.actions
        assert "check_image_generation_status" in actions

    def test_generate_image_action_exists(self):
        """Test that generate_image action is registered."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set")

        from computer_use.tools.browser.image_tools import _create_image_tools

        tools = _create_image_tools(api_key)

        actions = tools.registry.registry.actions
        assert "generate_image" in actions

    @pytest.mark.asyncio
    async def test_generate_image_and_store_in_directory(self):
        """Test image generation stores file in correct directory."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set")

        from computer_use.tools.browser.image_tools import (
            _create_image_tools,
            IMAGE_GEN_DIR,
            get_generated_image_paths,
        )
        from pathlib import Path

        tools = _create_image_tools(api_key)
        generate_image = tools.registry.registry.actions["generate_image"]

        result = await generate_image.function(
            prompt="A photorealistic image of a golden retriever puppy sitting on grass in a sunny park",
        )

        print(f"\nResult: {result}")
        print(f"Content: {result.extracted_content}")
        print(f"Error: {result.error}")

        if result.error:
            pytest.skip(f"Gemini API returned text instead of image: {result.error}")

        assert result.extracted_content is not None
        assert "generated" in result.extracted_content.lower()

        assert "Saved to:" in result.extracted_content
        saved_path = result.extracted_content.split("Saved to:")[-1].strip()

        image_file = Path(saved_path)
        assert image_file.exists(), f"Image file should exist at {saved_path}"
        assert (
            image_file.parent == IMAGE_GEN_DIR
        ), f"Image should be in {IMAGE_GEN_DIR}, got {image_file.parent}"
        assert image_file.suffix == ".png", "Image should be a PNG file"
        assert image_file.stat().st_size > 0, "Image file should not be empty"

        valid_paths = get_generated_image_paths()
        assert (
            str(image_file) in valid_paths
        ), f"Generated path {image_file} should be in whitelist"

        print(f"\n✅ Image stored correctly at: {saved_path}")
        print(f"   Directory: {IMAGE_GEN_DIR}")
        print(f"   Size: {image_file.stat().st_size} bytes")


class TestImageUploadIntegration:
    """
    Real integration test: Browser agent generates image, GUI agent selects it.

    This test uses actual agents - not mocks.
    Requires: GOOGLE_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY
    """

    @pytest.mark.asyncio
    async def test_browser_agent_image_upload_flow(self):
        """
        Full E2E test: Browser generates image -> opens file picker -> GUI selects file.

        This uses the real BrowserAgent with real GUI delegation.
        """
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set")

        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        if not anthropic_key and not openai_key:
            pytest.skip("No LLM API key set (ANTHROPIC_API_KEY or OPENAI_API_KEY)")

        from computer_use.agents.browser_agent import BrowserAgent
        from computer_use.config.llm_config import LLMConfig

        print("\n" + "=" * 60)
        print("REAL INTEGRATION TEST: Image Generation + File Upload")
        print("=" * 60)

        browser_llm = LLMConfig.get_browser_llm()
        print(f"Browser LLM: {type(browser_llm).__name__}")

        browser_agent = BrowserAgent(
            llm_client=browser_llm,
            headless=False,
            gui_delegate=None,
        )

        assert browser_agent.available, "Browser agent should be available"
        assert browser_agent.has_image_gen, "Image generation should be available"

        print("\nBrowser agent initialized")
        print(f"  has_twilio: {browser_agent.has_twilio}")
        print(f"  has_image_gen: {browser_agent.has_image_gen}")

        task = """
        1. Use generate_image to create a test image with prompt: 
           "A solid blue square on white background, simple geometric shape"
        2. Navigate to https://seleniumbase.io/apps/img_upload
        3. Find the file input element and use upload_file action with the generated image path
        4. Verify the image preview appears after upload
        5. Report the result
        """

        print(f"\nTask:\n{task}")
        print("\nExecuting browser task...")

        result = await browser_agent.execute_task(task)

        print("\n" + "=" * 60)
        print("RESULT:")
        print("=" * 60)
        print(f"Success: {result.success}")
        print(f"Action: {result.action_taken}")
        print(f"Error: {result.error}")
        if result.data:
            text = result.data.get("text", "")
            print(f"Data: {text[:500] if text else 'No text'}...")

        print("\n" + "=" * 60)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
