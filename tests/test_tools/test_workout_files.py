"""Tests for path-traversal defences in workout file tools."""

import gzip
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tp_mcp.tools.workout_files import (
    _validate_path,
    tp_download_workout_file,
    tp_upload_workout_file,
)

# ---------------------------------------------------------------------------
# _validate_path unit tests
# ---------------------------------------------------------------------------


class TestValidatePath:
    """Unit tests for the shared _validate_path helper."""

    def test_fit_file_under_home_passes(self, tmp_path):
        home = Path.home()
        candidate = home / "Downloads" / "activity.fit"
        resolved, reason = _validate_path(str(candidate), mode="upload")
        assert reason == "", reason
        assert resolved == candidate.resolve()

    def test_tcx_passes(self, tmp_path):
        candidate = Path.home() / "activity.tcx"
        resolved, reason = _validate_path(str(candidate), mode="upload")
        assert reason == ""

    def test_gpx_passes(self):
        candidate = Path.home() / "run.gpx"
        resolved, reason = _validate_path(str(candidate), mode="upload")
        assert reason == ""

    def test_csv_passes(self):
        candidate = Path.home() / "laps.csv"
        resolved, reason = _validate_path(str(candidate), mode="upload")
        assert reason == ""

    def test_exe_rejected(self):
        candidate = Path.home() / "payload.exe"
        resolved, reason = _validate_path(str(candidate), mode="upload")
        assert resolved is None
        assert "exe" in reason.lower() or "extension" in reason.lower()

    def test_bin_rejected(self):
        candidate = Path.home() / "run.bin"
        resolved, reason = _validate_path(str(candidate), mode="upload")
        assert resolved is None

    def test_etc_passwd_rejected_upload(self):
        resolved, reason = _validate_path("/etc/passwd", mode="upload")
        assert resolved is None
        assert "restricted" in reason.lower()

    def test_etc_ssh_config_rejected_upload(self):
        resolved, reason = _validate_path("/etc/ssh/sshd_config", mode="upload")
        assert resolved is None

    def test_private_etc_rejected_on_macos(self):
        # macOS /etc symlinks to /private/etc — resolver may produce /private/etc/...
        # Test both forms.
        resolved, reason = _validate_path("/private/etc/hosts", mode="upload")
        assert resolved is None

    def test_proc_rejected(self):
        resolved, reason = _validate_path("/proc/self/mem", mode="upload")
        assert resolved is None

    def test_ssh_dotdir_rejected(self):
        candidate = Path.home() / ".ssh" / "id_rsa"
        resolved, reason = _validate_path(str(candidate), mode="upload")
        assert resolved is None
        assert ".ssh" in reason

    def test_aws_dotdir_rejected(self):
        candidate = Path.home() / ".aws" / "credentials"
        resolved, reason = _validate_path(str(candidate), mode="upload")
        assert resolved is None

    def test_gnupg_dotdir_rejected(self):
        candidate = Path.home() / ".gnupg" / "secring.gpg"
        resolved, reason = _validate_path(str(candidate), mode="upload")
        assert resolved is None

    def test_dotdot_segment_collapsed_then_revalidated(self):
        # Path.resolve() collapses ..; if the result lands in /etc it must still be rejected.
        candidate = str(Path.home() / "Downloads" / ".." / ".." / "etc" / "passwd")
        resolved, reason = _validate_path(candidate, mode="upload")
        # After resolve, this lands outside $HOME — rejected either by system prefix or by home check.
        # For upload mode we only check system prefixes + dotdirs + extension.
        # /etc/passwd has no allowed extension, so it must be rejected on extension or prefix.
        assert resolved is None

    def test_download_inside_home_passes(self):
        candidate = Path.home() / "Downloads" / "tp-mcp" / "workout.fit.gz"
        resolved, reason = _validate_path(str(candidate), mode="download")
        assert reason == ""

    def test_download_outside_home_rejected(self):
        resolved, reason = _validate_path("/tmp/evil.fit.gz", mode="download")
        assert resolved is None
        assert "$HOME" in reason or "outside" in reason or "must be under" in reason

    def test_download_etc_rejected(self):
        resolved, reason = _validate_path("/etc/crontab", mode="download")
        assert resolved is None

    def test_download_dotdot_outside_home_rejected(self):
        candidate = str(Path.home() / ".." / ".." / "tmp" / "out")
        resolved, reason = _validate_path(candidate, mode="download")
        assert resolved is None

    # -- HIGH: download extension allowlist ----------------------------------

    def test_download_rejects_extension_not_in_allowlist(self):
        home = Path.home()
        bad_paths = [
            home / "Library" / "Keychains" / "login.keychain-db",
            home / ".gitconfig",
            home
            / "Library"
            / "Application Support"
            / "Google"
            / "Chrome"
            / "Default"
            / "Cookies.sqlite",
            home / "Downloads" / "Cookies",  # no extension
            home / "Downloads" / "notes.txt",
        ]
        for p in bad_paths:
            resolved, reason = _validate_path(str(p), mode="download")
            assert (
                resolved is None
            ), f"Expected rejection for {p}, got resolved={resolved}"
            assert (
                "extension" in reason.lower() or "unsupported" in reason.lower()
            ), f"Unexpected rejection reason for {p}: {reason}"

    def test_download_accepts_workout_extensions(self):
        home = Path.home()
        good_paths = [
            home / "Downloads" / "activity.fit",
            home / "Downloads" / "activity.fit.gz",
            home / "Downloads" / "route.tcx",
            home / "Downloads" / "track.gpx",
            home / "Downloads" / "laps.csv",
        ]
        for p in good_paths:
            resolved, reason = _validate_path(str(p), mode="download")
            assert reason == "", f"Expected acceptance for {p}, got reason={reason!r}"

    # -- MEDIUM: $HOME=/ collapse --------------------------------------------

    def test_home_root_collapse_rejected(self):
        # Patch Path.home() to simulate a Docker/CI image where $HOME is unset or /.
        with patch("tp_mcp.tools.workout_files.Path") as mock_path_cls:
            # Let most Path operations pass through to the real implementation.
            real_path = Path
            mock_path_cls.side_effect = real_path
            mock_path_cls.home.return_value = real_path("/")

            resolved, reason = _validate_path(
                str(real_path.home() / "activity.fit"), mode="download"
            )
        assert (
            resolved is None
        ), f"Expected rejection when $HOME=/, got resolved={resolved}"
        assert "$HOME" in reason and "/" in reason, f"Unexpected reason: {reason}"

    # -- LOW: symlink-into-/etc rejected after resolve -----------------------

    def test_symlink_into_etc_rejected_after_resolve(self, tmp_path):
        # Create a symlink with an allowed .fit extension that points outside $HOME.
        # After resolve(), the real target is /etc/passwd (or /private/etc/passwd on macOS),
        # which must be caught by the sensitive-prefix check before the extension check passes.
        symlink = tmp_path / "activity.fit"
        try:
            os.symlink("/etc/passwd", symlink)
        except OSError:
            pytest.skip("Cannot create symlinks in this environment")

        resolved, reason = _validate_path(str(symlink), mode="upload")
        assert (
            resolved is None
        ), f"Symlink pointing to /etc/passwd must be rejected after resolve, got resolved={resolved}"
        assert "restricted" in reason.lower(), f"Unexpected reason: {reason}"


# ---------------------------------------------------------------------------
# tp_upload_workout_file integration tests
# ---------------------------------------------------------------------------


class TestTpUploadWorkoutFilePathSecurity:
    """Path-traversal rejection tests for tp_upload_workout_file."""

    @pytest.mark.asyncio
    async def test_etc_passwd_rejected(self):
        result = await tp_upload_workout_file(workout_id="999", file_path="/etc/passwd")
        assert result.get("isError") is True
        assert result.get("error_code") == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_ssh_key_rejected(self):
        ssh_key = str(Path.home() / ".ssh" / "id_rsa")
        result = await tp_upload_workout_file(workout_id="999", file_path=ssh_key)
        assert result.get("isError") is True
        assert result.get("error_code") == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_exe_extension_rejected(self):
        path = str(Path.home() / "Downloads" / "payload.exe")
        result = await tp_upload_workout_file(workout_id="999", file_path=path)
        assert result.get("isError") is True
        assert result.get("error_code") == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_valid_fit_file_allowed(self, tmp_path):
        # Write a tiny fake FIT file in a home-equivalent tmp dir.
        # Patch Path.home() so tmp_path acts as $HOME for this test.
        fit_file = tmp_path / "activity.fit"
        fit_file.write_bytes(b"\x00" * 16)

        mock_response = MagicMock()
        mock_response.is_error = False
        mock_response.data = {"workoutId": 999}

        mock_get_response = MagicMock()
        mock_get_response.is_error = False
        mock_get_response.data = {"workoutDay": "2025-01-08"}

        with patch("tp_mcp.tools.workout_files._validate_path") as mock_validate:
            mock_validate.return_value = (fit_file, "")
            with patch("tp_mcp.tools.workout_files.TPClient") as mock_client_cls:
                mock_instance = AsyncMock()
                mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
                mock_instance.get = AsyncMock(return_value=mock_get_response)
                mock_instance.post = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value.__aenter__ = AsyncMock(
                    return_value=mock_instance
                )
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await tp_upload_workout_file(
                    workout_id="999", file_path=str(fit_file)
                )

        assert not result.get("isError"), result
        assert result["message"] == "Workout file uploaded successfully."


# ---------------------------------------------------------------------------
# tp_download_workout_file integration tests
# ---------------------------------------------------------------------------


class TestTpDownloadWorkoutFilePathSecurity:
    """Path-traversal rejection tests for tp_download_workout_file."""

    @pytest.mark.asyncio
    async def test_etc_output_path_rejected(self):
        result = await tp_download_workout_file(
            workout_id="999", file_id="1", output_path="/etc/crontab"
        )
        assert result.get("isError") is True
        assert result.get("error_code") == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_tmp_output_path_rejected(self):
        result = await tp_download_workout_file(
            workout_id="999", file_id="1", output_path="/tmp/evil"
        )
        assert result.get("isError") is True
        assert result.get("error_code") == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_ssh_authorized_keys_rejected(self):
        path = str(Path.home() / ".ssh" / "authorized_keys")
        result = await tp_download_workout_file(
            workout_id="999", file_id="1", output_path=path
        )
        assert result.get("isError") is True
        assert result.get("error_code") == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_valid_home_download_dir_allowed(self, tmp_path):
        # Use a writable tmp_path that sits under home (patch home to tmp root).
        output_dir = tmp_path / "tp-downloads"
        output_dir.mkdir()

        raw_content = gzip.compress(b"FIT data")

        mock_raw_response = MagicMock()
        mock_raw_response.is_error = False
        mock_raw_response.content_disposition = 'attachment; filename="activity.fit.gz"'
        mock_raw_response.content = raw_content
        mock_raw_response.content_type = "application/octet-stream"

        with patch("tp_mcp.tools.workout_files._validate_path") as mock_validate:
            mock_validate.return_value = (output_dir, "")
            with patch("tp_mcp.tools.workout_files.TPClient") as mock_client_cls:
                mock_instance = AsyncMock()
                mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
                mock_instance.get_raw = AsyncMock(return_value=mock_raw_response)
                mock_client_cls.return_value.__aenter__ = AsyncMock(
                    return_value=mock_instance
                )
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await tp_download_workout_file(
                    workout_id="999", file_id="1", output_path=str(output_dir)
                )

        assert not result.get("isError"), result
        assert result["message"] == "Workout file downloaded successfully."
