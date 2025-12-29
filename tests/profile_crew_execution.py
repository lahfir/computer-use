"""
Profiling script for CrewAI GUI Agent execution.
Traces all LLM calls, tool calls, timing, and outputs.
"""

import asyncio
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

os.environ["CREWAI_TELEMETRY"] = "false"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ExecutionProfiler:
    """Profiles all calls during crew execution."""

    def __init__(self):
        self.start_time = None
        self.tool_calls: List[Dict[str, Any]] = []
        self.llm_calls: List[Dict[str, Any]] = []

    def log_tool(self, name: str, duration: float, inputs: str, output: str):
        """Log a tool call."""
        entry = {
            "name": name,
            "duration": duration,
            "timestamp": time.time() - self.start_time if self.start_time else 0,
            "inputs": inputs,
            "output": output,
        }
        self.tool_calls.append(entry)

    def log_llm(self, duration: float, prompt_len: int, response_len: int):
        """Log an LLM call."""
        entry = {
            "duration": duration,
            "timestamp": time.time() - self.start_time if self.start_time else 0,
            "prompt_len": prompt_len,
            "response_len": response_len,
        }
        self.llm_calls.append(entry)

    def start(self):
        """Start profiling."""
        self.start_time = time.time()
        self.tool_calls = []
        self.llm_calls = []

    def print_summary(self):
        """Print profiling summary."""
        total_time = time.time() - self.start_time if self.start_time else 0

        print("\n" + "=" * 80)
        print("EXECUTION PROFILE SUMMARY")
        print("=" * 80)

        print(f"\nTotal execution time: {total_time:.2f}s")

        tool_time = sum(c["duration"] for c in self.tool_calls)
        llm_time = sum(c["duration"] for c in self.llm_calls)

        print(f"\nTOOL CALLS: {len(self.tool_calls)}, Total time: {tool_time:.2f}s")
        print(f"LLM CALLS: {len(self.llm_calls)}, Total time: {llm_time:.2f}s")

        if self.tool_calls:
            print("\n--- ALL TOOL CALLS (chronological) ---")
            for i, call in enumerate(self.tool_calls):
                print(f"\n  {i+1}. [{call['duration']:.2f}s] {call['name']}")
                print(f"      Inputs: {call['inputs'][:100]}")
                print(f"      Output: {call['output'][:150]}")

        if self.llm_calls:
            print("\n--- ALL LLM CALLS ---")
            for i, call in enumerate(self.llm_calls):
                print(
                    f"  {i+1}. [{call['duration']:.2f}s] prompt={call['prompt_len']} -> response={call['response_len']}"
                )

        print("\n--- SLOWEST TOOL CALLS ---")
        sorted_tools = sorted(
            self.tool_calls, key=lambda x: x["duration"], reverse=True
        )
        for call in sorted_tools[:5]:
            print(f"  [{call['duration']:.2f}s] {call['name']}")

        print("\n" + "=" * 80)


profiler = ExecutionProfiler()


def patch_gui_tools(gui_tools: Dict[str, Any]):
    """Patch all GUI tools to log executions."""
    for tool_name, tool in gui_tools.items():
        if hasattr(tool, "_run"):
            original_run = tool._run

            def make_traced_run(name, orig):
                def traced_run(*args, **kwargs):
                    print(f"\n{'='*60}")
                    print(f">>> TOOL START: {name}")
                    print(f"    Args: {args}")
                    print(f"    Kwargs: {kwargs}")
                    sys.stdout.flush()

                    start = time.time()
                    try:
                        result = orig(*args, **kwargs)
                        duration = time.time() - start

                        success = getattr(result, "success", None)
                        action = getattr(result, "action_taken", None)
                        data = getattr(result, "data", None)
                        error = getattr(result, "error", None)

                        print(f"<<< TOOL END: {name} [{duration:.2f}s]")
                        print(f"    Success: {success}")
                        print(f"    Action: {action}")
                        if data:
                            print(f"    Data: {str(data)[:300]}")
                        if error:
                            print(f"    Error: {error}")
                        print(f"{'='*60}")
                        sys.stdout.flush()

                        profiler.log_tool(
                            name,
                            duration,
                            f"args={args}, kwargs={kwargs}",
                            f"success={success}, action={action}",
                        )
                        return result
                    except Exception as e:
                        duration = time.time() - start
                        print(f"<<< TOOL ERROR: {name} [{duration:.2f}s] - {e}")
                        print(f"{'='*60}")
                        sys.stdout.flush()
                        profiler.log_tool(name, duration, str(kwargs), f"error={e}")
                        raise

                return traced_run

            tool._run = make_traced_run(tool_name, original_run)
            print(f"[PROFILER] Patched {tool_name}")


def patch_llm_calls():
    """Patch CrewAI's LLM.call method to log all LLM calls."""
    try:
        from crewai import LLM

        original_call = LLM.call

        def traced_call(self, messages, *args, **kwargs):
            model = getattr(self, "model", "unknown")

            if isinstance(messages, str):
                prompt_len = len(messages)
                msg_count = 1
                last_msg = messages[:300]
            else:
                prompt_len = sum(len(str(m.get("content", ""))) for m in messages)
                msg_count = len(messages)
                if messages:
                    last_msg = str(messages[-1].get("content", ""))[:300]
                else:
                    last_msg = ""

            print(f"\n{'*'*60}")
            print(f">>> LLM CALL START")
            print(f"    Model: {model}")
            print(f"    Messages: {msg_count}")
            print(f"    Prompt length: {prompt_len} chars")
            print(f"    Last message preview:")
            for line in last_msg.split("\n")[:5]:
                print(f"      {line[:100]}")
            sys.stdout.flush()

            start = time.time()
            result = original_call(self, messages, *args, **kwargs)
            duration = time.time() - start

            response_text = str(result) if result else ""
            response_len = len(response_text)

            print(f"<<< LLM CALL END [{duration:.2f}s]")
            print(f"    Response length: {response_len} chars")
            print(f"    Response preview:")
            for line in response_text[:500].split("\n")[:5]:
                print(f"      {line[:100]}")
            print(f"{'*'*60}")
            sys.stdout.flush()

            profiler.log_llm(duration, prompt_len, response_len)
            return result

        LLM.call = traced_call
        print("[PROFILER] Patched crewai.LLM.call")

    except Exception as e:
        print(f"[PROFILER] Could not patch CrewAI LLM: {e}")


async def run_profiled_task(task: str):
    """Run a task with full profiling."""
    import logging

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 80)
    print(f"PROFILING TASK: {task}")
    print("=" * 80)
    print(f"Started at: {datetime.now().isoformat()}")
    print()

    print("[PROFILER] Patching LLM...")
    patch_llm_calls()

    from computer_use.crew import ComputerUseCrew
    from computer_use.utils.platform_detector import detect_platform
    from computer_use.utils.safety_checker import SafetyChecker

    capabilities = detect_platform()
    safety_checker = SafetyChecker()

    crew = ComputerUseCrew(
        capabilities=capabilities,
        safety_checker=safety_checker,
    )

    print("[PROFILER] Patching GUI tools...")
    patch_gui_tools(crew.gui_tools)

    profiler.start()

    print("\n--- STARTING CREW EXECUTION ---\n")
    sys.stdout.flush()

    try:
        result = await crew.execute_task(task)
        print("\n--- CREW EXECUTION COMPLETE ---\n")
        print(f"Result: {result}")
    except KeyboardInterrupt:
        print("\n--- EXECUTION INTERRUPTED ---\n")
    except Exception as e:
        print(f"\n--- EXECUTION ERROR: {e} ---\n")
        import traceback

        traceback.print_exc()

    profiler.print_summary()


if __name__ == "__main__":
    task = (
        "Send /tmp/browser-use-downloads-8d1e9868/Heir-of-Fire-By-Sarah-J-Maas.pdf "
        "to Dr.Pondatti using Messages"
    )

    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])

    asyncio.run(run_profiled_task(task))
