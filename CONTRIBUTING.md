# Contributing

Thanks for taking a look. Small, focused improvements are easiest to review.

## Development setup

1. Use Python 3.11 or later.
2. Create and activate a virtual environment.
3. Install `requirements-dev.txt`.
4. Run `ruff check app tests` and `python -m unittest discover -v` before opening a pull request.

The app has no required API key. Tests use local fixtures and mock the optional OpenAI call, so they should not make network requests.

## Pull requests

- Explain the user problem and the behavior changed.
- Include or update a test for new non-trivial behavior.
- Keep sample documents fictional and never commit keys, private documents, or generated local data.
- Update the README when setup, limitations, or user-visible behavior changes.

## Scope

The current app is local and single-user. Changes that expose it to a network need a clear authentication, authorization, storage-isolation, and abuse-prevention design.
