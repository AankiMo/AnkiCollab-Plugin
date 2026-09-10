"""Tests for media_optimizer.py — filename validation, sanitization, optimization.

These verify:
- Filename validation (allowed characters, extensions, length, traversal)
- Filename sanitization (invalid → valid random name)
- Image optimization availability detection
- Edge cases in filename handling
"""

import pytest
from unittest.mock import MagicMock, patch
import os
import sys

# We need to patch PIL before importing media_optimizer
# Since media_optimizer imports from main.media_manager, we need to handle that

from media_optimizer import (
    is_allowed_filename,
    sanitize_filename,
    can_optimize,
    ALLOWED_EXTENSIONS,
    OPTIMIZABLE_INPUT_EXTENSIONS,
    FORMAT_TO_EXTENSION,
)

# ──────────────────────────────────────────────────────────────────────
# Filename validation
# ──────────────────────────────────────────────────────────────────────


class TestIsAllowedFilename:
    """Validates the safety criteria for filenames matching the Rust backend."""

    # Valid cases
    def test_simple_valid_filename(self):
        assert is_allowed_filename("image_01.png") is True

    def test_valid_with_spaces(self):
        assert is_allowed_filename("my image file.jpg") is True

    def test_valid_with_parentheses(self):
        assert is_allowed_filename("image (1).png") is True

    def test_valid_with_dashes(self):
        assert is_allowed_filename("my-image-file.webp") is True

    def test_valid_audio_extension(self):
        assert is_allowed_filename("audio_01.mp3") is True

    def test_valid_ogg_extension(self):
        assert is_allowed_filename("audio_01.ogg") is True

    def test_valid_underscore_start(self):
        assert is_allowed_filename("_hidden.png") is True

    def test_valid_with_plus(self):
        assert is_allowed_filename("file+name.jpg") is True

    def test_valid_with_comma(self):
        assert is_allowed_filename("file,name.jpg") is True

    def test_valid_with_percent(self):
        assert is_allowed_filename("file%20name.png") is True

    def test_valid_with_ampersand(self):
        assert is_allowed_filename("file&name.png") is True

    # Invalid cases
    def test_empty_filename(self):
        assert is_allowed_filename("") is False

    def test_none_filename(self):
        assert is_allowed_filename(None) is False

    def test_too_short(self):
        assert is_allowed_filename("a.b") is False

    def test_too_long(self):
        assert is_allowed_filename("a" * 252 + ".png") is False

    def test_path_separator_forward_slash(self):
        assert is_allowed_filename("dir/file.png") is False

    def test_path_separator_backslash(self):
        assert is_allowed_filename("dir\\file.png") is False

    def test_path_traversal(self):
        assert is_allowed_filename("..\\..\\etc\\passwd.png") is False

    def test_double_dot(self):
        assert is_allowed_filename("file..png") is False

    def test_trailing_dot(self):
        assert is_allowed_filename("file.png.") is False

    def test_trailing_space(self):
        assert is_allowed_filename("file.png ") is False

    def test_unicode_characters(self):
        assert is_allowed_filename("файл.png") is False

    def test_narrow_no_break_space(self):
        """U+202F should be rejected."""
        assert is_allowed_filename("file\u202fname.png") is False

    def test_starts_with_dot(self):
        assert is_allowed_filename(".hidden.png") is False

    def test_no_alphanumeric(self):
        assert is_allowed_filename("----.png") is False

    def test_whitespace_only(self):
        assert is_allowed_filename("     ") is False


# ──────────────────────────────────────────────────────────────────────
# Filename sanitization
# ──────────────────────────────────────────────────────────────────────


class TestSanitizeFilename:
    def test_valid_filename_unchanged(self):
        assert sanitize_filename("good_file.png") == "good_file.png"

    def test_invalid_gets_randomized(self):
        result = sanitize_filename("файл.png")
        assert result is not None
        assert result.endswith(".png")
        assert result.startswith("img_")

    def test_empty_filename(self):
        assert sanitize_filename("") is False

    def test_none_filename(self):
        assert sanitize_filename(None) is False

    def test_invalid_extension_returns_none(self):
        result = sanitize_filename("file.exe")
        assert result is None

    def test_no_extension_returns_false(self):
        result = sanitize_filename("noextension")
        assert result is False

    def test_preserves_valid_extension(self):
        result = sanitize_filename("bad\u202fname.jpg")
        assert result is not None
        assert result.endswith(".jpg")

    def test_allowed_extensions_list(self):
        """All allowed extensions should pass sanitization."""
        for ext in ALLOWED_EXTENSIONS:
            filename = f"test_file.{ext}"
            result = sanitize_filename(filename)
            assert (
                result is not None and result is not False
            ), f"Extension .{ext} should be allowed but got {result}"


# ──────────────────────────────────────────────────────────────────────
# Optimization availability
# ──────────────────────────────────────────────────────────────────────


class TestOptimizationAvailability:
    def test_can_optimize_returns_bool(self):
        result = can_optimize()
        assert isinstance(result, bool)

    def test_optimizable_extensions_subset(self):
        """All optimizable extensions should be in the full allowed list."""
        for ext in OPTIMIZABLE_INPUT_EXTENSIONS:
            bare = ext.lstrip(".")
            assert (
                bare in ALLOWED_EXTENSIONS
            ), f"Optimizable ext {ext} not in allowed list"

    def test_format_to_extension_mapping(self):
        """All format mappings should produce known extensions."""
        for fmt, ext in FORMAT_TO_EXTENSION.items():
            bare = ext.lstrip(".")
            assert (
                bare in ALLOWED_EXTENSIONS
            ), f"Format {fmt} maps to {ext} which is not allowed"


# ──────────────────────────────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_exactly_5_chars_minimum(self):
        """Minimum length is 5 characters."""
        assert is_allowed_filename("a.png") is True  # 5 chars
        assert is_allowed_filename("abcd") is False  # 4 chars, no ext

    def test_exactly_255_chars_maximum(self):
        """Maximum length is 255 characters."""
        name = "a" * 251 + ".png"  # 255 chars
        assert is_allowed_filename(name) is True

    def test_256_chars_too_long(self):
        name = "a" * 252 + ".png"  # 256 chars
        assert is_allowed_filename(name) is False

    def test_multiple_dots_valid(self):
        """Multiple dots are OK as long as no double-dot."""
        assert is_allowed_filename("my.image.file.png") is True

    def test_webp_not_in_optimizable(self):
        """WebP should NOT be in optimizable (already target format)."""
        assert ".webp" not in OPTIMIZABLE_INPUT_EXTENSIONS
