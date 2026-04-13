# Contributing to synpareia-trust-mcp

Thanks for your interest in contributing to the Synpareia Trust Toolkit. This is an MCP server providing trust tools for AI agents, built on the synpareia protocol. We welcome contributions that improve it.

## Getting Started

1. Fork the repository and clone your fork
2. Install dependencies: `uv sync --extra dev`
3. Run the test suite to confirm everything works: `make test`

## Development Workflow

1. Create a branch from `main` for your change
2. Make your changes
3. Format, lint, and type-check:
   ```bash
   make format     # ruff format
   make lint       # ruff check
   make typecheck  # mypy
   ```
4. Run tests: `make test`
5. Push your branch and open a pull request

## Code Style

- **Formatting and linting:** ruff (configured in `pyproject.toml`)
- **Type checking:** mypy with strict mode
- **Imports:** sorted by ruff's isort rules

## Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation only
- `test:` adding or updating tests
- `refactor:` code change that neither fixes a bug nor adds a feature

## Pull Requests

- All CI checks must pass before merge
- Keep PRs focused on a single change
- New features need tests
- Bug fixes need a regression test
- Update documentation if your change affects MCP tool interfaces

## Tests

Tests live in `tests/`. Run them with:

```bash
make test                # full suite
uv run pytest tests/ -v  # verbose output
```

## Questions?

Open a [discussion](https://github.com/synpareia/trust-mcp/discussions) or file an issue. We're happy to help.
