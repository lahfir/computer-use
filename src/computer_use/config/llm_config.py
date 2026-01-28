"""
Provider-agnostic LLM configuration system.
Supports Langchain LLMs for CrewAI agents and Browser-Use LLMs for web automation.
"""

import os
import sys
import warnings
from typing import Optional

warnings.filterwarnings("ignore", message=".*GOOGLE_API_KEY.*")
warnings.filterwarnings("ignore", message=".*GEMINI_API_KEY.*")

_original_stderr = sys.stderr


class _SuppressGoogleWarnings:
    """Suppress Google API key warnings written to stderr."""

    def write(self, msg):
        if "GOOGLE_API_KEY" not in msg and "GEMINI_API_KEY" not in msg:
            _original_stderr.write(msg)

    def flush(self):
        _original_stderr.flush()


sys.stderr = _SuppressGoogleWarnings()

from dotenv import load_dotenv  # noqa: E402
from crewai import LLM  # noqa: E402

from langchain_openai import ChatOpenAI  # noqa: E402
from langchain_anthropic import ChatAnthropic  # noqa: E402
from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: E402

sys.stderr = _original_stderr

load_dotenv()


class LLMConfig:
    """
    LLM configuration for all agents with singleton caching.
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

    _llm_cache: dict = {}
    _orchestration_cache: dict = {}
    _browser_cache: dict = {}
    _warmed_up: set = set()

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached LLM instances."""
        cls._llm_cache.clear()
        cls._orchestration_cache.clear()
        cls._browser_cache.clear()

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

        reasoning_effort = os.getenv("REASONING_EFFORT")
        if reasoning_effort and reasoning_effort not in [
            "none",
            "low",
            "medium",
            "high",
        ]:
            reasoning_effort = None

        cache_key = f"{provider}:{model_name}:{reasoning_effort or 'default'}"
        if cache_key in LLMConfig._llm_cache:
            return LLMConfig._llm_cache[cache_key]

        llm_timeout = int(os.getenv("LLM_TIMEOUT", "120"))

        from ..utils.ui import dashboard

        try:
            import litellm

            litellm.num_retries = 5
            litellm.request_timeout = 120
            if dashboard.is_verbose:
                litellm.set_verbose = True
        except ImportError:
            pass

        llm_kwargs = {
            "model": model_name,
            "api_key": api_key,
            "timeout": llm_timeout,
        }

        if reasoning_effort:
            llm_kwargs["reasoning_effort"] = reasoning_effort

        llm = LLM(**llm_kwargs)

        original_call = llm.call
        max_empty_retries = 3

        def robust_call(*args, **kwargs):
            import time

            for attempt in range(max_empty_retries):
                t0 = time.time()
                try:
                    result = original_call(*args, **kwargs)
                    if result is None or result == "":
                        if attempt < max_empty_retries - 1:
                            if dashboard.is_verbose:
                                print(
                                    f"[LLM EMPTY] {model_name} attempt {attempt + 1}, retrying..."
                                )
                            time.sleep(0.5 * (attempt + 1))
                            continue
                        if dashboard.is_verbose:
                            print(f"[LLM EMPTY] {model_name} all retries failed")
                        return "I apologize, but I couldn't generate a response. Please try again."
                    if dashboard.is_verbose:
                        print(f"[LLM OK] {model_name} ({time.time() - t0:.1f}s)")
                    return result
                except Exception as e:
                    if dashboard.is_verbose:
                        print(f"[LLM FAIL] {model_name}: {type(e).__name__}: {e}")
                    raise
            return "I apologize, but I couldn't generate a response. Please try again."

        llm.call = robust_call

        LLMConfig._llm_cache[cache_key] = llm
        return llm

    @classmethod
    def warmup_all_sync(cls) -> None:
        """
        Synchronously warm up all cached LLMs.

        Makes a test call to each LLM to establish the connection before
        any real tasks run. This prevents first-task delays.
        """
        import concurrent.futures

        llms_to_warmup = [
            (key, llm)
            for key, llm in cls._llm_cache.items()
            if key not in cls._warmed_up
        ]

        if not llms_to_warmup:
            return

        def warmup_single(item):
            key, llm = item
            try:
                llm.call(messages=[{"role": "user", "content": "Hi"}])
            except Exception:
                pass
            cls._warmed_up.add(key)
            return key

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(warmup_single, item) for item in llms_to_warmup]
            concurrent.futures.wait(futures, timeout=30.0)

    @classmethod
    def ensure_all_warmed_up(cls, timeout: float = 10.0) -> None:
        """
        Ensure all LLMs are warmed up synchronously.

        Args:
            timeout: Ignored, kept for API compatibility
        """
        cls.warmup_all_sync()

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

        cache_key = f"orch:{provider}:{model_name}"
        if cache_key in LLMConfig._orchestration_cache:
            return LLMConfig._orchestration_cache[cache_key]

        llm = None
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENAI_API_KEY not found. Please set it in your .env file."
                )
            llm = ChatOpenAI(model=model_name, api_key=api_key)
        elif provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY not found. Please set it in your .env file."
                )
            llm = ChatAnthropic(model=model_name, api_key=api_key)
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
                llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key)
            finally:
                if gemini_key_backup:
                    os.environ["GEMINI_API_KEY"] = gemini_key_backup
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENAI_API_KEY not found. Please set it in your .env file."
                )
            llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key)

        LLMConfig._orchestration_cache[cache_key] = llm
        return llm

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

        cache_key = f"browser:{provider}:{model}"
        if cache_key in LLMConfig._browser_cache:
            return LLMConfig._browser_cache[cache_key]

        llm = None
        if provider == "openai":
            from browser_use.llm.openai.chat import ChatOpenAI

            model_name = model or "gpt-4o-mini"
            llm = ChatOpenAI(model=model_name, api_key=os.getenv("OPENAI_API_KEY"))

        elif provider == "anthropic":
            from browser_use.llm.anthropic.chat import ChatAnthropic

            model_name = model or "claude-3-5-sonnet-20241022"
            llm = ChatAnthropic(
                model=model_name, api_key=os.getenv("ANTHROPIC_API_KEY")
            )

        elif provider == "google":
            from browser_use.llm.google.chat import ChatGoogle

            model_name = model or "gemini-2.0-flash-exp"
            llm = ChatGoogle(
                model=model_name,
                api_key=os.getenv("GOOGLE_API_KEY"),
                max_retries=5,
                retryable_status_codes=[403, 500, 502, 503, 504],
                retry_delay=1.0,
            )

        else:
            raise ValueError(f"Unsupported Browser-Use provider: {provider}")

        LLMConfig._browser_cache[cache_key] = llm
        return llm
