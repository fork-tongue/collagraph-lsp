"""Tests for go-to-definition support in Collagraph .cgx files."""

from textwrap import dedent

from lsprotocol.types import Position

from collagraph_lsp.definition import (
    build_symbol_table,
    find_script_blocks,
    get_definition,
)


class TestFindScriptBlocks:
    def test_single_script_block(self):
        source = dedent("""\
            <template>
              <div>Hello</div>
            </template>
            <script>
            x = 1
            </script>""")

        blocks = find_script_blocks(source)
        assert len(blocks) == 1
        assert "x = 1" in blocks[0].content
        assert blocks[0].start_line == 3  # line of content after <script>

    def test_no_script_block(self):
        source = "<template><div>Hello</div></template>"
        blocks = find_script_blocks(source)
        assert len(blocks) == 0

    def test_multiple_script_blocks(self):
        source = dedent("""\
            <script>
            a = 1
            </script>
            <template><div></div></template>
            <script>
            b = 2
            </script>""")

        blocks = find_script_blocks(source)
        assert len(blocks) == 2
        assert "a = 1" in blocks[0].content
        assert "b = 2" in blocks[1].content


class TestBuildSymbolTable:
    def test_assignment(self):
        source = dedent("""\
            <script>
            x = 1
            </script>""")

        blocks = find_script_blocks(source)
        symbols = build_symbol_table(blocks[0])
        names = [s.name for s in symbols]
        assert "x" in names

    def test_function_def(self):
        source = dedent("""\
            <script>
            def handle_click():
                pass
            </script>""")

        blocks = find_script_blocks(source)
        symbols = build_symbol_table(blocks[0])
        names = [s.name for s in symbols]
        assert "handle_click" in names

    def test_class_def(self):
        source = dedent("""\
            <script>
            class MyComponent:
                pass
            </script>""")

        blocks = find_script_blocks(source)
        symbols = build_symbol_table(blocks[0])
        names = [s.name for s in symbols]
        assert "MyComponent" in names

    def test_import(self):
        source = dedent("""\
            <script>
            import os
            from sys import path
            </script>""")

        blocks = find_script_blocks(source)
        symbols = build_symbol_table(blocks[0])
        names = [s.name for s in symbols]
        assert "os" in names
        assert "path" in names

    def test_import_alias(self):
        source = dedent("""\
            <script>
            import numpy as np
            from collections import OrderedDict as OD
            </script>""")

        blocks = find_script_blocks(source)
        symbols = build_symbol_table(blocks[0])
        names = [s.name for s in symbols]
        assert "np" in names
        assert "OD" in names
        assert "numpy" not in names
        assert "OrderedDict" not in names

    def test_tuple_unpacking(self):
        source = dedent("""\
            <script>
            a, b = 1, 2
            </script>""")

        blocks = find_script_blocks(source)
        symbols = build_symbol_table(blocks[0])
        names = [s.name for s in symbols]
        assert "a" in names
        assert "b" in names

    def test_annotated_assignment(self):
        source = dedent("""\
            <script>
            x: int = 5
            </script>""")

        blocks = find_script_blocks(source)
        symbols = build_symbol_table(blocks[0])
        names = [s.name for s in symbols]
        assert "x" in names

    def test_async_function_def(self):
        source = dedent("""\
            <script>
            async def fetch_data():
                pass
            </script>""")

        blocks = find_script_blocks(source)
        symbols = build_symbol_table(blocks[0])
        names = [s.name for s in symbols]
        assert "fetch_data" in names

    def test_walrus_operator(self):
        source = dedent("""\
            <script>
            result = [y := 10]
            </script>""")

        blocks = find_script_blocks(source)
        symbols = build_symbol_table(blocks[0])
        names = [s.name for s in symbols]
        assert "y" in names
        assert "result" in names

    def test_syntax_error_returns_empty(self):
        source = dedent("""\
            <script>
            def (broken
            </script>""")

        blocks = find_script_blocks(source)
        symbols = build_symbol_table(blocks[0])
        assert symbols == []

    def test_line_numbers_are_absolute(self):
        source = dedent("""\
            <template>
              <div>Hello</div>
            </template>
            <script>
            x = 1
            def foo():
                pass
            </script>""")

        blocks = find_script_blocks(source)
        symbols = build_symbol_table(blocks[0])
        sym_x = next(s for s in symbols if s.name == "x")
        sym_foo = next(s for s in symbols if s.name == "foo")
        # x is on line 4 (0-based), foo on line 5
        assert sym_x.line == 4
        assert sym_foo.line == 5


class TestGetDefinitionScriptToScript:
    def test_simple_assignment(self):
        source = dedent("""\
            <template>
              <div>Hello</div>
            </template>
            <script>
            x = 1
            print(x)
            </script>""")

        # Cursor on 'x' in print(x) — line 5, character 6
        result = get_definition(source, Position(line=5, character=6), "file:///test.cgx")
        assert result is not None
        assert result.range.start.line == 4
        assert result.range.start.character == 0

    def test_function_def(self):
        source = dedent("""\
            <script>
            def handle_click():
                pass
            handle_click()
            </script>""")

        # Cursor on 'handle_click' in the call — line 3
        result = get_definition(source, Position(line=3, character=0), "file:///test.cgx")
        assert result is not None
        assert result.range.start.line == 1

    def test_import(self):
        source = dedent("""\
            <script>
            from os import path
            print(path)
            </script>""")

        # Cursor on 'path' in print(path)
        result = get_definition(source, Position(line=2, character=6), "file:///test.cgx")
        assert result is not None
        assert result.range.start.line == 1

    def test_undefined_variable(self):
        source = dedent("""\
            <script>
            x = 1
            print(undefined_var)
            </script>""")

        # Cursor on 'undefined_var'
        result = get_definition(source, Position(line=2, character=6), "file:///test.cgx")
        assert result is None

    def test_cursor_on_non_identifier(self):
        source = dedent("""\
            <script>
            x = 1 + 2
            </script>""")

        # Cursor on '+' operator — line 1, character 6
        result = get_definition(source, Position(line=1, character=6), "file:///test.cgx")
        assert result is None


class TestGetDefinitionTemplateToScript:
    def test_template_interpolation_to_script(self):
        source = dedent("""\
            <template>
              <div>{{ message }}</div>
            </template>
            <script>
            message = "Hello"
            </script>""")

        # Cursor on 'message' in {{ message }} — line 1
        # "  <div>{{ message }}</div>" — 'message' starts at character 12
        result = get_definition(source, Position(line=1, character=12), "file:///test.cgx")
        assert result is not None
        assert result.range.start.line == 4
        assert result.range.start.character == 0

    def test_template_interpolation_undefined(self):
        source = dedent("""\
            <template>
              <div>{{ unknown_var }}</div>
            </template>
            <script>
            x = 1
            </script>""")

        # Cursor on 'unknown_var' in {{ unknown_var }}
        result = get_definition(source, Position(line=1, character=12), "file:///test.cgx")
        assert result is None

    def test_cursor_outside_interpolation(self):
        source = dedent("""\
            <template>
              <div>Hello World</div>
            </template>
            <script>
            x = 1
            </script>""")

        # Cursor on 'Hello' in template text (not in {{ }})
        result = get_definition(source, Position(line=1, character=8), "file:///test.cgx")
        assert result is None

    def test_triple_brace_interpolation(self):
        source = dedent("""\
            <template>
              <div>{{{ message }}}</div>
            </template>
            <script>
            message = "Hello"
            </script>""")

        # Cursor on 'message' in {{{ message }}}
        result = get_definition(source, Position(line=1, character=13), "file:///test.cgx")
        assert result is not None
        assert result.range.start.line == 4

    def test_function_from_template(self):
        source = dedent("""\
            <template>
              <button @click="{{ handle_click }}">Click</button>
            </template>
            <script>
            def handle_click():
                pass
            </script>""")

        # Cursor on 'handle_click' in {{ handle_click }}
        result = get_definition(source, Position(line=1, character=24), "file:///test.cgx")
        assert result is not None
        assert result.range.start.line == 4


class TestGetDefinitionEdgeCases:
    def test_no_script_block(self):
        source = "<template><div>{{ x }}</div></template>"
        result = get_definition(source, Position(line=0, character=19), "file:///test.cgx")
        assert result is None

    def test_cursor_outside_script_and_template(self):
        source = dedent("""\
            <template>
              <div>Hello</div>
            </template>
            <script>
            x = 1
            </script>
            <style>
            .foo { color: red; }
            </style>""")

        # Cursor in <style> block
        result = get_definition(source, Position(line=7, character=1), "file:///test.cgx")
        assert result is None

    def test_definition_uri_preserved(self):
        source = dedent("""\
            <script>
            x = 1
            print(x)
            </script>""")

        uri = "file:///path/to/component.cgx"
        result = get_definition(source, Position(line=2, character=6), uri)
        assert result is not None
        assert result.uri == uri


class TestDefinitionHandlerRegistered:
    def test_definition_handler_exists(self):
        from collagraph_lsp.server import definition

        assert callable(definition)
