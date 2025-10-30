"""Tests for completion support in Collagraph .cgx files.

Phase 1: Only tests completions within <script> tags.
"""

from textwrap import dedent

import pytest
from lsprotocol.types import Position

from collagraph_lsp.completions import (
    analyze_context,
    is_in_script_region,
    position_to_offset,
)


class TestContextDetection:
    """Test detection of Python regions in .cgx files."""

    def test_detect_script_region(self):
        source = dedent(
            """
            <template>
              <div>Hello</div>
            </template>
            <script>
            import os
            x = 10
            </script>"""
        ).lstrip()

        # Cursor in script section
        position = Position(line=4, character=7)  # "import"
        assert is_in_script_region(source, position)

        # Cursor outside script section
        position = Position(line=1, character=5)  # in template
        assert not is_in_script_region(source, position)

    def test_analyze_context_script_section(self):
        """Test that analyze_context correctly identifies script sections."""
        source = dedent(
            """
            <template>
              <div>Hello</div>
            </template>
            <script>
            import os
            x = 10
            </script>"""
        ).lstrip()

        context = analyze_context(source, Position(line=4, character=7))
        assert context.is_python_code
        assert context.full_source == source

    def test_analyze_context_template(self):
        """Test that analyze_context correctly identifies non-script regions."""
        source = dedent(
            """
            <template>
              <div>Hello World</div>
            </template>"""
        ).lstrip()

        context = analyze_context(source, Position(line=1, character=5))
        assert not context.is_python_code


class TestPythonCompletions:
    """Test Python completions in script sections."""

    @pytest.mark.asyncio
    async def test_completion_context_in_script(self):
        """Test that context is correctly detected in script sections."""
        source = dedent(
            """
            <template>
              <div>Hello</div>
            </template>
            <script>
            import os
            os.
            </script>"""
        ).lstrip()

        context = analyze_context(source, Position(line=5, character=3))
        assert context.is_python_code

    @pytest.mark.asyncio
    async def test_no_completion_in_template(self):
        """Test that completions are not provided in template regions."""
        source = dedent(
            """
            <template>
              <div>Hello World</div>
            </template>
            <script>
            import os
            </script>"""
        ).lstrip()

        # Cursor in template section
        context = analyze_context(source, Position(line=1, character=5))
        assert not context.is_python_code


class TestEdgeCases:
    """Test edge cases and error handling for script section detection."""

    def test_malformed_cgx_file(self):
        """Test handling of malformed .cgx files."""
        source = "<script>import os\nos."  # No closing tag

        # Should not crash
        context = analyze_context(source, Position(line=1, character=3))
        # Without closing tag, won't detect as script region (acceptable limitation)
        # The important thing is it doesn't crash
        assert isinstance(context.is_python_code, bool)

    def test_script_with_type_attribute(self):
        """Test <script> tag with type attribute."""
        source = dedent(
            """
            <script type="text/python">
            import os
            os.path
            </script>"""
        ).lstrip()

        position = Position(line=2, character=3)  # "os.path"
        assert is_in_script_region(source, position)

    def test_multiple_script_sections(self):
        """Test handling of multiple <script> sections."""
        source = dedent(
            """
            <script>
            import os
            </script>
            <template>
                <div>Test</div>
            </template>
            <script>
            import sys
            </script>"""
        ).lstrip()

        # First script section
        assert is_in_script_region(source, Position(line=1, character=7))
        # Second script section
        assert is_in_script_region(source, Position(line=7, character=7))
        # Template section (between scripts)
        assert not is_in_script_region(source, Position(line=4, character=5))

    def test_position_to_offset_multiline(self):
        """Test position_to_offset helper with multiline content."""
        source = dedent(
            """
            line1
            line2
            line3"""
        ).lstrip()

        # Start of file
        assert position_to_offset(source, Position(line=0, character=0)) == 0
        # Start of second line
        assert position_to_offset(source, Position(line=1, character=0)) == 6
        # Middle of second line
        assert position_to_offset(source, Position(line=1, character=3)) == 9

    def test_cursor_on_script_tag_boundary(self):
        """Test cursor position at the boundaries of script tag."""
        source = dedent(
            """
            <script>
            import os
            </script>
            """
        ).lstrip()

        # Just inside opening tag
        assert is_in_script_region(source, Position(line=1, character=0))
        # Just before closing tag
        assert is_in_script_region(source, Position(line=1, character=9))
        # On the opening tag itself - should not be inside
        assert not is_in_script_region(source, Position(line=0, character=5))
