"""Completion support for Collagraph .cgx files."""

import logging
import re
from dataclasses import dataclass

import jedi
from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    InsertTextFormat,
    Position,
)


@dataclass
class ScriptRegion:
    """Information about a script region and the cursor position within it."""

    in_script: bool
    script_content: str | None
    script_line: int | None  # Line within script content (0-based)
    script_column: int | None  # Column within script content (0-based)


def extract_script_region(source: str, position: Position) -> ScriptRegion:
    """
    Extract script region and transform position to be relative to script content.

    Handles multiple <script> sections by finding the one containing the cursor.

    Returns:
        ScriptRegion with:
        - in_script: True if cursor is inside <script> content
        - script_content: The Python code inside <script> tags (if in_script)
        - script_line: Line number within script content (0-based, if in_script)
        - script_column: Column number within script content (0-based, if in_script)
    """
    script_pattern = r"<script[^>]*>(.*?)</script>"

    # Calculate offset of cursor position in full source
    source_offset = position_to_offset(source, position)

    # Find all script sections and check which one contains the cursor
    for match in re.finditer(script_pattern, source, re.DOTALL):
        script_content = match.group(1)
        script_start_offset = match.start(1)
        script_end_offset = match.end(1)

        # Check if cursor is within this script content
        if script_start_offset <= source_offset <= script_end_offset:
            # Calculate position within script content
            script_offset = source_offset - script_start_offset

            # Convert offset to line/column within script
            script_lines = script_content.split("\n")
            current_offset = 0
            script_line = 0
            script_column = 0

            for line_idx, line in enumerate(script_lines):
                if current_offset + len(line) + 1 > script_offset:  # +1 for newline
                    script_line = line_idx
                    script_column = script_offset - current_offset
                    break
                current_offset += len(line) + 1

            return ScriptRegion(
                in_script=True,
                script_content=script_content,
                script_line=script_line,
                script_column=script_column,
            )

    # No script section contains the cursor
    return ScriptRegion(
        in_script=False,
        script_content=None,
        script_line=None,
        script_column=None,
    )


def position_to_offset(source: str, position: Position) -> int:
    """Convert Position (line, character) to string offset."""
    lines = source.split("\n")
    offset = sum(len(line) + 1 for line in lines[: position.line])  # +1 for newline
    offset += position.character
    return offset


async def get_python_completions(
    script_region: ScriptRegion,
) -> list[CompletionItem]:
    """
    Get Python completions using Jedi for script sections.

    Phase 1: Provide completions for <script> section content.
    Jedi can handle incomplete code (like "os.") which is common during typing.

    Args:
        script_region: ScriptRegion containing script content and cursor position

    Returns:
        List of completion items from Jedi
    """
    if not script_region.in_script or not script_region.script_content:
        return []

    try:
        # Use Jedi for Python completions on the script content
        # Jedi handles incomplete code gracefully
        script = jedi.Script(code=script_region.script_content)

        # Get completions (Jedi uses 1-based line numbers)
        completions = script.complete(
            line=script_region.script_line + 1,
            column=script_region.script_column,
        )

        # Convert Jedi completions to LSP CompletionItems
        items = []
        for comp in completions:
            items.append(
                CompletionItem(
                    label=comp.name,
                    kind=map_jedi_type_to_lsp(comp.type),
                    detail=comp.description,
                    documentation=comp.docstring(raw=True)
                    if comp.docstring()
                    else None,
                    insert_text=comp.name,
                    insert_text_format=InsertTextFormat.PlainText,
                    sort_text=comp.name,
                )
            )

        return items

    except Exception as e:
        # Return empty list on any error
        logging.warning(f"Completion failed with error: {e}")
        return []


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
