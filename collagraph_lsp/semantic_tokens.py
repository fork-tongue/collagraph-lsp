"""Semantic token provider for Collagraph .cgx files."""

import ast
import logging
import re
from typing import List

from collagraph.sfc.parser import CGXParser

logger = logging.getLogger(__name__)

# LSP semantic token types (standard types from the spec)
TOKEN_TYPES = [
    "namespace",
    "class",
    "enum",
    "interface",
    "struct",
    "typeParameter",
    "type",
    "parameter",
    "variable",
    "property",
    "enumMember",
    "decorator",
    "event",
    "function",
    "method",
    "macro",
    "label",
    "comment",
    "string",
    "keyword",
    "number",
    "regexp",
    "operator",
]

# LSP semantic token modifiers
TOKEN_MODIFIERS = [
    "declaration",
    "definition",
    "readonly",
    "static",
    "deprecated",
    "abstract",
    "async",
    "modification",
    "documentation",
    "defaultLibrary",
]


class SemanticToken:
    """Represents a semantic token with its position and type."""

    def __init__(
        self,
        line: int,
        start_char: int,
        length: int,
        token_type: str,
        modifiers: List[str] | None = None,
    ):
        self.line = line
        self.start_char = start_char
        self.length = length
        self.token_type = token_type
        self.modifiers = modifiers or []


class SemanticTokensProvider:
    """Provides semantic tokens for .cgx files."""

    def __init__(self):
        """Initialize the provider."""
        self.token_types = TOKEN_TYPES
        self.token_modifiers = TOKEN_MODIFIERS

    def get_tokens(
        self, content: str, file_path: str = "<stdin>"
    ) -> List[SemanticToken]:
        """
        Extract semantic tokens from a CGX file.

        Args:
            content: The CGX file content
            file_path: Optional file path for better error messages

        Returns:
            List of semantic tokens
        """
        tokens = []

        try:
            # Parse the CGX file
            parser = CGXParser()
            parser.feed(content)

            # Extract tokens from script section
            script_node = parser.root.child_with_tag("script")
            if script_node:
                script_tokens = self._extract_script_tokens(content, script_node)
                tokens.extend(script_tokens)

            # Extract tokens from template section
            template_nodes = [
                node
                for node in parser.root.children
                if not hasattr(node, "tag") or node.tag != "script"
            ]
            for template_node in template_nodes:
                template_tokens = self._extract_template_tokens(
                    content, template_node, parser
                )
                tokens.extend(template_tokens)

        except Exception as e:
            logger.error(f"Error extracting semantic tokens: {e}", exc_info=True)

        # Sort tokens by position
        tokens.sort(key=lambda t: (t.line, t.start_char))
        return tokens

    def _extract_script_tokens(self, content: str, script_node) -> List[SemanticToken]:
        """
        Extract semantic tokens from the script section using AST.

        Args:
            content: The full CGX content
            script_node: The parsed script node

        Returns:
            List of semantic tokens
        """
        tokens = []

        try:
            # Get script section line range
            start_line = script_node.location[0]
            end_line = script_node.end[0] - 1

            # Extract script content
            lines = content.splitlines()
            script_content = "\n".join(lines[start_line:end_line])

            # Parse the Python code
            tree = ast.parse(script_content)

            # Walk the AST and collect tokens
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Class definition
                    tokens.append(
                        SemanticToken(
                            line=start_line + node.lineno - 1,
                            start_char=node.col_offset,
                            length=len(node.name),
                            token_type="class",
                            modifiers=["declaration"],
                        )
                    )

                elif isinstance(node, ast.FunctionDef):
                    # Function/method definition
                    token_type = "method" if self._is_method(node) else "function"
                    modifiers = ["declaration"]
                    if any(
                        isinstance(d, ast.Name) and d.id == "async"
                        for d in getattr(node, "decorator_list", [])
                    ):
                        modifiers.append("async")

                    tokens.append(
                        SemanticToken(
                            line=start_line + node.lineno - 1,
                            start_char=node.col_offset,
                            length=len(node.name),
                            token_type=token_type,
                            modifiers=modifiers,
                        )
                    )

                    # Parameters
                    for arg in node.args.args:
                        if arg.arg != "self" and arg.arg != "cls":
                            tokens.append(
                                SemanticToken(
                                    line=start_line + arg.lineno - 1,
                                    start_char=arg.col_offset,
                                    length=len(arg.arg),
                                    token_type="parameter",
                                    modifiers=["declaration"],
                                )
                            )

                elif isinstance(node, ast.Import):
                    # Import statements
                    for alias in node.names:
                        tokens.append(
                            SemanticToken(
                                line=start_line + node.lineno - 1,
                                start_char=node.col_offset,
                                length=len(alias.name),
                                token_type="namespace",
                            )
                        )

                elif isinstance(node, ast.ImportFrom):
                    # From import statements
                    if node.module:
                        tokens.append(
                            SemanticToken(
                                line=start_line + node.lineno - 1,
                                start_char=node.col_offset,
                                length=len(node.module),
                                token_type="namespace",
                            )
                        )

        except SyntaxError:
            # Script has syntax errors, skip token extraction
            pass
        except Exception as e:
            logger.debug(f"Error extracting script tokens: {e}")

        return tokens

    def _extract_template_tokens(
        self, content: str, template_node, parser
    ) -> List[SemanticToken]:
        """
        Extract semantic tokens from template section.

        Args:
            content: The full CGX content
            template_node: The parsed template node
            parser: The CGX parser

        Returns:
            List of semantic tokens
        """
        tokens = []

        try:
            lines = content.splitlines()

            # Recursively process template nodes
            self._process_template_node(template_node, lines, tokens)

        except Exception as e:
            logger.debug(f"Error extracting template tokens: {e}")

        return tokens

    def _process_template_node(
        self, node, lines: List[str], tokens: List[SemanticToken]
    ):
        """
        Recursively process a template node to extract tokens.

        Args:
            node: The template node to process
            lines: The source lines
            tokens: List to append tokens to
        """
        # Skip text and comment nodes
        if not hasattr(node, "tag"):
            return

        # Get the node's line
        if hasattr(node, "location"):
            line_num = node.location[0]
            if line_num < len(lines):
                line_content = lines[line_num]

                # Extract tag name
                tag_match = re.search(r"<(\w+)", line_content)
                if tag_match:
                    tag_name = tag_match.group(1)
                    tokens.append(
                        SemanticToken(
                            line=line_num,
                            start_char=tag_match.start(1),
                            length=len(tag_name),
                            token_type="class",  # Component names as classes
                        )
                    )

        # Process attributes
        if hasattr(node, "attrs"):
            for attr_name, attr_value in node.attrs.items():
                self._process_attribute(node, attr_name, attr_value, lines, tokens)

        # Process children
        if hasattr(node, "children"):
            for child in node.children:
                self._process_template_node(child, lines, tokens)

    def _process_attribute(
        self,
        node,
        attr_name: str,
        attr_value,
        lines: List[str],
        tokens: List[SemanticToken],
    ):
        """
        Process a template attribute and extract tokens from expressions.

        Args:
            node: The template node
            attr_name: The attribute name
            attr_value: The attribute value
            lines: The source lines
            tokens: List to append tokens to
        """
        if not hasattr(node, "location"):
            return

        line_num = node.location[0]
        if line_num >= len(lines):
            return

        # Find the attribute in the source
        # This is simplified - in production you'd need more robust parsing
        line_content = lines[line_num]

        # Highlight directive names (v-if, v-for, v-bind, v-on, etc.)
        if attr_name.startswith("v-"):
            attr_match = re.search(rf"\b({re.escape(attr_name)})\b", line_content)
            if attr_match:
                tokens.append(
                    SemanticToken(
                        line=line_num,
                        start_char=attr_match.start(1),
                        length=len(attr_name),
                        token_type="decorator",  # Directives as decorators
                    )
                )

        # Highlight shorthand bindings (: and @)
        elif attr_name.startswith(":") or attr_name.startswith("@"):
            attr_match = re.search(
                rf"([{attr_name[0]}]{re.escape(attr_name[1:])})", line_content
            )
            if attr_match:
                tokens.append(
                    SemanticToken(
                        line=line_num,
                        start_char=attr_match.start(1),
                        length=1,  # Just the : or @
                        token_type="operator",
                    )
                )
                # The property/event name
                tokens.append(
                    SemanticToken(
                        line=line_num,
                        start_char=attr_match.start(1) + 1,
                        length=len(attr_name) - 1,
                        token_type="event" if attr_name.startswith("@") else "property",
                    )
                )

        # Extract Python expressions from attribute values
        if isinstance(attr_value, str) and attr_value.strip():
            if attr_name.startswith((":", "@", "v-")):
                # This contains a Python expression
                # We could parse it, but for now just mark it as a variable reference
                # In production, you'd want to parse the expression properly
                pass

    def _is_method(self, node: ast.FunctionDef) -> bool:
        """
        Check if a function definition is a method (has self/cls parameter).

        Args:
            node: The function definition node

        Returns:
            True if it's a method
        """
        if node.args.args:
            first_arg = node.args.args[0].arg
            return first_arg in ("self", "cls")
        return False

    def encode_tokens(self, tokens: List[SemanticToken]) -> List[int]:
        """
        Encode tokens into the LSP semantic tokens format.

        The format is a flat array of integers where each token is represented by
        5 values:
        - Delta line (relative to previous token)
        - Delta start (relative to previous token if same line, absolute otherwise)
        - Length
        - Token type (index into token_types array)
        - Token modifiers (bit flags)

        Args:
            tokens: List of semantic tokens

        Returns:
            Encoded token data as list of integers
        """
        data = []
        prev_line = 0
        prev_start = 0

        for token in tokens:
            # Calculate deltas
            delta_line = token.line - prev_line
            delta_start = (
                token.start_char - prev_start if delta_line == 0 else token.start_char
            )

            # Get token type index
            try:
                token_type_idx = self.token_types.index(token.token_type)
            except ValueError:
                logger.warning(f"Unknown token type: {token.token_type}")
                token_type_idx = 0

            # Encode modifiers as bit flags
            modifier_bits = 0
            for modifier in token.modifiers:
                try:
                    modifier_idx = self.token_modifiers.index(modifier)
                    modifier_bits |= 1 << modifier_idx
                except ValueError:
                    logger.warning(f"Unknown token modifier: {modifier}")

            # Append the 5 values
            data.extend(
                [delta_line, delta_start, token.length, token_type_idx, modifier_bits]
            )

            # Update previous position
            prev_line = token.line
            prev_start = token.start_char

        return data
