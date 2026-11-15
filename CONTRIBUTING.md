# Contributing to Pomodoro

Thanks for your interest in improving Pomodoro! Bug reports, ideas and pull requests are all welcome.

## Reporting bugs and suggesting features

Open an [issue](https://github.com/Aftar-Ahmad-Sami/Pomodoro/issues/new/choose) and pick **Bug report** or **Feature request**. For a bug, the version, Windows version and steps to reproduce make it much faster to fix.

Found a security problem? Please don't open a public issue; see [SECURITY.md](SECURITY.md).

## Setting up

You need Windows 10 or 11 and Python 3.10+.

```powershell
git clone https://github.com/Aftar-Ahmad-Sami/Pomodoro.git
cd Pomodoro
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m pomodoro
```

A conda environment works too: activate it and run `pip install -e ".[dev]"`.

The [project layout](README.md#project-layout) in the README explains what each module does.

## Making a change

1. For anything bigger than a small fix, open an issue first to agree on the approach.
2. Create a branch from `main`.
3. Keep timer logic in `timer.py` and `bank.py`, which don't depend on the window, and add tests for it in `tests/`. The timer takes its clock as a parameter, so tests use a fake clock instead of waiting.
4. Run all the checks; CI runs the same ones and a pull request must pass them:

   ```powershell
   pytest
   ruff check .
   ruff format .
   mypy
   ```

5. Update the README if you change behavior, keyboard shortcuts or setup steps.
6. Open a pull request and fill in the template. For UI changes, a screenshot helps.

## Style

- Formatting and linting are handled by Ruff (line length 120); type hints are checked by mypy in strict mode.
- Write comments that explain *why*, not *what*.
- Keep user-facing text short and plain, matching the existing wording in the app.
- Never commit secrets. Slack settings belong in `%LOCALAPPDATA%\Pomodoro\slack.json`, outside the repo, and tests use fake tokens.

## Releasing (maintainers)

1. Update the version in both `pyproject.toml` and `src/pomodoro/__init__.py`.
2. Commit, then tag and push:

   ```powershell
   git tag v1.1.0
   git push origin v1.1.0
   ```

The [Release workflow](.github/workflows/release.yml) checks that the tag matches both versions, runs the tests, builds `PomodoroSetup.exe` and `Pomodoro.exe`, and publishes them as a GitHub Release with generated notes.

## Code of conduct

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

By contributing, you agree that your contributions are licensed under the project's [Apache License 2.0](LICENSE).
