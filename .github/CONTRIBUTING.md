# Contributing to Lifeguard

Thank you for your interest in contributing to Lifeguard! This document provides guidelines for contributing.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Set up the development environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   pip install -e .
   ```
4. Create a branch for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Guidelines

### Code Style

- Follow PEP 8 guidelines
- Use type hints for function parameters and return values
- Use `from __future__ import annotations` at the top of files
- Run `ruff check` and `ruff format` before committing

### Project Structure

```
src/lifeguard/
├── cogs/           # Core Discord cogs
├── db/             # Database models and repositories
└── modules/        # Feature modules (albion, content_review, etc.)
    └── <module>/
        ├── __init__.py
        ├── cog.py      # Discord commands
        ├── models.py   # Data models
        └── repo.py     # Firestore persistence
```

### Adding a New Module

1. Create a new folder under `src/lifeguard/modules/`
2. Follow the existing pattern with `cog.py`, `models.py`, `repo.py`
3. Export public symbols in `__init__.py`
4. Register the cog in `bot.py`

## Pull Request Process

1. Ensure your code passes linting (`ruff check src/`)
2. Update documentation if needed
3. Submit a pull request with a clear description
4. Link any related issues

## Reporting Issues

- Use the issue templates when creating new issues
- Provide as much detail as possible
- Include logs and reproduction steps for bugs

## Questions?

Feel free to open a discussion or issue if you have questions about contributing.
