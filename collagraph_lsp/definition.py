"""Go-to-definition support for Collagraph .cgx files.

Supports:
- Script → Script: jumping from a variable usage to its definition
- Template → Script: jumping from {{ variable }} to its definition in <script>
"""

import ast
import logging
import re
from dataclasses import dataclass
from functools import lru_cache

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


def build_symbol_table(block: ScriptBlock) -> dict[str, SymbolDefinition]:
    """Build a symbol table from the Python code in a script block using the ast module."""
    symbols: dict[str, SymbolDefinition] = {}
    try:
        tree = ast.parse(block.content)
    except SyntaxError:
        logger.warning("Failed to parse script block as Python")
        return symbols

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            symbols[node.name] = SymbolDefinition(
                name=node.name,
                line=block.start_line + node.lineno - 1,
                column=node.col_offset + 4,  # 'def '
            )
        elif isinstance(node, ast.AsyncFunctionDef):
            symbols[node.name] = SymbolDefinition(
                name=node.name,
                line=block.start_line + node.lineno - 1,
                column=node.col_offset + 10,  # 'async def '
            )
        elif isinstance(node, ast.ClassDef):
            symbols[node.name] = SymbolDefinition(
                name=node.name,
                line=block.start_line + node.lineno - 1,
                column=node.col_offset + 6,
            )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for name, lineno, col_offset in _collect_target_names(target):
                    symbols[name] = SymbolDefinition(
                        name=name,
                        line=block.start_line + lineno - 1,
                        column=col_offset,
                    )
        elif isinstance(node, ast.AnnAssign) and node.target:
            for name, lineno, col_offset in _collect_target_names(node.target):
                symbols[name] = SymbolDefinition(
                    name=name,
                    line=block.start_line + lineno - 1,
                    column=col_offset,
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname if alias.asname else alias.name
                symbols[bound_name] = SymbolDefinition(
                    name=bound_name,
                    line=block.start_line + node.lineno - 1,
                    column=node.col_offset,
                )
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound_name = alias.asname if alias.asname else alias.name
                symbols[bound_name] = SymbolDefinition(
                    name=bound_name,
                    line=block.start_line + node.lineno - 1,
                    column=node.col_offset,
                )
        elif isinstance(node, ast.NamedExpr):
            symbols[node.target.id] = SymbolDefinition(
                name=node.target.id,
                line=block.start_line + node.target.lineno - 1,
                column=node.target.col_offset,
            )

    return symbols


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
    while end < len(source) - 1 and (
        source[end + 1].isalnum() or source[end + 1] == "_"
    ):
        end += 1

    word = source[start : end + 1]
    # Must be a valid identifier (not a keyword-only check, just basic validation)
    if word.isidentifier():
        return word
    return None


def get_definition(source: str, position: Position, uri: str) -> Location | None:
    """
    Find the definition of the symbol at the given position.

    Supports cursors in:
    - <script> blocks (script → script)
    - {{ interpolations }} in <template> blocks (template → script)

    Returns an LSP Location or None if no definition is found.
    """
    symbols = get_symbols(source)
    if not symbols:
        logger.warning("Could not construct symbols")
        return None

    offset = _position_to_offset(source, position)
    word = _get_word_at_offset(source, offset)
    if not word:
        logger.info(f"No word found at {source}, {position}")
        return None

    if sym := symbols.get(word):
        return Location(
            uri=uri,
            range=Range(
                start=Position(line=sym.line, character=sym.column),
                end=Position(line=sym.line, character=sym.column + len(sym.name)),
            ),
        )
    return None


@lru_cache(maxsize=16)
def get_symbols(source: str):
    script_blocks = find_script_blocks(source)
    if not script_blocks:
        logger.warning("No code block found")
        return None

    # Build a merged symbol table from all script blocks
    all_symbols: dict[str, SymbolDefinition] = {}
    for block in script_blocks:
        symbols = build_symbol_table(block)
        # Bug if there are multiple definitions for the same name
        # We could also keep a list per symbol name
        # But that would also require being able to return multiple locations
        all_symbols.update(symbols)

    return all_symbols
