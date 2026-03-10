"""Shared utilities for Collagraph .cgx file parsing."""

import re
from dataclasses import dataclass

from lsprotocol.types import Position


@dataclass
class ScriptBlock:
    """Parsed <script> block with its position in the .cgx file."""

    content: str
    start_line: int  # 0-based line of first line of content (after <script> tag)
    start_offset: int  # character offset in full source where content starts
    end_offset: int  # character offset in full source where content ends


def position_to_offset(source: str, position: Position) -> int:
    """Convert a Position (line, character) to a character offset in the source."""
    lines = source.split("\n")
    offset = sum(len(line) + 1 for line in lines[: position.line])  # +1 for newline
    offset += position.character
    return offset


def find_script_blocks(source: str) -> list[ScriptBlock]:
    """
    Find all <script> blocks in a .cgx source and return their content and offsets.
    """
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
