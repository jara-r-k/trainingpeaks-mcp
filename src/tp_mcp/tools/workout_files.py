"""Workout file upload, download, and delete tools."""

import base64
import gzip
import tempfile
from pathlib import Path
from typing import Any

from tp_mcp.client import TPClient

FILE_DATA_DIR = Path(tempfile.gettempdir()) / "tp-mcp" / "files"

# Workout file extensions accepted for upload (case-insensitive).
_ALLOWED_UPLOAD_EXTENSIONS = {".fit", ".tcx", ".gpx", ".csv"}

# TP only ever returns these extensions on download — anything else indicates a path
# that was crafted to escape containment (e.g. ~/Library/Keychains/login.keychain-db).
_ALLOWED_DOWNLOAD_EXTENSIONS = {".fit", ".fit.gz", ".tcx", ".gpx", ".csv"}

# Sensitive path prefixes — reading or writing these is never legitimate for workout files.
_SENSITIVE_PREFIXES = (
    "/etc/",
    "/var/",
    "/root/",
    "/sys/",
    "/proc/",
    "/private/etc/",
    "/private/var/",
)

# Dotfile directory names whose presence anywhere in a resolved path is grounds for rejection.
_SENSITIVE_DIR_NAMES = {".ssh", ".aws", ".config", ".gnupg", ".kube", ".docker"}


def _validate_path(
    raw: str,
    *,
    mode: str,  # "upload" | "download"
) -> tuple[Path, str] | tuple[None, str]:
    """Resolve *raw* to a safe absolute path; return (Path, "") on success or (None, reason) on failure.

    Security contract:
    - Symlinks and ``..`` components are eliminated by ``Path.resolve()``.
    - Paths in sensitive OS prefixes (/etc, /var, /sys, /proc, /root, /private/etc) are rejected.
    - Paths containing dotfile credential directories (.ssh, .aws, .gnupg, etc.) are rejected.
    - Upload paths must have an allowed workout extension (.fit, .tcx, .gpx, .csv).
    - Download output paths must be under $HOME. Unrestricted writes are not supported
      (no TP_ALLOW_UNRESTRICTED_PATHS override is currently implemented).
    """
    try:
        resolved = Path(raw).expanduser().resolve()
    except (OSError, ValueError) as exc:
        return None, f"Invalid path: {exc}"

    resolved_str = str(resolved)

    # Reject sensitive OS prefixes (prevents reading host keys, /proc/mem, etc.)
    for prefix in _SENSITIVE_PREFIXES:
        if resolved_str.startswith(prefix):
            return (
                None,
                f"Path is in a restricted system location ({prefix.rstrip('/')}).",
            )

    # Reject paths that pass through a dotfile credential directory.
    for part in resolved.parts:
        if part in _SENSITIVE_DIR_NAMES:
            return (
                None,
                f"Path passes through a restricted credential directory ({part}).",
            )

    if mode == "upload":
        suffix = resolved.suffix.lower()
        if suffix not in _ALLOWED_UPLOAD_EXTENSIONS:
            exts = ", ".join(sorted(_ALLOWED_UPLOAD_EXTENSIONS))
            return None, f"Unsupported file extension '{suffix}'. Allowed: {exts}."

    if mode == "download":
        # Extension allowlist mirrors upload — TP only returns workout file types.
        # A non-workout extension signals an attempt to overwrite a sensitive $HOME file.
        suffix = resolved.suffix.lower()
        # Handle compound extension (.fit.gz) by checking the last two suffixes.
        compound = "".join(s.lower() for s in resolved.suffixes[-2:])
        if (
            compound not in _ALLOWED_DOWNLOAD_EXTENSIONS
            and suffix not in _ALLOWED_DOWNLOAD_EXTENSIONS
        ):
            exts = ", ".join(sorted(_ALLOWED_DOWNLOAD_EXTENSIONS))
            return (
                None,
                f"Download path has unsupported extension '{suffix}'. Allowed: {exts}.",
            )

        home = Path.home().resolve()
        # $HOME resolving to / means no real user directory is set (Docker/CI root).
        # Allowing it would make relative_to() pass for every path on the filesystem.
        if home == Path("/"):
            return None, (
                "$HOME resolves to /. Set $HOME to a real user directory before using file tools."
            )
        # Reject paths outside $HOME — unrestricted writes are not supported.
        try:
            resolved.relative_to(home)
        except ValueError:
            return None, (
                f"Download output path must be under {home}. "
                "Writing outside $HOME is not supported."
            )

    return resolved, ""


def _is_numeric_id(value: str, *, allow_negative: bool = False) -> bool:
    """Return True when value is a numeric ID string."""
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    if allow_negative:
        return text.lstrip("-").isdigit()
    return text.isdigit()


def _normalize_workout_day(workout_day: str) -> str:
    """Convert YYYY-MM-DD to TP datetime format, pass through if already datetime."""
    value = workout_day.strip()
    if "T" in value:
        return value
    return f"{value}T00:00:00"


def _gzip_if_needed(file_bytes: bytes) -> bytes:
    """Ensure upload payload uses gzip bytes as expected by TP filedata endpoint."""
    if len(file_bytes) >= 2 and file_bytes[0] == 0x1F and file_bytes[1] == 0x8B:
        return file_bytes
    return gzip.compress(file_bytes)


def _parse_content_disposition_filename(value: str | None) -> str | None:
    """Extract filename from Content-Disposition header."""
    if not value:
        return None
    lower = value.lower()
    token = "filename="
    idx = lower.find(token)
    if idx == -1:
        return None
    filename = value[idx + len(token) :].strip().strip('"').strip("'")
    return Path(filename).name if filename else None


def _save_workout_file(
    workout_id: str, file_id: str, filename: str, data: bytes
) -> str:
    """Persist downloaded workout file and return absolute path."""
    FILE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    fallback_name = f"workout_{workout_id}_file_{file_id}.fit.gz"
    safe_name = Path(filename).name if filename else fallback_name
    path = FILE_DATA_DIR / safe_name
    path.write_bytes(data)
    return str(path.resolve())


async def tp_upload_workout_file(
    workout_id: str,
    file_path: str | None = None,
    file_data_base64: str | None = None,
    workout_day: str | None = None,
) -> dict[str, Any]:
    """Upload a workout file (.fit, .tcx, .gpx) to an existing workout.

    Args:
        workout_id: The workout ID.
        file_path: Path to the file on disk (mutually exclusive with file_data_base64).
        file_data_base64: Base64-encoded file bytes (mutually exclusive with file_path).
        workout_day: Workout date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). If omitted, fetched from the workout.

    Returns:
        Dict with upload confirmation or error.
    """
    if not _is_numeric_id(workout_id):
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "workout_id must be a numeric ID.",
        }
    if not file_path and not file_data_base64:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "Provide either file_path or file_data_base64.",
        }
    if file_path and file_data_base64:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "Provide only one of file_path or file_data_base64.",
        }

    raw_bytes: bytes
    file_name: str
    if file_path:
        safe_path, reason = _validate_path(file_path, mode="upload")
        if safe_path is None:
            return {
                "isError": True,
                "error_code": "VALIDATION_ERROR",
                "message": reason,
            }
        try:
            raw_bytes = safe_path.read_bytes()
        except OSError as e:
            return {
                "isError": True,
                "error_code": "VALIDATION_ERROR",
                "message": f"Could not read file_path: {e}",
            }
        file_name = safe_path.name
    else:
        try:
            raw_bytes = base64.b64decode(file_data_base64 or "", validate=True)
        except (ValueError, TypeError) as e:
            return {
                "isError": True,
                "error_code": "VALIDATION_ERROR",
                "message": f"file_data_base64 is invalid base64: {e}",
            }
        file_name = f"workout_{workout_id}.fit.gz"

    if not raw_bytes:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "Uploaded file content must not be empty.",
        }

    gzipped = _gzip_if_needed(raw_bytes)
    payload_data = base64.b64encode(gzipped).decode("ascii")

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        resolved_workout_day: str
        if workout_day:
            resolved_workout_day = _normalize_workout_day(workout_day)
        else:
            get_endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{workout_id}"
            get_response = await client.get(get_endpoint)
            if get_response.is_error:
                return {
                    "isError": True,
                    "error_code": (
                        get_response.error_code.value
                        if get_response.error_code
                        else "API_ERROR"
                    ),
                    "message": f"Failed to fetch workout for upload: {get_response.message}",
                }
            workout_payload = (
                get_response.data if isinstance(get_response.data, dict) else {}
            )
            existing_day = workout_payload.get("workoutDay")
            if not existing_day:
                return {
                    "isError": True,
                    "error_code": "API_ERROR",
                    "message": "Could not determine workoutDay for upload. Provide workout_day explicitly.",
                }
            resolved_workout_day = _normalize_workout_day(str(existing_day))

        endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{workout_id}/filedata"
        response = await client.post(
            endpoint,
            json={
                "workoutDay": resolved_workout_day,
                "data": payload_data,
                "fileName": file_name,
                "uploadClient": "TP Web App",
            },
        )

        if response.is_error:
            return {
                "isError": True,
                "error_code": (
                    response.error_code.value if response.error_code else "API_ERROR"
                ),
                "message": response.message,
            }

        resp_data = response.data if isinstance(response.data, dict) else {}
        return {
            "workout_id": str(resp_data.get("workoutId", workout_id)),
            "uploaded_bytes": len(raw_bytes),
            "uploaded_gzip_bytes": len(gzipped),
            "workout_day": resolved_workout_day,
            "message": "Workout file uploaded successfully.",
        }


async def tp_download_workout_file(
    workout_id: str,
    file_id: str,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Download a workout file by file_id.

    Args:
        workout_id: The workout ID.
        file_id: The file ID (from device_files or attachment_files in tp_get_workout).
        output_path: Optional path to save the file. Can be a directory or full file path.

    Returns:
        Dict with file info and saved path, or error.
    """
    if not _is_numeric_id(workout_id):
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "workout_id must be a numeric ID.",
        }
    if not _is_numeric_id(file_id, allow_negative=True):
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "file_id must be a numeric ID (can be negative).",
        }

    # Validate output_path before making any API call — rejects malicious paths early.
    safe_output: Path | None = None
    if output_path:
        safe_output, reason = _validate_path(output_path, mode="download")
        if safe_output is None:
            return {
                "isError": True,
                "error_code": "VALIDATION_ERROR",
                "message": reason,
            }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{workout_id}/rawfiledata/{file_id}"
        response = await client.get_raw(endpoint)

        if response.is_error:
            if (
                response.error_code is not None
                and response.error_code.value == "NOT_FOUND"
            ):
                return {
                    "isError": True,
                    "error_code": "NOT_FOUND",
                    "message": f"Workout file {file_id} not found.",
                }
            return {
                "isError": True,
                "error_code": (
                    response.error_code.value if response.error_code else "API_ERROR"
                ),
                "message": response.message,
            }

        filename = _parse_content_disposition_filename(response.content_disposition)
        content = response.content
        if safe_output is not None:
            if safe_output.is_dir():
                save_name = filename or f"workout_{workout_id}_file_{file_id}.fit.gz"
                file_out = safe_output / Path(save_name).name
            else:
                file_out = safe_output
            file_out.parent.mkdir(parents=True, exist_ok=True)
            file_out.write_bytes(content)
            saved_to = str(file_out)
        else:
            saved_to = _save_workout_file(
                workout_id=workout_id,
                file_id=file_id,
                filename=filename or "",
                data=content,
            )

        return {
            "workout_id": workout_id,
            "file_id": file_id,
            "file_name": filename,
            "content_type": response.content_type,
            "size_bytes": len(content),
            "saved_to": saved_to,
            "message": "Workout file downloaded successfully.",
        }


async def tp_delete_workout_file(workout_id: str, file_id: str) -> dict[str, Any]:
    """Delete a workout file.

    Args:
        workout_id: The workout ID.
        file_id: The file ID (from device_files or attachment_files in tp_get_workout).

    Returns:
        Dict with confirmation or error.
    """
    if not _is_numeric_id(workout_id):
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "workout_id must be a numeric ID.",
        }
    if not _is_numeric_id(file_id, allow_negative=True):
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "file_id must be a numeric ID (can be negative).",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{workout_id}/filedata/{file_id}"
        response = await client.delete(endpoint)
        if response.is_error:
            return {
                "isError": True,
                "error_code": (
                    response.error_code.value if response.error_code else "API_ERROR"
                ),
                "message": response.message,
            }

        return {
            "workout_id": workout_id,
            "file_id": file_id,
            "message": "Workout file deleted successfully.",
        }
