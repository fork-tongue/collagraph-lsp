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
pip install uv
```

### Install from source

```bash
# Clone the repository
git clone https://github.com/fork-tongue/collagraph-lsp.git
cd collagraph-lsp

# Install with uv
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

The server works with default Ruff settings. It should pick up on your configuration in your project root:

```toml
# pyproject.toml
[tool.ruff]
line-length = 120
select = ["E", "F", "W"]
ignore = ["E501"]
```

## Editor Integration

### Sublime Text

1. Install [LSP](https://packagecontrol.io/packages/LSP) package via Package Control

2. Manually configure LSP by adding to your settings:

```json
{
  "clients": {
    "collagraph-lsp": {
      "enabled": true,
      "command": ["collagraph-lsp"],
      "selector": "source.collagraph | text.html.collagraph",
      "schemes": ["file"],
      "languageId": "collagraph"
    }
  }
}
```

### VS Code

Coming soon!

### Zed

Coming soon!


## Example CGX File

```html
<widget>
  <label :text="message"></label>
  <button @clicked="on_click">Click Me</button>
</widget>

<script>
import collagraph as cg
# This line has an unused import
from PySide6.QtWidgets import QBoxLayout

class TestComponent(cg.Component):
    def init(self):
        self.message = "Hello from Collagraph LSP!"

    def on_click(self):
        print(self.message)
        # This line has an error - undefined variable
        undefined_variable = "test"
</script>

```

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


## How It Works

1. **Parsing**: When a `.cgx` file is opened or modified, the Collagraph parser extracts the `<script>` section with its exact line range

2. **Virtual File Creation**: Creates a virtual Python file where:
   - Script section lines are preserved as-is
   - Non-script lines (template, style) are replaced with `#` comments
   - This preserves line numbers for accurate error reporting

3. **Template Compilation**: Uses Collagraph's `construct_ast` to compile the template into a `render()` method:
   - The render method references all variables used in the template
   - This allows Ruff to see that template variables are actually used
   - For example, if `QBoxLayout` is imported and used in a template attribute, Ruff won't report it as unused

4. **Virtual Subclass**: Appends a virtual subclass with the render method to the file:
   ```python
   class VirtualDirectives(Directives):
       def render(self):  # noqa
           # ... generated code that uses template variables ...
   ```

5. **Linting**: Runs Ruff on the complete virtual Python file (with `--ignore=RUF100` to skip unused noqa warnings)

6. **Mapping**: Diagnostics are correctly positioned since line numbers are preserved

7. **Publishing**: Sends diagnostics to the editor via LSP protocol


## License

MIT License

## Related Projects

- [Collagraph](https://github.com/fork-tongue/collagraph) - Python port of Vue.js
- [Ruff](https://github.com/astral-sh/ruff) - Fast Python linter
- [pygls](https://github.com/openlawlibrary/pygls) Library for LSP implementation
