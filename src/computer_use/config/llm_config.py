"""
Provider-agnostic LLM configuration system.
Supports Langchain LLMs for CrewAI agents and Browser-Use LLMs for web automation.
"""

import os
from typing import Optional
from dotenv import load_dotenv
from crewai import LLM

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


class LLMConfig:
    """
    LLM configuration for all agents.
    Supports multiple providers: OpenAI, Anthropic, Google, Ollama.

    Environment Variables:
    - LLM_PROVIDER / LLM_MODEL: Default provider and model
    - VISION_LLM_PROVIDER / VISION_LLM_MODEL: Override for GUI vision tasks
    - BROWSER_LLM_PROVIDER / BROWSER_LLM_MODEL: Override for browser automation

    Agent LLM Usage:
    - General LLM: Coordinator and System agents (Langchain)
    - Vision LLM: GUI agent for screenshot analysis (Langchain)
    - Browser LLM: Browser agent for web automation (Browser-Use)
    """

    @staticmethod
    def get_llm(provider: Optional[str] = None, model: Optional[str] = None):
        """
        Get CrewAI LLM for agents (uses LiteLLM internally).

        Args:
            provider: LLM provider (openai, anthropic, google, ollama)
            model: Specific model name

        Returns:
            CrewAI LLM instance
        """
        provider = provider or os.getenv("LLM_PROVIDER", "openai")
        model_name = model or os.getenv("LLM_MODEL")

        if not model_name:
            default_models = {
                "openai": "gpt-4o-mini",
                "anthropic": "claude-3-5-sonnet-20241022",
                "google": "gemini-2.0-flash-exp",
                "ollama": "llama3",
            }
            model_name = default_models.get(provider, "gpt-4o-mini")

        # Format model name with provider prefix for LiteLLM
        if provider == "google" and not model_name.startswith("gemini/"):
            model_name = f"gemini/{model_name}"
        elif provider == "anthropic" and not model_name.startswith("anthropic/"):
            model_name = f"anthropic/{model_name}"
        elif provider == "openai" and "/" not in model_name:
            pass
        elif provider == "ollama" and not model_name.startswith("ollama/"):
            model_name = f"ollama/{model_name}"

        # Get API key and ensure it's in the environment
        api_key = None
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                os.environ["OPENAI_API_KEY"] = api_key
        elif provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                os.environ["ANTHROPIC_API_KEY"] = api_key
        elif provider == "google":
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if api_key:
                os.environ["GEMINI_API_KEY"] = api_key
                os.environ["GOOGLE_API_KEY"] = api_key

        if not api_key:
            raise ValueError(
                f"API key not found for provider '{provider}'. "
                f"Please set the appropriate environment variable in your .env file."
            )

        return LLM(model=model_name, api_key=api_key)

    @staticmethod
    def get_orchestration_llm(
        provider: Optional[str] = None, model: Optional[str] = None
    ):
        """
        Get LangChain LLM for orchestration (supports structured output).

        Args:
            provider: LLM provider (openai, anthropic, google)
            model: Specific model name

        Returns:
            LangChain LLM instance
        """
        provider = provider or os.getenv("LLM_PROVIDER", "openai")
        model_name = model or os.getenv("LLM_MODEL")

        if not model_name:
            default_models = {
                "openai": "gpt-4o-mini",
                "anthropic": "claude-3-5-sonnet-20241022",
                "google": "gemini-2.0-flash-exp",
            }
            model_name = default_models.get(provider, "gpt-4o-mini")

        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENAI_API_KEY not found. Please set it in your .env file."
                )
            return ChatOpenAI(model=model_name, api_key=api_key)
        elif provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY not found. Please set it in your .env file."
                )
            return ChatAnthropic(model=model_name, api_key=api_key)
        elif provider == "google":
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError(
                    "GOOGLE_API_KEY or GEMINI_API_KEY not found. Please set it in your .env file."
                )
            gemini_key_backup = os.environ.pop("GEMINI_API_KEY", None)
            if not os.getenv("GOOGLE_API_KEY"):
                os.environ["GOOGLE_API_KEY"] = api_key
            try:
                return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key)
            finally:
                if gemini_key_backup:
                    os.environ["GEMINI_API_KEY"] = gemini_key_backup
        else:
            # Fallback to OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENAI_API_KEY not found. Please set it in your .env file."
                )
            return ChatOpenAI(model="gpt-4o-mini", api_key=api_key)

    @staticmethod
    def get_vision_llm(provider: Optional[str] = None, model: Optional[str] = None):
        """
        Get vision-capable LLM for GUI screenshot analysis.

        Args:
            provider: LLM provider (openai, anthropic, google)
            model: Specific vision model name

        Returns:
            Vision-capable CrewAI LLM instance
        """
        provider = (
            provider
            or os.getenv("VISION_LLM_PROVIDER")
            or os.getenv("LLM_PROVIDER", "openai")
        )
        model_name = model or os.getenv("VISION_LLM_MODEL")

        if not model_name:
            default_vision_models = {
                "openai": "gpt-4o",
                "anthropic": "claude-3-5-sonnet-20241022",
                "google": "gemini-2.0-flash-exp",
            }
            model_name = default_vision_models.get(provider)

        return LLMConfig.get_llm(provider, model_name)

    @staticmethod
    def get_browser_llm(provider: Optional[str] = None, model: Optional[str] = None):
        """
        Get Browser-Use compatible LLM for web automation.
        Converts Langchain LLM to Browser-Use LLM wrapper.

        Args:
            provider: LLM provider (openai, anthropic, google)
            model: Specific model name

        Returns:
            Browser-Use LLM instance
        """
        provider = (
            provider
            or os.getenv("BROWSER_LLM_PROVIDER")
            or os.getenv("LLM_PROVIDER", "openai")
        )
        model = model or os.getenv("BROWSER_LLM_MODEL") or os.getenv("LLM_MODEL")

        if provider == "openai":
            from browser_use.llm.openai.chat import ChatOpenAI

            model_name = model or "gpt-4o-mini"
            return ChatOpenAI(model=model_name, api_key=os.getenv("OPENAI_API_KEY"))

        elif provider == "anthropic":
            from browser_use.llm.anthropic.chat import ChatAnthropic

            model_name = model or "claude-3-5-sonnet-20241022"
            return ChatAnthropic(
                model=model_name, api_key=os.getenv("ANTHROPIC_API_KEY")
            )

        elif provider == "google":
            from browser_use.llm.google.chat import ChatGoogle

            model_name = model or "gemini-2.0-flash-exp"
            return ChatGoogle(model=model_name, api_key=os.getenv("GOOGLE_API_KEY"))

        else:
            raise ValueError(f"Unsupported Browser-Use provider: {provider}")
