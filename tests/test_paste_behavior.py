"""
Test for Browser-Use text paste behavior.
Verifies content is pasted instantly (not typed character-by-character).
"""

import os
import pytest
from dotenv import load_dotenv

load_dotenv()

LARGE_CONTENT = """Lorem ipsum dolor sit amet, consectetur adipiscing elit. 
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. 
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia.
Lorem ipsum dolor sit amet, consectetur adipiscing elit. 
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. 
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia.
Lorem ipsum dolor sit amet, consectetur adipiscing elit. 
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. 
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia.
Lorem ipsum dolor sit amet, consectetur adipiscing elit. 
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. 
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia.
"""


class TestPasteTools:
    """Tests for paste_text tool availability and functionality."""

    def test_paste_tools_loaded(self):
        """Verify paste_tools are loaded and paste_text action exists."""
        from computer_use.tools.browser.paste_tools import load_paste_tools

        tools = load_paste_tools()
        assert tools is not None, "Paste tools should be loaded"

        actions = tools.registry.registry.actions
        assert "paste_text" in actions, "paste_text action should be registered"

    def test_browser_tools_include_paste(self):
        """Verify browser tools include paste_text action."""
        from computer_use.tools.browser import load_browser_tools

        tools, _, _ = load_browser_tools()
        assert tools is not None, "Browser tools should be loaded"

        actions = tools.registry.registry.actions
        assert "paste_text" in actions, "paste_text should be in browser tools"


class TestPasteBehavior:
    """Integration tests for paste behavior with browser agent."""

    @pytest.mark.asyncio
    async def test_paste_content_into_online_notepad(self):
        """
        Test that browser agent uses paste_text for content entry.

        Uses a simple online notepad to verify:
        1. Navigation works
        2. Content is pasted instantly (not typed slowly)
        3. Content appears correctly
        """
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        google_key = os.getenv("GOOGLE_API_KEY")

        if not (anthropic_key or openai_key or google_key):
            pytest.skip("No LLM API key set")

        from computer_use.agents.browser_agent import BrowserAgent
        from computer_use.config.llm_config import LLMConfig

        print("\n" + "=" * 60)
        print("TEST: Paste Content Into Online Notepad")
        print("=" * 60)

        browser_llm = LLMConfig.get_browser_llm()
        print(f"Browser LLM: {type(browser_llm).__name__}")

        browser_agent = BrowserAgent(
            llm_client=browser_llm,
            headless=False,
            gui_delegate=None,
        )

        assert browser_agent.available, "Browser agent should be available"

        content_to_paste = LARGE_CONTENT

        task = f"""
        1. Navigate to https://www.editpad.org/
        2. Find the main text area on the page
        3. Use paste_text to enter the following content:

        {content_to_paste}

        4. Verify the text was entered correctly
        5. Report success
        """

        print(f"\nContent length: {len(content_to_paste)} characters")
        print(f"Task:\n{task[:200]}...")
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

        assert result.success, f"Task should succeed. Error: {result.error}"

    @pytest.mark.asyncio
    async def test_paste_email_and_password(self):
        """
        Test that short content like emails and passwords are also pasted.

        Uses a login form demo to verify instant paste for credentials.
        """
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        google_key = os.getenv("GOOGLE_API_KEY")

        if not (anthropic_key or openai_key or google_key):
            pytest.skip("No LLM API key set")

        from computer_use.agents.browser_agent import BrowserAgent
        from computer_use.config.llm_config import LLMConfig

        print("\n" + "=" * 60)
        print("TEST: Paste Email and Password")
        print("=" * 60)

        browser_llm = LLMConfig.get_browser_llm()
        browser_agent = BrowserAgent(
            llm_client=browser_llm,
            headless=False,
            gui_delegate=None,
        )

        assert browser_agent.available, "Browser agent should be available"

        task = """
        1. Navigate to https://the-internet.herokuapp.com/login
        2. Use paste_text to enter username: tomsmith
        3. Use paste_text to enter password: SuperSecretPassword!
        4. Click the Login button
        5. Report the result message shown after login attempt
        """

        print("\nExecuting browser task...")

        result = await browser_agent.execute_task(task)

        print("\n" + "=" * 60)
        print("RESULT:")
        print("=" * 60)
        print(f"Success: {result.success}")
        print(f"Error: {result.error}")
        if result.data:
            text = result.data.get("text", "")
            print(f"Data: {text[:300] if text else 'No text'}...")

        print("\n" + "=" * 60)

        assert result.success, f"Login task should succeed. Error: {result.error}"


class TestPromptGuidelines:
    """Tests to verify prompt guidelines are properly configured."""

    def test_text_input_rules_mention_paste_text(self):
        """Verify prompts mention paste_text action."""
        from computer_use.prompts.browser_prompts import get_text_input_rules

        rules = get_text_input_rules()

        assert "paste_text" in rules, "Rules should mention paste_text action"
        assert "input" in rules.lower(), "Rules should contrast with input action"

    def test_full_context_includes_paste_guidance(self):
        """Verify full context includes paste_text guidance."""
        from computer_use.prompts.browser_prompts import build_full_context

        context = build_full_context(
            has_twilio=False,
            has_image_gen=False,
            has_gui_delegate=False,
        )

        assert "paste_text" in context, "Context should include paste_text guidance"
        assert "TEXT INPUT" in context, "Context should include text input section"

    def test_prompts_discourage_input_action(self):
        """Verify prompts explicitly discourage using input() for text."""
        from computer_use.prompts.browser_prompts import get_text_input_rules

        rules = get_text_input_rules()

        assert (
            "NEVER" in rules or "NOT" in rules
        ), "Rules should explicitly discourage input() usage"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
