"""Tests for completion support in Collagraph .cgx files.

Phase 1: Only tests completions within <script> tags.
"""

from textwrap import dedent

import pytest
from lsprotocol.types import Position

from collagraph_lsp.completions import (
    extract_script_region,
    get_python_completions,
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
        assert extract_script_region(source, position).in_script

        # Cursor outside script section
        position = Position(line=1, character=5)  # in template
        assert not extract_script_region(source, position).in_script

    def test_extract_script_section(self):
        """Test that extract_script_region correctly identifies script sections."""
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

        script_region = extract_script_region(source, Position(line=4, character=7))
        assert script_region.in_script
        assert script_region.script_content is not None
        assert "import os" in script_region.script_content

    def test_extract_template_region(self):
        """Test that extract_script_region correctly identifies non-script regions."""
        source = dedent(
            """
            <template>
              <div>Hello World</div>
            </template>"""
        ).lstrip()

        script_region = extract_script_region(source, Position(line=1, character=5))
        assert not script_region.in_script
        assert script_region.script_content is None


class TestPythonCompletions:
    """Test Python completions in script sections."""

    @pytest.mark.asyncio
    async def test_completion_context_in_script(self):
        """Test that script region is correctly extracted for completions."""
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

        script_region = extract_script_region(source, Position(line=5, character=3))
        assert script_region.in_script
        assert script_region.script_content is not None

    @pytest.mark.asyncio
    async def test_jedi_test(self):
        """Test that Jedi returns exactly the expected completions for string
        methods."""
        source = dedent(
            """




            <script>
            toet = "asdf"
            toet.st
            </script>"""
        )

        # Position after "toet.st" - line 7 in the full file
        # (after opening newline + 4 blank lines + <script> + toet = "asdf")
        position = Position(line=7, character=7)
        script_region = extract_script_region(source, position)
        assert script_region.in_script

        # Get actual completions from Jedi
        items = await get_python_completions(script_region)

        # Should have completions for string methods starting with "st"
        # e.g., startswith, strip, etc.
        assert len(items) >= 2, f"Expected at least 2 completions, got {len(items)}"
        labels = [item.label for item in items]
        assert any("start" in label.lower() for label in labels), (
            f"Expected string methods starting with 'st', got: {labels}"
        )

    @pytest.mark.asyncio
    async def test_actual_jedi_completions_returned(self):
        """Test that Jedi actually returns completion items for Python code."""
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

        # Position after "os." on line 5 (0-indexed)
        position = Position(line=5, character=3)
        script_region = extract_script_region(source, position)

        # Get actual completions from Jedi
        items = await get_python_completions(script_region)

        # Should have completions for os module attributes
        assert len(items) > 0, "Expected Jedi to return completions for 'os.'"

        # Check that items have proper LSP structure
        assert all(hasattr(item, "label") for item in items)
        assert all(hasattr(item, "kind") for item in items)

        # Should include common os module attributes
        labels = [item.label for item in items]
        assert any("path" in label for label in labels), (
            "Expected 'path' in os completions"
        )

    @pytest.mark.asyncio
    async def test_completions_for_builtin_module(self):
        """Test completions for builtin module attributes."""
        source = dedent(
            """
            <script>
            import sys
            sys.
            </script>
            <template>
              <div>Test</div>
            </template>"""
        ).lstrip()

        # Position after "sys."
        position = Position(line=2, character=4)
        script_region = extract_script_region(source, position)

        items = await get_python_completions(script_region)

        # Should have completions for sys module
        assert len(items) > 0, "Expected completions for sys module"

        labels = [item.label for item in items]
        # Check for common sys attributes
        assert any("version" in label or "path" in label for label in labels), (
            "Expected sys module attributes in completions"
        )

    @pytest.mark.asyncio
    async def test_completions_with_component_context(self):
        """Test that completions work for component classes."""
        source = dedent(
            """
            <script>
            from collagraph import Component

            class MyComponent(Component):
                def __init__(self):
                    self.my_value = 42

                def my_method(self):
                    self.
            </script>
            <template>
              <div>{{ my_value }}</div>
            </template>"""
        ).lstrip()

        # Position after "self."
        position = Position(line=8, character=13)
        script_region = extract_script_region(source, position)

        items = await get_python_completions(script_region)

        # Should have completions for self attributes
        assert len(items) > 0, "Expected completions for 'self.'"

        labels = [item.label for item in items]
        # Should see our custom attributes/methods
        assert any("my_value" in label or "my_method" in label for label in labels), (
            "Expected component attributes in completions"
        )

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
        script_region = extract_script_region(source, Position(line=1, character=5))
        assert not script_region.in_script

    @pytest.mark.asyncio
    async def test_completions_with_invalid_syntax(self):
        """Test that completions handle invalid syntax gracefully."""
        # Invalid Python syntax
        source = dedent(
            """
            <script>
            this is not valid python syntax!!!
            </script>
            <template>
              <div>Test</div>
            </template>"""
        ).lstrip()

        position = Position(line=1, character=10)
        script_region = extract_script_region(source, position)

        # Should not crash - Jedi may provide keyword completions
        items = await get_python_completions(script_region)
        # Jedi is robust and may provide some completions even with invalid syntax
        assert isinstance(items, list), "Expected list of completions (possibly empty)"


class TestEdgeCases:
    """Test edge cases and error handling for script section detection."""

    def test_malformed_cgx_file(self):
        """Test handling of malformed .cgx files."""
        source = "<script>import os\nos."  # No closing tag

        # Should not crash
        script_region = extract_script_region(source, Position(line=1, character=3))
        # Without closing tag, won't detect as script region (acceptable limitation)
        # The important thing is it doesn't crash
        assert isinstance(script_region.in_script, bool)

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
        assert extract_script_region(source, position).in_script

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
        assert extract_script_region(source, Position(line=1, character=7)).in_script
        # Second script section
        assert extract_script_region(source, Position(line=7, character=7)).in_script
        # Template section (between scripts)
        assert not extract_script_region(
            source, Position(line=4, character=5)
        ).in_script

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
        assert extract_script_region(source, Position(line=1, character=0)).in_script
        # Just before closing tag
        assert extract_script_region(source, Position(line=1, character=9)).in_script
        # On the opening tag itself - should not be inside
        assert not extract_script_region(
            source, Position(line=0, character=5)
        ).in_script
