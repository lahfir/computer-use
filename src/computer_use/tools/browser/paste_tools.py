"""
Browser-Use paste tools for instant text entry.
Uses JavaScript to set values directly instead of character-by-character typing.
"""

import platform
from pydantic import BaseModel, Field


class PasteTextAction(BaseModel):
    """Parameters for paste_text action."""

    index: int = Field(description="Index of the element to paste into")
    text: str = Field(description="Text content to paste")
    clear: bool = Field(
        default=True, description="Clear existing content before pasting"
    )


class TypeToFocusedAction(BaseModel):
    """
    Parameters for type_to_focused action.
    Use after clicking a canvas-based editor (like Google Docs).
    """

    text: str = Field(
        description="Text content to type into the currently focused element"
    )
    clear: bool = Field(
        default=False, description="Clear existing content first (Cmd+A then Backspace)"
    )


def load_paste_tools():
    """
    Load paste tools for instant text entry.

    Returns:
        Tools object with paste action, or None if browser_use not available.
    """
    try:
        import browser_use  # noqa: F401

        return _create_paste_tools()
    except ImportError:
        return None


def _create_paste_tools():
    """
    Create paste tools with custom actions.

    Returns:
        Configured Tools object with paste action.
    """
    from browser_use import Tools, ActionResult
    from browser_use.browser.session import BrowserSession

    tools = Tools()

    @tools.registry.action(
        description="""Paste text instantly into an input field or textarea. 
        MUCH faster than input() which types character-by-character.
        Use this for: emails, passwords, URLs, paragraphs, any text content.
        Always use paste_text instead of input for better reliability.""",
        param_model=PasteTextAction,
    )
    async def paste_text(
        params: PasteTextAction, browser_session: BrowserSession
    ) -> ActionResult:
        """
        Paste text instantly using JavaScript value assignment.

        This bypasses character-by-character typing by directly setting
        the element's value property, making it instant regardless of
        text length.
        """
        try:
            node = await browser_session.get_element_by_index(params.index)
            if node is None:
                return ActionResult(
                    error=f"Element index {params.index} not found - page may have changed"
                )

            backend_node_id = node.backend_node_id
            if not backend_node_id:
                return ActionResult(error="Could not get backend node ID for element")

            cdp_session = await browser_session.get_or_create_cdp_session()

            result = await cdp_session.cdp_client.send.DOM.resolveNode(
                params={"backendNodeId": backend_node_id},
                session_id=cdp_session.session_id,
            )

            if "object" not in result or "objectId" not in result["object"]:
                return ActionResult(error="Could not resolve element to object")

            object_id = result["object"]["objectId"]

            escaped_text = (
                params.text.replace("\\", "\\\\")
                .replace("`", "\\`")
                .replace("$", "\\$")
            )

            tag_check = """function() {
                return {
                    tagName: this.tagName,
                    isInput: this.tagName === 'INPUT' || this.tagName === 'TEXTAREA'
                };
            }"""

            tag_result = await cdp_session.cdp_client.send.Runtime.callFunctionOn(
                params={
                    "functionDeclaration": tag_check,
                    "objectId": object_id,
                    "returnByValue": True,
                },
                session_id=cdp_session.session_id,
            )

            element_info = tag_result.get("result", {}).get("value", {})
            is_input = element_info.get("isInput", False)

            if is_input:
                clear_flag = "true" if params.clear else "false"
                js_code = f"""function() {{
                    const text = `{escaped_text}`;
                    if ({clear_flag}) this.value = '';
                    this.value = {clear_flag} ? text : this.value + text;
                    this.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    this.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return 'success:input';
                }}"""

                eval_result = await cdp_session.cdp_client.send.Runtime.callFunctionOn(
                    params={
                        "functionDeclaration": js_code,
                        "objectId": object_id,
                        "returnByValue": True,
                    },
                    session_id=cdp_session.session_id,
                )
                method_used = "input"
            else:
                focus_js = """function() { this.focus(); return 'focused'; }"""
                await cdp_session.cdp_client.send.Runtime.callFunctionOn(
                    params={
                        "functionDeclaration": focus_js,
                        "objectId": object_id,
                        "returnByValue": True,
                    },
                    session_id=cdp_session.session_id,
                )

                if params.clear:
                    await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
                        params={
                            "type": "keyDown",
                            "key": "a",
                            "code": "KeyA",
                            "modifiers": 8,
                        },
                        session_id=cdp_session.session_id,
                    )
                    await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
                        params={
                            "type": "keyUp",
                            "key": "a",
                            "code": "KeyA",
                            "modifiers": 8,
                        },
                        session_id=cdp_session.session_id,
                    )
                    await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
                        params={
                            "type": "keyDown",
                            "key": "Backspace",
                            "code": "Backspace",
                        },
                        session_id=cdp_session.session_id,
                    )
                    await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
                        params={
                            "type": "keyUp",
                            "key": "Backspace",
                            "code": "Backspace",
                        },
                        session_id=cdp_session.session_id,
                    )

                clipboard_js = f"""async function() {{
                    const text = `{escaped_text}`;
                    try {{
                        await navigator.clipboard.writeText(text);
                        return 'clipboard_ready';
                    }} catch(e) {{
                        return 'clipboard_failed: ' + e.message;
                    }}
                }}"""

                clipboard_result = (
                    await cdp_session.cdp_client.send.Runtime.callFunctionOn(
                        params={
                            "functionDeclaration": clipboard_js,
                            "objectId": object_id,
                            "returnByValue": True,
                            "awaitPromise": True,
                        },
                        session_id=cdp_session.session_id,
                    )
                )

                clipboard_status = clipboard_result.get("result", {}).get("value", "")

                if "clipboard_ready" in str(clipboard_status):
                    import platform

                    mod_key = 8 if platform.system() == "Darwin" else 2

                    await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
                        params={
                            "type": "keyDown",
                            "key": "v",
                            "code": "KeyV",
                            "modifiers": mod_key,
                        },
                        session_id=cdp_session.session_id,
                    )
                    await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
                        params={
                            "type": "keyUp",
                            "key": "v",
                            "code": "KeyV",
                            "modifiers": mod_key,
                        },
                        session_id=cdp_session.session_id,
                    )
                    method_used = "clipboard+paste"
                else:
                    await cdp_session.cdp_client.send.Input.insertText(
                        params={"text": params.text},
                        session_id=cdp_session.session_id,
                    )
                    method_used = "insertText"

            if is_input:
                if eval_result.get("exceptionDetails"):
                    error_msg = eval_result["exceptionDetails"].get(
                        "text", "Unknown error"
                    )
                    return ActionResult(error=f"JavaScript error: {error_msg}")

            text_preview = (
                params.text[:50] + "..." if len(params.text) > 50 else params.text
            )
            return ActionResult(
                extracted_content=f"Pasted text ({len(params.text)} chars) via {method_used}: {text_preview}"
            )

        except Exception as e:
            return ActionResult(error=f"Paste failed: {str(e)}")

    @tools.registry.action(
        description="""Insert text INSTANTLY into the currently focused element.
        PERFECT for canvas-based editors like Google Docs, Notion, Figma.
        
        HANDLES ANY AMOUNT OF TEXT IN ONE CALL - do NOT chunk or batch.
        
        WORKFLOW:
        1. First click() the canvas/editor area to focus it
        2. Then call type_to_focused(text="ALL your content here") - ONE call only
        
        Example: type_to_focused(text="# Full Report\\n\\nParagraph 1...\\n\\nParagraph 2...")
        
        This is INSTANT regardless of text length. Never break into multiple calls.""",
        param_model=TypeToFocusedAction,
    )
    async def type_to_focused(
        params: TypeToFocusedAction, browser_session: BrowserSession
    ) -> ActionResult:
        """
        Type text directly into whatever element is currently focused.

        This is the correct approach for canvas-based editors like Google Docs:
        - Canvas editors use a hidden <input> to capture keystrokes
        - Clicking the canvas focuses that hidden input
        - Input.insertText sends text to the focused element
        """
        try:
            cdp_session = await browser_session.get_or_create_cdp_session()

            if params.clear:
                mod_key = 8 if platform.system() == "Darwin" else 2

                await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
                    params={
                        "type": "keyDown",
                        "key": "a",
                        "code": "KeyA",
                        "modifiers": mod_key,
                    },
                    session_id=cdp_session.session_id,
                )
                await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
                    params={
                        "type": "keyUp",
                        "key": "a",
                        "code": "KeyA",
                        "modifiers": mod_key,
                    },
                    session_id=cdp_session.session_id,
                )
                await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
                    params={
                        "type": "keyDown",
                        "key": "Backspace",
                        "code": "Backspace",
                    },
                    session_id=cdp_session.session_id,
                )
                await cdp_session.cdp_client.send.Input.dispatchKeyEvent(
                    params={
                        "type": "keyUp",
                        "key": "Backspace",
                        "code": "Backspace",
                    },
                    session_id=cdp_session.session_id,
                )

            await cdp_session.cdp_client.send.Input.insertText(
                params={"text": params.text},
                session_id=cdp_session.session_id,
            )

            text_preview = (
                params.text[:50] + "..." if len(params.text) > 50 else params.text
            )
            return ActionResult(
                extracted_content=f"Typed to focused element ({len(params.text)} chars): {text_preview}"
            )

        except Exception as e:
            return ActionResult(error=f"Type to focused failed: {str(e)}")

    return tools
