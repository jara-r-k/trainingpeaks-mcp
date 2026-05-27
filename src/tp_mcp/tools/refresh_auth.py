"""TOOL-08: tp_refresh_auth - Attempt to refresh authentication from browser.

SECURITY NOTES:
- Cookie values are NEVER included in the return dict (would leak to Claude)
- Only returns: success status, browser name, athlete_id, email
- Cookie is stored directly via store_credential(), never passed through return
"""

from typing import Any

from tp_mcp.auth import store_credential, validate_auth
from tp_mcp.auth.browser import extract_tp_cookie
from tp_mcp.sanitiser import sanitise_result


def _sanitize_result(result: dict[str, Any]) -> dict[str, Any]:
    """SECURITY: Ensure no cookie values in result dict before returning to Claude.

    Delegates to the central sanitiser so the coverage is consistent across
    all tools. Kept as a named function for defence-in-depth and call-site clarity.
    """
    return sanitise_result(result)


async def tp_refresh_auth(browser: str = "auto") -> dict[str, Any]:
    """Attempt to refresh TrainingPeaks authentication by extracting cookie from browser.

    This tool tries to automatically extract a fresh cookie from the user's browser.
    Requires the user to be logged into TrainingPeaks in their browser.

    Args:
        browser: Browser to extract from. Options: chrome, firefox, safari, edge, auto.
                 Use 'auto' to try all browsers.

    Returns:
        Dict with success status and message.
    """
    # Try to extract cookie from browser
    result = extract_tp_cookie(browser if browser != "auto" else None)

    if not result.success:
        # Check if it's a missing dependency issue
        if "not installed" in result.message:
            return {
                "success": False,
                "message": "Browser extraction not available",
                "details": "The browser-cookie3 package is not installed.",
                "action_needed": "Run: pip install tp-mcp[browser]",
            }

        return {
            "success": False,
            "message": "Could not extract cookie from browser",
            "details": result.message,
            "action_needed": (
                "Make sure you're logged into TrainingPeaks at app.trainingpeaks.com "
                "in your browser, then try again. Or run 'tp-mcp auth' manually."
            ),
        }

    # Validate the extracted cookie
    cookie = result.cookie
    validation = await validate_auth(cookie)

    if not validation.is_valid:
        return {
            "success": False,
            "message": "Extracted cookie is invalid or expired",
            "details": validation.message,
            "action_needed": "Log into TrainingPeaks at app.trainingpeaks.com in your browser, then try again.",
        }

    # Store the valid cookie
    store_result = store_credential(cookie)

    if not store_result.success:
        return {
            "success": False,
            "message": "Could not store the refreshed cookie",
            "details": store_result.message,
            "action_needed": "Run 'tp-mcp auth' manually.",
        }

    # SECURITY: Sanitize before returning to ensure no cookie leakage
    return _sanitize_result(
        {
            "success": True,
            "message": f"Authentication refreshed from {result.browser}",
            "athlete_id": validation.athlete_id,
            "email": validation.email,
            "action_needed": None,
        }
    )
