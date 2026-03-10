"""Go-to-definition support for Collagraph .cgx files.

Supports:
- Script → Script: jumping from a variable usage to its definition
- Template → Script: jumping from {{ variable }} to its definition in <script>
"""

import ast
import logging
import re
from dataclasses import dataclass

from lsprotocol.types import Location, Position, Range

logger = logging.getLogger(__name__)


@dataclass
class SymbolDefinition:
    """A symbol defined in a <script> block."""

    name: str
    line: int  # 0-based line within the full .cgx file
    column: int  # 0-based column


@dataclass
class ScriptBlock:
    """Parsed <script> block with its position in the .cgx file."""

    content: str
    start_line: int  # 0-based line of first line of content (after <script> tag)
    start_offset: int  # character offset in full source where content starts
    end_offset: int  # character offset in full source where content ends


def find_script_blocks(source: str) -> list[ScriptBlock]:
    """Find all <script> blocks in a .cgx source and return their content and offsets."""
    blocks = []
    for match in re.finditer(r"<script[^>]*>(.*?)</script>", source, re.DOTALL):
        content = match.group(1)
        start_offset = match.start(1)
        end_offset = match.end(1)
        # Count newlines before start_offset to get the start line
        start_line = source[:start_offset].count("\n")
        blocks.append(
            ScriptBlock(
                content=content,
                start_line=start_line,
                start_offset=start_offset,
                end_offset=end_offset,
            )
        )
    return blocks


def _collect_target_names(target: ast.AST) -> list[tuple[str, int, int]]:
    """Collect all names from an assignment target (handles tuples, lists, starred)."""
    results = []
    if isinstance(target, ast.Name):
        results.append((target.id, target.lineno, target.col_offset))
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            results.extend(_collect_target_names(elt))
    elif isinstance(target, ast.Starred):
        results.extend(_collect_target_names(target.value))
    return results


def build_symbol_table(block: ScriptBlock) -> list[SymbolDefinition]:
    """Build a symbol table from the Python code in a script block using the ast module."""
    symbols: list[SymbolDefinition] = []
    try:
        tree = ast.parse(block.content)
    except SyntaxError:
        logger.debug("Failed to parse script block as Python")
        return symbols

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            symbols.append(
                SymbolDefinition(
                    name=node.name,
                    line=block.start_line + node.lineno - 1,
                    column=node.col_offset,
                )
            )
        elif isinstance(node, ast.ClassDef):
            symbols.append(
                SymbolDefinition(
                    name=node.name,
                    line=block.start_line + node.lineno - 1,
                    column=node.col_offset,
                )
            )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for name, lineno, col_offset in _collect_target_names(target):
                    symbols.append(
                        SymbolDefinition(
                            name=name,
                            line=block.start_line + lineno - 1,
                            column=col_offset,
                        )
                    )
        elif isinstance(node, ast.AnnAssign) and node.target:
            for name, lineno, col_offset in _collect_target_names(node.target):
                symbols.append(
                    SymbolDefinition(
                        name=name,
                        line=block.start_line + lineno - 1,
                        column=col_offset,
                    )
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname if alias.asname else alias.name
                symbols.append(
                    SymbolDefinition(
                        name=bound_name,
                        line=block.start_line + node.lineno - 1,
                        column=node.col_offset,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound_name = alias.asname if alias.asname else alias.name
                symbols.append(
                    SymbolDefinition(
                        name=bound_name,
                        line=block.start_line + node.lineno - 1,
                        column=node.col_offset,
                    )
                )
        elif isinstance(node, ast.NamedExpr):
            symbols.append(
                SymbolDefinition(
                    name=node.target.id,
                    line=block.start_line + node.target.lineno - 1,
                    column=node.target.col_offset,
                )
            )

    return symbols


def _find_template_regions(source: str) -> list[tuple[int, int]]:
    """Find <template> regions as (start_offset, end_offset) pairs."""
    regions = []
    for match in re.finditer(r"<template[^>]*>(.*?)</template>", source, re.DOTALL):
        regions.append((match.start(1), match.end(1)))
    return regions


def _position_to_offset(source: str, position: Position) -> int:
    """Convert a Position (line, character) to a character offset in the source."""
    lines = source.split("\n")
    offset = sum(len(line) + 1 for line in lines[: position.line])
    offset += position.character
    return offset


def _get_word_at_offset(source: str, offset: int) -> str | None:
    """Extract the Python identifier at the given offset."""
    if offset < 0 or offset >= len(source):
        return None

    # Check if the character at offset is part of an identifier
    if not (source[offset].isalnum() or source[offset] == "_"):
        return None

    # Walk backwards to find the start of the word
    start = offset
    while start > 0 and (source[start - 1].isalnum() or source[start - 1] == "_"):
        start -= 1

    # Walk forwards to find the end of the word
    end = offset
    while end < len(source) - 1 and (source[end + 1].isalnum() or source[end + 1] == "_"):
        end += 1

    word = source[start : end + 1]
    # Must be a valid identifier (not a keyword-only check, just basic validation)
    if word.isidentifier():
        return word
    return None


def _is_in_template_interpolation(
    source: str, offset: int, template_regions: list[tuple[int, int]]
) -> bool:
    """Check if the offset is inside a {{ ... }} or {{{ ... }}} interpolation within a template."""
    for region_start, region_end in template_regions:
        if region_start <= offset <= region_end:
            # We're inside a template region; check if we're inside {{ }}
            region_text = source[region_start:region_end]
            rel_offset = offset - region_start
            # Find all interpolation spans in the region
            for match in re.finditer(r"\{\{\{?(.*?)\}?\}\}", region_text):
                if match.start() <= rel_offset <= match.end():
                    return True
            return False
    return False


def _is_in_script_block(
    offset: int, script_blocks: list[ScriptBlock]
) -> ScriptBlock | None:
    """Return the script block containing the offset, or None."""
    for block in script_blocks:
        if block.start_offset <= offset <= block.end_offset:
            return block
    return None


def get_definition(
    source: str, position: Position, uri: str
) -> Location | None:
    """
    Find the definition of the symbol at the given position.

    Supports cursors in:
    - <script> blocks (script → script)
    - {{ interpolations }} in <template> blocks (template → script)

    Returns an LSP Location or None if no definition is found.
    """
    script_blocks = find_script_blocks(source)
    if not script_blocks:
        return None

    # Build a merged symbol table from all script blocks
    all_symbols: list[SymbolDefinition] = []
    for block in script_blocks:
        all_symbols.extend(build_symbol_table(block))

    if not all_symbols:
        return None

    offset = _position_to_offset(source, position)
    word = _get_word_at_offset(source, offset)
    if not word:
        return None

    # Check if cursor is in a script block or template interpolation
    in_block = _is_in_script_block(offset, script_blocks)
    template_regions = _find_template_regions(source)
    in_template = _is_in_template_interpolation(source, offset, template_regions)

    if not in_block and not in_template:
        return None

    # Look up the word in the symbol table (first matching definition)
    for sym in all_symbols:
        if sym.name == word:
            return Location(
                uri=uri,
                range=Range(
                    start=Position(line=sym.line, character=sym.column),
                    end=Position(line=sym.line, character=sym.column + len(sym.name)),
                ),
            )

    return None
