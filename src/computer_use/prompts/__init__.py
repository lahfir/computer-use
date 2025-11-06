"""
Centralized prompt templates for all agents.
"""

from .browser_prompts import BROWSER_AGENT_GUIDELINES
from .coordinator_prompts import COORDINATOR_SYSTEM_PROMPT

__all__ = ["BROWSER_AGENT_GUIDELINES", "COORDINATOR_SYSTEM_PROMPT"]
