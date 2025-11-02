# Collagraph LSP Server

A Language Server Protocol (LSP) implementation for [Collagraph](https://github.com/fork-tongue/collagraph) `.cgx` files with integrated [ruff](https://github.com/astral-sh/ruff) linting.

Collagraph is a Python port of Vue.js, supporting single-file components in `.cgx` files. This LSP server provides real-time linting and formatting for Python code within these files.

## Features

- **Linting with ruff**: Uses ruff to lint the Python code within the script tag
- **Formatting with ruff**: Uses ruff to format the python code within the script tag and template expressions
- **Python autocompletion**: Provides intelligent code completion for Python code in `<script>` sections using Jedi with full component context


## Installation

Install from PyPi:

```bash
uv tool install collagraph-lsp
# or with pip
pip install collagraph-lsp
```

### Install from source

```bash
# Clone the repository
git clone https://github.com/fork-tongue/collagraph-lsp.git
cd collagraph-lsp
uv tool install .
```

## Usage

### Running the Server

The LSP server communicates over stdin/stdout. To start it:

```bash
# Using uv
uv run collagraph-lsp

# Or run directly
uv run python -m collagraph_lsp.server
```

### Configuration

The server works with default Ruff settings, although it should pick up on your configuration in your project root.

## Editor Integration

Coming soon:

* Sublime Text
* VS Code
* Zed

## Development

### Running Tests

```bash
# Install (development) dependencies
uv sync

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=collagraph_lsp

# Lint and format
uv run ruff check --fix
uv run ruff format
```

## Related Projects

- [collagraph](https://github.com/fork-tongue/collagraph) - Python port of Vue.js
- [ruff-cgx](https://github.com/fork-tongue/ruff-cgx) - Linter and formatter for cgx files
