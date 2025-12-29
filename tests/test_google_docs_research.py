"""
Test for Google Docs research workflow.
Browser agent researches a topic, logs into Google, and creates a doc with findings.
"""

import os
import pytest
from dotenv import load_dotenv

load_dotenv()


class TestGoogleDocsResearch:
    """Integration test for research and Google Docs creation workflow."""

    @pytest.mark.asyncio
    async def test_research_and_add_to_google_docs(self):
        """
        Full E2E test: Research Kalshi.com -> Login to Google -> Create doc.

        This tests the browser agent's ability to:
        1. Perform web research on a topic
        2. Handle Google login
        3. Create and populate a new Google Doc with research findings
        """
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        google_key = os.getenv("GOOGLE_API_KEY")

        if not (anthropic_key or openai_key or google_key):
            pytest.skip("No LLM API key set")

        from computer_use.agents.browser_agent import BrowserAgent
        from computer_use.config.llm_config import LLMConfig

        print("\n" + "=" * 70)
        print("TEST: Research Kalshi.com and Add to Google Docs")
        print("=" * 70)

        browser_llm = LLMConfig.get_browser_llm()
        print(f"Browser LLM: {type(browser_llm).__name__}")

        browser_agent = BrowserAgent(
            llm_client=browser_llm,
            headless=False,
            gui_delegate=None,
        )

        assert browser_agent.available, "Browser agent should be available"

        task = """
        Do an intensive research about Kalshi.com. Login to this google account 
        and add the research to a new google doc.

        Credentials:
        Email: dream4billions@gmail.com
        Password: dream4billions@262001
        """

        print("\nTask Summary: Research -> Google Login -> Create Doc")
        print("=" * 70)
        print("\nExecuting browser task...")

        result = await browser_agent.execute_task(task)

        print("\n" + "=" * 70)
        print("RESULT:")
        print("=" * 70)
        print(f"Success: {result.success}")
        print(
            f"Action: {result.action_taken[:200] if result.action_taken else 'None'}..."
        )
        print(f"Error: {result.error}")
        if result.data:
            text = result.data.get("text", "")
            print(f"Output: {text[:800] if text else 'No text'}...")

        print("\n" + "=" * 70)

        assert result.success, f"Task should succeed. Error: {result.error}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
