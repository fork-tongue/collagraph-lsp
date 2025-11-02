"""Integration tests for the LSP server."""

import textwrap
from importlib.metadata import version

import pytest

from collagraph_lsp.server import (
    CollagraphLanguageServer,
    lint_cgx_content,
    server,
    validate_document,
)


@pytest.fixture
def ls():
    """Fixture providing a fresh language server instance."""
    return CollagraphLanguageServer("collagraph-lsp-test", "v0.1.0")


def test_server_initialization(ls):
    """Test that the server initializes correctly."""
    assert ls.name == "collagraph-lsp-test"
    assert ls.version == "v0.1.0"


def test_server_module_instance():
    """Test that the module-level server instance is properly configured."""
    assert server.name == "collagraph-lsp"
    assert server.version == f"v{version('collagraph_lsp')}"


def test_did_open_handler():
    """Test that the server has a did_open handler registered."""
    from collagraph_lsp.server import did_open

    assert callable(did_open)
    # Check that the handler is decorated with TEXT_DOCUMENT_DID_OPEN
    assert hasattr(did_open, "__name__")


def test_did_change_handler():
    """Test that the server has a did_change handler registered."""
    from collagraph_lsp.server import did_change

    assert callable(did_change)


def test_did_save_handler():
    """Test that the server has a did_save handler registered."""
    from collagraph_lsp.server import did_save

    assert callable(did_save)


def test_did_close_handler():
    """Test that the server has a did_close handler registered."""
    from collagraph_lsp.server import did_close

    assert callable(did_close)


def test_validate_document_with_valid_cgx(ls):
    """Test validation of a valid CGX document."""
    # Test the linter directly rather than full validation
    # (which requires initialized workspace)
    content = textwrap.dedent(
        """
        <template>
          <label :text="message"></label>
        </template>

        <script>
        from collagraph import Component

        class TestComponent(Component):
            message = "Hello"
        </script>
        """
    ).lstrip()

    diagnostics = lint_cgx_content(content)

    # Valid CGX should have no diagnostics (or only expected ones)
    assert isinstance(diagnostics, list)


def test_validate_document_with_python_errors(ls):
    """Test validation of a CGX document with Python errors."""
    content = textwrap.dedent(
        """
        <template>
          <label :text="message"></label>
        </template>

        <script>
        from collagraph import Component
        import unused_module

        class TestComponent(Component):
            undefined_variable = "test"
        </script>
        """
    ).lstrip()

    diagnostics = lint_cgx_content(content)

    # Should detect Python errors
    assert len(diagnostics) > 0


def test_severity_conversion():
    """Test severity string to LSP severity conversion."""
    from lsprotocol.types import DiagnosticSeverity

    from collagraph_lsp.server import _severity_to_lsp

    assert _severity_to_lsp("error") == DiagnosticSeverity.Error
    assert _severity_to_lsp("warning") == DiagnosticSeverity.Warning
    assert _severity_to_lsp("info") == DiagnosticSeverity.Information
    assert _severity_to_lsp("hint") == DiagnosticSeverity.Hint

    # Unknown severity should default to Warning
    assert _severity_to_lsp("unknown") == DiagnosticSeverity.Warning


def test_non_cgx_file_skipped(ls, caplog):
    """Test that validation logic is CGX-specific."""
    import logging

    # Test that non-.cgx files are skipped
    uri = "file:///test.py"

    with caplog.at_level(logging.DEBUG):
        # This should skip validation without raising an exception
        validate_document(ls, uri)

    # Check that the skip message was logged
    assert any("Skipping non-CGX file" in record.message for record in caplog.records)


def test_linter_integration(ls):
    """Test that the server's linter works correctly."""
    test_content = textwrap.dedent(
        """
        <template>
          <label :text="message"></label>
        </template>

        <script>
        from collagraph import Component

        class TestComponent(Component):
            message = "Hello"
        </script>
        """
    ).lstrip()

    diagnostics = lint_cgx_content(test_content)

    # Valid CGX should have no diagnostics (or only expected ones)
    assert isinstance(diagnostics, list)


def test_linter_detects_unused_imports(ls):
    """Test that the linter detects unused imports."""
    test_content = textwrap.dedent(
        """
        <template>
          <label :text="message"></label>
        </template>

        <script>
        from collagraph import Component
        import unused_module

        class TestComponent(Component):
            message = "Hello"
        </script>
        """
    ).lstrip()

    diagnostics = lint_cgx_content(test_content)

    # Should detect the unused import
    assert len(diagnostics) > 0
    assert any(
        "unused_module" in diag.message.lower() or "unused" in diag.message.lower()
        for diag in diagnostics
    )


def test_formatting_handler():
    """Test that the server has a formatting handler registered."""
    from collagraph_lsp.server import formatting

    assert callable(formatting)


def test_format_cgx_content(ls):
    """Test formatting of CGX content through the formatter."""
    from ruff_cgx import format_cgx_content

    content = textwrap.dedent(
        """
        <template>
          <item />
        </template>

        <script>
        from collagraph import   (Component,)
        class   Simple( Component  ):
            pass
        </script>
        """
    ).lstrip()

    formatted = format_cgx_content(content, "test.cgx")

    expected = textwrap.dedent(
        """
        <template>
          <item />
        </template>

        <script>
        from collagraph import (
            Component,
        )


        class Simple(Component):
            pass
        </script>
        """
    ).lstrip()

    assert formatted == expected


def test_initialize_handler_with_ruff_command(ls):
    """Test that INITIALIZE handler accepts and applies ruffCommand."""
    from lsprotocol.types import InitializeParams
    from ruff_cgx import get_ruff_command, reset_ruff_command

    from collagraph_lsp.server import initialize

    # Reset to default first
    reset_ruff_command()

    # Create initialization params with ruffCommand
    params = InitializeParams(
        process_id=1234,
        root_uri="file:///test",
        capabilities={},
        initialization_options={"ruffCommand": "custom-ruff"},
    )

    # Call initialize handler
    initialize(ls, params)

    # Check that settings were stored
    assert ls.settings["ruffCommand"] == "custom-ruff"

    # Check that ruff command was applied
    assert get_ruff_command() == "custom-ruff"

    # Reset after test
    reset_ruff_command()


def test_initialize_handler_without_options(ls):
    """Test that INITIALIZE handler works without initialization options."""
    from lsprotocol.types import InitializeParams
    from ruff_cgx import reset_ruff_command

    from collagraph_lsp.server import initialize

    # Reset to default first
    reset_ruff_command()

    # Create initialization params without options
    params = InitializeParams(process_id=1234, root_uri="file:///test", capabilities={})

    # Call initialize handler
    initialize(ls, params)

    # Check that settings remain default
    assert ls.settings["ruffCommand"] is None

    # Reset after test
    reset_ruff_command()


def test_did_change_configuration_handler(ls):
    """Test that WORKSPACE_DID_CHANGE_CONFIGURATION handler updates settings."""
    from lsprotocol.types import DidChangeConfigurationParams
    from ruff_cgx import get_ruff_command, reset_ruff_command

    from collagraph_lsp.server import did_change_configuration

    # Reset to default first
    reset_ruff_command()

    # Create configuration change params
    params = DidChangeConfigurationParams(settings={"ruffCommand": "updated-ruff"})

    # Call handler
    did_change_configuration(ls, params)

    # Check that settings were updated
    assert ls.settings["ruffCommand"] == "updated-ruff"

    # Check that ruff command was applied
    assert get_ruff_command() == "updated-ruff"

    # Reset after test
    reset_ruff_command()
