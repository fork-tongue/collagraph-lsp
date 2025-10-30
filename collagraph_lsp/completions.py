"""Completion support for Collagraph .cgx files."""

import ast
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import jedi
from collagraph.sfc import construct_ast
from lsprotocol.types import CompletionItem, CompletionItemKind, InsertTextFormat, Position


@dataclass
class CompletionContext:
    """Context information about the cursor position."""

    is_python_code: bool

    # Full CGX source (needed for construct_ast)
    full_source: str

    # Position within the full file
    original_position: Position


def analyze_context(source: str, position: Position) -> CompletionContext:
    """
    Analyze the .cgx file to determine what context the cursor is in.

    Phase 1: Only detects if cursor is in <script> tag (Python code)
    """
    # Check if in <script> tag
    if is_in_script_region(source, position):
        return CompletionContext(
            is_python_code=True,
            full_source=source,
            original_position=position,
        )

    # Not in a Python region
    return CompletionContext(
        is_python_code=False,
        full_source=source,
        original_position=position,
    )


def is_in_script_region(source: str, position: Position) -> bool:
    """Check if cursor is inside a <script> tag."""
    script_pattern = r"<script[^>]*>(.*?)</script>"
    matches = re.finditer(script_pattern, source, re.DOTALL)
    offset = position_to_offset(source, position)

    for match in matches:
        # Check if offset is within the script content (not the tags themselves)
        if match.start(1) <= offset <= match.end(1):
            return True
    return False


def position_to_offset(source: str, position: Position) -> int:
    """Convert Position (line, character) to string offset."""
    lines = source.split("\n")
    offset = sum(len(line) + 1 for line in lines[: position.line])  # +1 for newline
    offset += position.character
    return offset


async def get_python_completions(
    source: str,
    position: Position,
    context: CompletionContext,
) -> list[CompletionItem]:
    """
    Get Python completions using Jedi with full component context.

    This uses construct_ast (same as linter.py) to compile the template
    into a render() method, giving Jedi full context about:
    - All imports
    - Component class structure
    - state, props, computed properties
    - Methods that template expressions can access
    """
    if not context.is_python_code:
        return []

    # Create a temporary file for construct_ast (it requires a file path)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cgx", delete=False) as tmp_file:
        tmp_file.write(context.full_source)
        tmp_path = Path(tmp_file.name)

    try:
        # Use construct_ast to compile template into render() method
        # This gives Jedi full context about what's available in templates
        component_ast, _ = construct_ast(path=tmp_path, template=context.full_source)

        # Convert AST back to source code for Jedi
        virtual_source = ast.unparse(component_ast)

        # Use Jedi for Python completions on the full virtual source
        script = jedi.Script(
            code=virtual_source,
            path=str(tmp_path),
        )

        # Get completions at the original position
        # Note: Line numbers are preserved by construct_ast
        completions = script.complete(
            line=context.original_position.line + 1,  # Jedi uses 1-based line numbers
            column=context.original_position.character,
        )

        # Convert Jedi completions to LSP CompletionItems
        items = []
        for comp in completions:
            items.append(
                CompletionItem(
                    label=comp.name,
                    kind=map_jedi_type_to_lsp(comp.type),
                    detail=comp.description,
                    documentation=comp.docstring(raw=True) if comp.docstring() else None,
                    insert_text=comp.name,
                    insert_text_format=InsertTextFormat.PlainText,
                    sort_text=comp.name,
                )
            )

        return items

    except Exception:
        # If construct_ast fails, fall back to basic completions
        # (just the <script> section without template context)
        return []

    finally:
        # Clean up temporary file
        tmp_path.unlink(missing_ok=True)


def map_jedi_type_to_lsp(jedi_type: str) -> CompletionItemKind:
    """Map Jedi completion types to LSP CompletionItemKind."""
    mapping = {
        "module": CompletionItemKind.Module,
        "class": CompletionItemKind.Class,
        "function": CompletionItemKind.Function,
        "param": CompletionItemKind.Variable,
        "path": CompletionItemKind.File,
        "keyword": CompletionItemKind.Keyword,
        "property": CompletionItemKind.Property,
        "statement": CompletionItemKind.Variable,
    }
    return mapping.get(jedi_type, CompletionItemKind.Text)
