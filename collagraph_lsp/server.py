"""Main LSP server implementation for Collagraph files."""

import logging
from importlib.metadata import version

from lsprotocol.types import (
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_FORMATTING,
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    DocumentFormattingParams,
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
from ruff_cgx import format_cgx_content, lint_cgx_content

from .semantic_tokens import SemanticTokensProvider

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CollagraphLanguageServer(LanguageServer):
    """Language server for Collagraph .cgx files."""

    def init(self):
        self.semantic_tokens_provider = SemanticTokensProvider()


# Create the server instance
server = CollagraphLanguageServer("collagraph-lsp", f"v{version('collagraph_lsp')}")


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


def main():
    """Main entry point for the LSP server."""

    # Start the server using stdin/stdout
    logger.info("Starting Collagraph LSP server...")
    server.start_io()


if __name__ == "__main__":
    main()
