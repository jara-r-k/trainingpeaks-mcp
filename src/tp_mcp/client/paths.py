"""Shared URL-path normalisation for HTTP safety decisions."""

from urllib.parse import unquote

import httpx


def normalise_path(endpoint: str) -> str | None:
    """Return a lowercase safety path, or None when it cannot be resolved safely.

    Start with httpx's wire spelling: it removes literal dot segments before a
    server can decode escapes. Then decode up to five times and remove decoded
    dot segments too. Query/fragment text is excluded before decoding, so encoded
    delimiters inside the path remain part of the path being checked.
    """
    path = endpoint.split("#", 1)[0].split("?", 1)[0]
    try:
        # Build only; the dummy authority ensures absolute-URL path handling.
        path = httpx.URL(scheme="https", host="path.invalid", path=path).raw_path.decode("ascii")
    except httpx.InvalidURL:
        return None
    for _ in range(5):
        decoded = unquote(path)
        if decoded == path:
            break
        path = decoded
    if unquote(path) != path:
        return None

    # Match httpx's dot removal, retaining empty segments (repeated slashes).
    parts: list[str] = []
    for part in path.split("/"):
        if part == ".":
            continue
        if part == "..":
            if parts and parts != [""]:
                parts.pop()
        else:
            parts.append(part)
    return "/".join(parts).lower()
