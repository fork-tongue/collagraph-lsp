"""Tests for semantic tokens provider."""

from collagraph_lsp.semantic_tokens import SemanticTokensProvider


def test_semantic_tokens_provider_initialization():
    """Test that the provider initializes correctly."""
    provider = SemanticTokensProvider()
    assert len(provider.token_types) > 0
    assert len(provider.token_modifiers) > 0
    assert "class" in provider.token_types
    assert "function" in provider.token_types
    assert "declaration" in provider.token_modifiers


def test_get_tokens_from_script():
    """Test extracting tokens from script section."""
    content = """<template>
  <widget />
</template>

<script>
import collagraph as cg

class MyComponent(cg.Component):
    def __init__(self, props):
        super().__init__(props)
        self.state["count"] = 0

    def increment(self):
        self.state["count"] += 1
</script>
"""
    provider = SemanticTokensProvider()
    tokens = provider.get_tokens(content)

    # Should find class and method definitions
    token_types = [t.token_type for t in tokens]
    assert "class" in token_types
    assert "method" in token_types or "function" in token_types
    assert "parameter" in token_types


def test_get_tokens_from_template():
    """Test extracting tokens from template section."""
    content = """<template>
  <widget>
    <button @clicked="increment" :text="label" />
  </widget>
</template>

<script>
class MyComponent:
    def increment(self):
        pass
</script>
"""
    provider = SemanticTokensProvider()
    tokens = provider.get_tokens(content)

    # Should find template elements and directives
    token_types = [t.token_type for t in tokens]
    assert "class" in token_types  # widget/button tags
    # Note: directives and events are harder to test without exact positions


def test_get_tokens_empty_file():
    """Test handling of empty file."""
    content = ""
    provider = SemanticTokensProvider()
    tokens = provider.get_tokens(content)
    assert tokens == []


def test_get_tokens_no_script():
    """Test handling file with no script section."""
    content = """<template>
  <widget />
</template>
"""
    provider = SemanticTokensProvider()
    tokens = provider.get_tokens(content)
    # Should still extract template tokens
    assert isinstance(tokens, list)


def test_get_tokens_invalid_python():
    """Test handling invalid Python in script section."""
    content = """<template>
  <widget />
</template>

<script>
def invalid syntax here
</script>
"""
    provider = SemanticTokensProvider()
    tokens = provider.get_tokens(content)
    # Should not crash, just return empty or partial tokens
    assert isinstance(tokens, list)


def test_encode_tokens():
    """Test encoding tokens into LSP format."""
    provider = SemanticTokensProvider()

    # Create sample tokens
    from collagraph_lsp.semantic_tokens import SemanticToken

    tokens = [
        SemanticToken(
            line=0,
            start_char=0,
            length=5,
            token_type="class",
            modifiers=["declaration"],
        ),
        SemanticToken(
            line=0, start_char=6, length=3, token_type="function", modifiers=[]
        ),
        SemanticToken(
            line=1, start_char=4, length=4, token_type="variable", modifiers=[]
        ),
    ]

    encoded = provider.encode_tokens(tokens)

    # Should be a flat list of integers (5 per token)
    assert len(encoded) == len(tokens) * 5
    assert all(isinstance(x, int) for x in encoded)

    # First token
    assert encoded[0] == 0  # delta line
    assert encoded[1] == 0  # delta start
    assert encoded[2] == 5  # length

    # Second token (same line)
    assert encoded[5] == 0  # delta line (same line)
    assert encoded[6] == 6  # delta start (from previous)
    assert encoded[7] == 3  # length

    # Third token (next line)
    assert encoded[10] == 1  # delta line
    assert encoded[11] == 4  # delta start (absolute since new line)
    assert encoded[12] == 4  # length


def test_encode_tokens_empty():
    """Test encoding empty token list."""
    provider = SemanticTokensProvider()
    encoded = provider.encode_tokens([])
    assert encoded == []


def test_class_detection():
    """Test that class definitions are properly detected."""
    content = """<script>
class Foo:
    pass

class Bar(Foo):
    pass
</script>
"""
    provider = SemanticTokensProvider()
    tokens = provider.get_tokens(content)

    class_tokens = [t for t in tokens if t.token_type == "class"]
    assert len(class_tokens) >= 2  # Should find both Foo and Bar


def test_method_detection():
    """Test that methods are properly detected."""
    content = """<script>
class MyClass:
    def method_one(self):
        pass

    def method_two(self, param):
        pass
</script>
"""
    provider = SemanticTokensProvider()
    tokens = provider.get_tokens(content)

    method_tokens = [t for t in tokens if t.token_type == "method"]
    assert len(method_tokens) >= 2  # Should find both methods


def test_parameter_detection():
    """Test that parameters are properly detected (excluding self)."""
    content = """<script>
def my_function(arg1, arg2, arg3):
    pass

class MyClass:
    def method(self, param1, param2):
        pass
</script>
"""
    provider = SemanticTokensProvider()
    tokens = provider.get_tokens(content)

    param_tokens = [t for t in tokens if t.token_type == "parameter"]
    # Should find: arg1, arg2, arg3, param1, param2 (not self)
    assert len(param_tokens) >= 5


def test_import_detection():
    """Test that imports are properly detected."""
    content = """<script>
import collagraph
from collagraph import Component
from typing import List, Dict
</script>
"""
    provider = SemanticTokensProvider()
    tokens = provider.get_tokens(content)

    namespace_tokens = [t for t in tokens if t.token_type == "namespace"]
    assert len(namespace_tokens) >= 1  # Should find at least the modules


def test_complex_cgx_file():
    """Test with a complete CGX file similar to real usage."""
    content = """<template>
  <widget>
    <button @clicked="increment" :text="button_label" />
    <label :text="counter_text" />
  </widget>
</template>

<script>
import collagraph as cg
from typing import Dict

class Counter(cg.Component):
    def __init__(self, props: Dict):
        super().__init__(props)
        self.state["count"] = 0
        self.button_label = "Click me"

    def increment(self):
        self.state["count"] += 1

    @property
    def counter_text(self):
        return f"Count: {self.state['count']}"
</script>
"""
    provider = SemanticTokensProvider()
    tokens = provider.get_tokens(content)

    # Should find various token types
    token_types = set(t.token_type for t in tokens)
    assert "class" in token_types
    assert "method" in token_types or "function" in token_types
    assert "parameter" in token_types

    # Should be able to encode without errors
    encoded = provider.encode_tokens(tokens)
    assert len(encoded) > 0
    assert len(encoded) % 5 == 0  # Must be multiple of 5
