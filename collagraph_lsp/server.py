"""Main LSP server implementation for Collagraph files."""

import logging
from importlib.metadata import version

from lsprotocol.types import (
    INITIALIZE,
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_FORMATTING,
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    WORKSPACE_DID_CHANGE_CONFIGURATION,
    CompletionList,
    CompletionOptions,
    CompletionParams,
    DiagnosticSeverity,
    DidChangeConfigurationParams,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    DocumentFormattingParams,
    InitializeParams,
    Position,
    PublishDiagnosticsParams,
    Range,
    SemanticTokens,
    SemanticTokensLegend,
    SemanticTokensParams,
    TextEdit,
)
from lsprotocol.types import (
    Diagnostic as LspDiagnostic,
)
from pygls.lsp.server import LanguageServer
from ruff_cgx import (
    format_cgx_content,
    get_ruff_command,
    lint_cgx_content,
    set_ruff_command,
)

from .completions import extract_script_region, get_python_completions
from .semantic_tokens import SemanticTokensProvider

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CollagraphLanguageServer(LanguageServer):
    """Language server for Collagraph .cgx files."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.semantic_tokens_provider = SemanticTokensProvider()
        # Configuration settings
        self.settings = {
            "ruffCommand": None,  # None means use ruff_cgx default (env var or "ruff")
        }


# Create the server instance
server = CollagraphLanguageServer("collagraph-lsp", f"v{version('collagraph_lsp')}")


def _apply_ruff_command(ruff_command: str | None):
    """
    Apply the ruff command configuration.

    Args:
        ruff_command: Path or command name for ruff executable, or None to use default
    """
    if ruff_command:
        logger.info(f"Setting ruff command to: {ruff_command}")
        set_ruff_command(ruff_command)
    else:
        # Use ruff_cgx default (env var or "ruff")
        logger.info(f"Using default ruff command: {get_ruff_command()}")


def _severity_to_lsp(severity: str) -> DiagnosticSeverity:
    """Convert our severity string to LSP DiagnosticSeverity."""
    mapping = {
        "error": DiagnosticSeverity.Error,
        "warning": DiagnosticSeverity.Warning,
        "info": DiagnosticSeverity.Information,
        "hint": DiagnosticSeverity.Hint,
    }
    return mapping.get(severity, DiagnosticSeverity.Warning)


def validate_document(ls: CollagraphLanguageServer, uri: str):
    """
    Validate a CGX document and publish diagnostics.

    Args:
        ls: The language server instance
        uri: The document URI
    """
    try:
        # Only validate .cgx files
        if not uri.endswith(".cgx"):
            logger.debug(f"Skipping non-CGX file: {uri}")
            return

        # Get the document (pygls 2.0 uses get_text_document)
        doc = ls.workspace.get_text_document(uri)
        content = doc.source

        logger.info(f"Validating document: {uri}")

        # Run the linter
        diagnostics = lint_cgx_content(content)

        # Convert to LSP diagnostics
        lsp_diagnostics = []
        for diag in diagnostics:
            lsp_diag = LspDiagnostic(
                range=Range(
                    start=Position(line=diag.line, character=diag.column),
                    end=Position(line=diag.end_line, character=diag.end_column),
                ),
                message=diag.message,
                severity=_severity_to_lsp(diag.severity),
                code=diag.code,
                source=diag.source,
            )
            lsp_diagnostics.append(lsp_diag)

        # Publish diagnostics (pygls 2.0 uses PublishDiagnosticsParams)
        params = PublishDiagnosticsParams(uri=uri, diagnostics=lsp_diagnostics)
        ls.text_document_publish_diagnostics(params)
        logger.info(f"Published {len(lsp_diagnostics)} diagnostics for {uri}")

    except Exception as e:
        logger.error(f"Error validating document {uri}: {e}", exc_info=True)


@server.feature(INITIALIZE)
def initialize(ls: CollagraphLanguageServer, params: InitializeParams):
    """
    Handle initialization request from the client.

    Accepts configuration via initialization options:
    - ruffCommand: Path or command name for ruff executable

    Example initialization options from client:
    {
        "ruffCommand": "/opt/homebrew/bin/ruff"
    }
    """
    logger.info("Initializing Collagraph LSP server")

    # Get initialization options
    init_options = params.initialization_options or {}

    # Extract settings
    ruff_command = init_options.get("ruffCommand")

    # Store settings
    if ruff_command is not None:
        ls.settings["ruffCommand"] = ruff_command

    # Apply ruff command configuration
    _apply_ruff_command(ls.settings["ruffCommand"])

    logger.info(f"Server initialized with settings: {ls.settings}")


@server.feature(WORKSPACE_DID_CHANGE_CONFIGURATION)
def did_change_configuration(
    ls: CollagraphLanguageServer, params: DidChangeConfigurationParams
):
    """
    Handle configuration change notifications from the client.

    Expects settings in the format:
    {
        "collagraph-lsp": {
            "ruffCommand": "/opt/homebrew/bin/ruff"
        }
    }
    """
    logger.info("Configuration changed")

    # Get settings from params
    settings = params.settings

    # Extract collagraph-lsp settings
    if isinstance(settings, dict):
        # Update ruff command if provided
        if "ruffCommand" in settings:
            ls.settings["ruffCommand"] = settings["ruffCommand"]
            _apply_ruff_command(ls.settings["ruffCommand"])
            logger.info(f"Updated settings: {ls.settings}")


@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: CollagraphLanguageServer, params: DidOpenTextDocumentParams):
    """Handle document open event."""
    logger.info(f"Document opened: {params.text_document.uri}")
    validate_document(ls, params.text_document.uri)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: CollagraphLanguageServer, params: DidChangeTextDocumentParams):
    """Handle document change event."""
    logger.info(f"Document changed: {params.text_document.uri}")
    validate_document(ls, params.text_document.uri)


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: CollagraphLanguageServer, params: DidSaveTextDocumentParams):
    """Handle document save event."""
    logger.info(f"Document saved: {params.text_document.uri}")
    validate_document(ls, params.text_document.uri)


@server.feature(TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: CollagraphLanguageServer, params: DidCloseTextDocumentParams):
    """Handle document close event."""
    logger.info(f"Document closed: {params.text_document.uri}")
    # Clear diagnostics for closed document
    clear_params = PublishDiagnosticsParams(
        uri=params.text_document.uri, diagnostics=[]
    )
    ls.text_document_publish_diagnostics(clear_params)


@server.feature(TEXT_DOCUMENT_FORMATTING)
def formatting(ls: CollagraphLanguageServer, params: DocumentFormattingParams):
    """Handle document formatting request."""
    uri = params.text_document.uri
    logger.info(f"Formatting document: {uri}")

    try:
        # Only format .cgx files
        if not uri.endswith(".cgx"):
            logger.debug(f"Skipping non-CGX file: {uri}")
            return []

        # Get the document
        doc = ls.workspace.get_text_document(uri)
        content = doc.source

        # Format the content
        formatted_content = format_cgx_content(content, uri)

        # If content didn't change, return empty list
        if formatted_content == content:
            logger.info(f"No formatting changes needed for {uri}")
            return []

        # Calculate the range that needs to be replaced (entire document)
        lines = content.splitlines(keepends=True)
        last_line = len(lines) - 1
        last_char = len(lines[-1]) if lines else 0

        # Create a text edit that replaces the entire document
        text_edit = TextEdit(
            range=Range(
                start=Position(line=0, character=0),
                end=Position(line=last_line, character=last_char),
            ),
            new_text=formatted_content,
        )

        logger.info(f"Formatted document {uri}")
        return [text_edit]

    except Exception as e:
        logger.error(f"Error formatting document {uri}: {e}", exc_info=True)
        return []


@server.feature(
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    SemanticTokensLegend(
        token_types=SemanticTokensProvider().token_types,
        token_modifiers=SemanticTokensProvider().token_modifiers,
    ),
)
def semantic_tokens_full(
    ls: CollagraphLanguageServer, params: SemanticTokensParams
) -> SemanticTokens:
    """
    Handle semantic tokens request.

    Provides rich syntax highlighting based on semantic analysis of the code.
    """
    uri = params.text_document.uri
    logger.info(f"Providing semantic tokens for: {uri}")

    try:
        # Only process .cgx files
        if not uri.endswith(".cgx"):
            logger.debug(f"Skipping non-CGX file: {uri}")
            return SemanticTokens(data=[])

        # Get the document
        doc = ls.workspace.get_text_document(uri)
        content = doc.source

        # Extract semantic tokens
        tokens = ls.semantic_tokens_provider.get_tokens(content, uri)

        # Encode tokens in LSP format
        encoded_data = ls.semantic_tokens_provider.encode_tokens(tokens)

        logger.info(f"Provided {len(tokens)} semantic tokens for {uri}")
        return SemanticTokens(data=encoded_data)

    except Exception as e:
        logger.error(f"Error providing semantic tokens for {uri}: {e}", exc_info=True)
        return SemanticTokens(data=[])


@server.feature(
    TEXT_DOCUMENT_COMPLETION,
    CompletionOptions(
        trigger_characters=[".", "[", "(", '"', "'"],
        resolve_provider=False,
    ),
)
async def completions(
    ls: CollagraphLanguageServer, params: CompletionParams
) -> CompletionList:
    """
    Handle completion request.

    Phase 1: Provides Python completions in <script> sections only.
    """
    uri = params.text_document.uri
    position = params.position
    logger.info(
        f"Providing completions for: {uri} at {position.line}:{position.character}"
    )

    try:
        # Only process .cgx files
        if not uri.endswith(".cgx"):
            logger.debug(f"Skipping non-CGX file: {uri}")
            return CompletionList(is_incomplete=False, items=[])

        # Get the document
        doc = ls.workspace.get_text_document(uri)
        content = doc.source

        # Extract script region at the cursor position
        script_region = extract_script_region(content, position)

        # Phase 1: Only provide completions for <script> sections
        if script_region.in_script:
            items = await get_python_completions(script_region)
            logger.info(f"Provided {len(items)} completions for {uri}")
        else:
            items = []
            logger.debug(
                "Cursor not in script section at "
                f"{uri}:{position.line}:{position.character}"
            )

        return CompletionList(is_incomplete=False, items=items)

    except Exception as e:
        logger.error(f"Error providing completions for {uri}: {e}", exc_info=True)
        return CompletionList(is_incomplete=False, items=[])


def main():
    """Main entry point for the LSP server."""

    # Start the server using stdin/stdout
    logger.info("Starting Collagraph LSP server...")
    server.start_io()


if __name__ == "__main__":
    main()
