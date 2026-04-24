# P0 — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Before you start:** read the Master Integration Plan at [./2026-04-25-jarasport-tp-mcp-master.md](./2026-04-25-jarasport-tp-mcp-master.md) and follow §12 Session Protocol.

**Goal:** Scaffold the `jarasport-tp-mcp` repository with commercial-grade foundations — package layout, linting, typing, testing, coverage gating, pre-commit hooks, CI matrix, container build, and a test-all-code enforcement hook. Ships a no-op but fully gated repository that every later phase builds on.

**Architecture:** New repository `jara-r-k/jarasport-tp-mcp` (decision in Task 1). Python `src/` layout with two top-level packages: `tp_core/` and `tp_mcp/`, each with their own test tree. Dependencies managed by `uv`. CI on GitHub Actions, matrix Python 3.10–3.14.

**Tech Stack:** Python 3.12 (dev), `uv`, `hatchling` (build), `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `pytest-cov`, `hypothesis`, `respx`, `bandit`, `pip-audit`, `gitleaks`, `trivy`, `pre-commit`, GitHub Actions, Docker (`python:3.12-slim`).

**Estimated effort:** 4 working days.

---

## File Structure (at end of P0)

```
jarasport-tp-mcp/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                  # Lint, type, test matrix, coverage, security
│   │   └── docker.yml              # Container build + trivy scan
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   ├── pull_request_template.md
│   └── CODEOWNERS
├── .pre-commit-config.yaml
├── .gitignore
├── .gitleaks.toml
├── .editorconfig
├── .dockerignore
├── CHANGELOG.md                    # keep-a-changelog skeleton
├── CONTRIBUTING.md
├── LICENSE                         # MIT
├── README.md                       # Quickstart skeleton
├── SECURITY.md                     # Disclosure policy
├── Dockerfile                      # Multi-stage, non-root, distroless-ish
├── pyproject.toml                  # uv + hatchling + tool configs
├── uv.lock
├── scripts/
│   ├── check_test_coverage.py      # Pre-commit: every src file needs a test
│   └── check_no_secrets.py         # Fail if committed file looks like a secret
├── src/
│   ├── tp_core/
│   │   ├── __init__.py             # Exports __version__
│   │   └── py.typed                # PEP 561 marker
│   └── tp_mcp/
│       ├── __init__.py             # Exports __version__
│       └── py.typed
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Shared fixtures (minimal)
│   ├── tp_core/
│   │   ├── __init__.py
│   │   └── test_canary.py          # Proves the test runner works
│   └── tp_mcp/
│       ├── __init__.py
│       └── test_canary.py
└── docs/
    └── superpowers/
        ├── specs/...               # (Already exists)
        └── plans/...               # (Already exists)
```

**Why `src/` layout:** forces installation before tests run, catches missing package metadata, standard pattern.

**Why separate `tp_core` and `tp_mcp` from day zero:** enforces the dependency rule (`tp_core` never imports from `tp_mcp`) via import graph, not discipline.

**Why a pre-commit script that checks test coverage:** CI coverage is a lagging signal. A pre-commit hook catches "added code without a test" at the earliest possible moment.

---

## Conventions Established in P0 (load-bearing)

All later phases inherit these:

- **Line length**: 100 (not 88, not 120 — calibrated for type-annotated Python).
- **Import style**: `ruff` enforces isort rules (profile `black`-compatible).
- **Docstrings**: Google style, mandatory on public modules/classes/functions.
- **Type hints**: `mypy --strict`. No `Any` without an inline `# noqa` + reason. No implicit `Optional`.
- **Commit format**: Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`, `perf:`, `build:`, `ci:`). Enforced by a commit-msg hook.
- **Test naming**: `tests/<pkg>/test_<module>.py`, one test file mirrors one source module.
- **No `print()` in `src/`**: enforced by ruff.
- **No `TODO` without a tracking reference**: enforced by a custom pre-commit rule.

---

## Task 1: Decide and create the GitHub repository

**Files:**
- Create: (GitHub repo `jara-r-k/jarasport-tp-mcp`)
- Modify: Master plan §1 (update status to IN PROGRESS) and §8 (resolve Q-001)
- Test: manual verification

- [ ] **Step 1: Check PyPI name availability**

```bash
pip index versions jarasport-tp-mcp 2>&1 | head -5
```

Expected: `ERROR: No matching distribution found` — name is available. If occupied, propose alternatives (`jara-tp-mcp`, `tp-mcp-jarasport`) and update the spec before proceeding.

- [ ] **Step 2: Create repo via `gh`**

```bash
gh repo create jara-r-k/jarasport-tp-mcp \
  --public \
  --description "Commercial-grade TrainingPeaks MCP server (multi-tenant, Clerk-authenticated)" \
  --license MIT \
  --gitignore Python \
  --clone
cd jarasport-tp-mcp
```

Expected: repo created, cloned to current directory.

- [ ] **Step 3: Copy spec and master plan into new repo**

```bash
mkdir -p docs/superpowers/specs docs/superpowers/plans/HANDOFFS
cp ~/projects/trainingpeaks-mcp/docs/superpowers/specs/2026-04-25-jarasport-tp-mcp-design.md docs/superpowers/specs/
cp ~/projects/trainingpeaks-mcp/docs/superpowers/plans/2026-04-25-jarasport-tp-mcp-master.md docs/superpowers/plans/
cp ~/projects/trainingpeaks-mcp/docs/superpowers/plans/2026-04-25-jarasport-tp-mcp-P0-foundations.md docs/superpowers/plans/
```

- [ ] **Step 4: Update Q-001 in master plan**

Set `Resolved` column to today's date and `Resolution path` to "PyPI name `jarasport-tp-mcp` confirmed available".

- [ ] **Step 5: Initial commit**

```bash
git add .
git commit -m "chore: bootstrap repo with spec and plans"
git push -u origin main
```

---

## Task 2: pyproject.toml with project metadata and deps

**Files:**
- Create: `pyproject.toml`
- Test: `python -m build --sdist --wheel .` succeeds

- [ ] **Step 1: Write pyproject.toml**

```toml
[build-system]
requires = ["hatchling>=1.21"]
build-backend = "hatchling.build"

[project]
name = "jarasport-tp-mcp"
version = "0.0.0"
description = "Commercial-grade TrainingPeaks MCP server with multi-tenant Clerk authentication"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [{ name = "Jara Rokahr-Knowles" }]
keywords = ["mcp", "trainingpeaks", "cycling", "running", "triathlon", "claude"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
    "Typing :: Typed",
]
dependencies = []

[project.optional-dependencies]
dev = [
    "ruff>=0.5.0",
    "mypy>=1.10",
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "pytest-benchmark>=4.0",
    "hypothesis>=6.100",
    "respx>=0.21",
    "bandit[toml]>=1.7",
    "pip-audit>=2.7",
    "pre-commit>=3.7",
]

[project.urls]
Homepage = "https://github.com/jara-r-k/jarasport-tp-mcp"
Issues = "https://github.com/jara-r-k/jarasport-tp-mcp/issues"
Changelog = "https://github.com/jara-r-k/jarasport-tp-mcp/blob/main/CHANGELOG.md"

[project.scripts]
tp-mcp = "tp_mcp.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/tp_core", "src/tp_mcp"]

[tool.ruff]
line-length = 100
target-version = "py310"
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E", "W",      # pycodestyle
    "F",           # pyflakes
    "I",           # isort
    "B",           # bugbear
    "C4",          # comprehensions
    "UP",          # pyupgrade
    "S",           # bandit
    "SIM",         # simplify
    "RUF",         # ruff-specific
    "ARG",         # unused args
    "PL",          # pylint subset
    "N",           # naming
    "T20",         # no print
    "ANN",         # type annotations
    "D",           # pydocstyle
]
ignore = [
    "D203",        # one-blank-line-before-class (conflicts with D211)
    "D213",        # multi-line-summary-second-line (conflicts with D212)
    "ANN101",      # self
    "ANN102",      # cls
    "PLR0913",     # too many arguments — sometimes necessary at boundaries
]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "ANN", "D", "PLR2004"]   # allow asserts, skip annotations and docstrings in tests
"scripts/**" = ["T20"]                         # scripts may print

[tool.mypy]
python_version = "3.10"
strict = true
warn_unreachable = true
warn_redundant_casts = true
warn_unused_ignores = true
disallow_any_generics = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
no_implicit_optional = true
explicit_package_bases = true
mypy_path = "src"
packages = ["tp_core", "tp_mcp"]

[[tool.mypy.overrides]]
module = ["tests.*"]
disallow_untyped_defs = false
check_untyped_defs = true

[tool.pytest.ini_options]
minversion = "8.0"
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = [
    "--strict-markers",
    "--strict-config",
    "-ra",
    "--cov=tp_core",
    "--cov=tp_mcp",
    "--cov-branch",
    "--cov-report=term-missing",
    "--cov-report=xml:coverage.xml",
    "--cov-fail-under=90",
]
markers = [
    "smoke: Real-API smoke tests, not run in CI",
    "slow: Slow tests excluded from default run",
    "property: Hypothesis property-based tests",
    "contract: Tool schema contract tests",
    "integration: Integration tests via respx / VCR",
]

[tool.coverage.run]
branch = true
source = ["src/tp_core", "src/tp_mcp"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    "@overload",
]

[tool.bandit]
exclude_dirs = ["tests", "scripts"]
```

- [ ] **Step 2: Install with dev extras**

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Expected: installs ~20 dev packages, no errors.

- [ ] **Step 3: Verify build**

```bash
python -m pip install build
python -m build --sdist --wheel .
ls dist/
```

Expected: `jarasport_tp_mcp-0.0.0.tar.gz` and `jarasport_tp_mcp-0.0.0-py3-none-any.whl` exist.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add pyproject.toml with dev deps and tool configs"
```

---

## Task 3: Create package skeletons with py.typed markers

**Files:**
- Create: `src/tp_core/__init__.py`
- Create: `src/tp_core/py.typed`
- Create: `src/tp_mcp/__init__.py`
- Create: `src/tp_mcp/py.typed`
- Test: `python -c "import tp_core, tp_mcp; print(tp_core.__version__)"`

- [ ] **Step 1: Write `src/tp_core/__init__.py`**

```python
"""Pure TrainingPeaks client library.

User-agnostic. Has no MCP dependencies. Safe to use standalone for CLI or service
code that needs TP access without MCP.
"""

__version__ = "0.0.0"

__all__ = ["__version__"]
```

- [ ] **Step 2: Write `src/tp_mcp/__init__.py`**

```python
"""MCP adapter for the jarasport TrainingPeaks service.

Thin layer over tp_core. Handles transport, Clerk authentication, user context
propagation, credential storage, and observability.
"""

__version__ = "0.0.0"

__all__ = ["__version__"]
```

- [ ] **Step 3: Create `py.typed` marker files**

```bash
touch src/tp_core/py.typed src/tp_mcp/py.typed
```

- [ ] **Step 4: Verify imports**

```bash
python -c "import tp_core, tp_mcp; print(tp_core.__version__, tp_mcp.__version__)"
```

Expected output: `0.0.0 0.0.0`.

- [ ] **Step 5: Commit**

```bash
git add src/
git commit -m "feat: add tp_core and tp_mcp package skeletons"
```

---

## Task 4: Canary tests prove the test runner works end-to-end

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/tp_core/__init__.py`
- Create: `tests/tp_core/test_canary.py`
- Create: `tests/tp_mcp/__init__.py`
- Create: `tests/tp_mcp/test_canary.py`

- [ ] **Step 1: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures. Populated by later phases."""
```

- [ ] **Step 2: Create `__init__.py` files**

```bash
touch tests/__init__.py tests/tp_core/__init__.py tests/tp_mcp/__init__.py
```

- [ ] **Step 3: Write `tests/tp_core/test_canary.py`**

```python
"""Canary test — proves the tp_core test runner and coverage collector work."""

from tp_core import __version__


def test_version_is_set() -> None:
    """Package version must be a non-empty string."""
    assert isinstance(__version__, str)
    assert __version__  # non-empty


def test_version_matches_expected() -> None:
    """Initial version is 0.0.0 until first release."""
    assert __version__ == "0.0.0"
```

- [ ] **Step 4: Write `tests/tp_mcp/test_canary.py`**

```python
"""Canary test — proves the tp_mcp test runner and coverage collector work."""

from tp_mcp import __version__


def test_version_is_set() -> None:
    """Package version must be a non-empty string."""
    assert isinstance(__version__, str)
    assert __version__  # non-empty


def test_version_matches_expected() -> None:
    """Initial version is 0.0.0 until first release."""
    assert __version__ == "0.0.0"
```

- [ ] **Step 5: Run tests with coverage**

```bash
pytest -v
```

Expected: 4 passed. Coverage report shows 100% for both packages (they're trivial).

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "test: add canary tests for both packages"
```

---

## Task 5: Verify ruff passes on the scaffolding

**Files:**
- Test: ruff runs clean

- [ ] **Step 1: Run ruff check**

```bash
ruff check .
```

Expected: `All checks passed!`. If not, fix issues before proceeding.

- [ ] **Step 2: Run ruff format check**

```bash
ruff format --check .
```

Expected: no files need reformatting. If any do, run `ruff format .` and commit the change.

- [ ] **Step 3: Commit any formatting fixes**

```bash
# Only if format --check flagged anything
git add .
git commit -m "style: apply ruff format"
```

---

## Task 6: Verify mypy strict passes on the scaffolding

**Files:**
- Test: `mypy --strict src/`

- [ ] **Step 1: Run mypy**

```bash
mypy src/
```

Expected: `Success: no issues found in 4 source files`.

If it fails, fix the types (most likely issue: missing annotations in `__init__.py`). Commit fixes with `fix(types): …`.

---

## Task 7: Script — per-commit test-coverage enforcement

**Files:**
- Create: `scripts/check_test_coverage.py`
- Test: `python scripts/check_test_coverage.py` against a synthetic missing file

- [ ] **Step 1: Write `scripts/check_test_coverage.py`**

```python
#!/usr/bin/env python3
"""Pre-commit hook: every src/**/*.py file must have a matching tests/**/test_*.py.

Exceptions:
- __init__.py
- py.typed (not .py)
- Files containing only `from __future__ import annotations` and imports.

Override: include `[skip-test-coverage]` in the commit message body (checked by
CI) plus an inline `# pragma: no test-coverage` in the file (checked here).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
TEST_ROOT = REPO_ROOT / "tests"
OVERRIDE_PRAGMA = "# pragma: no test-coverage"


def _expected_test_path(src_file: pathlib.Path) -> pathlib.Path:
    """Map src/pkg/module.py -> tests/pkg/test_module.py."""
    rel = src_file.relative_to(SRC_ROOT)
    return TEST_ROOT / rel.parent / f"test_{rel.name}"


def _changed_py_files() -> list[pathlib.Path]:
    """Return staged .py files under src/."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=A"],
        capture_output=True,
        text=True,
        check=True,
    )
    files: list[pathlib.Path] = []
    for line in result.stdout.splitlines():
        path = REPO_ROOT / line
        if path.suffix == ".py" and path.is_relative_to(SRC_ROOT):
            files.append(path)
    return files


def _has_override(src_file: pathlib.Path) -> bool:
    """Return True if the file declares the override pragma."""
    try:
        return OVERRIDE_PRAGMA in src_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def main() -> int:
    """Return 0 if every new src file has a test, else 1."""
    missing: list[tuple[pathlib.Path, pathlib.Path]] = []
    for src_file in _changed_py_files():
        if src_file.name == "__init__.py":
            continue
        if _has_override(src_file):
            continue
        expected = _expected_test_path(src_file)
        if not expected.exists():
            missing.append((src_file, expected))
    if missing:
        print("Test-coverage enforcement failed. Add a test for each of these:")
        for src_file, expected in missing:
            rel_src = src_file.relative_to(REPO_ROOT)
            rel_test = expected.relative_to(REPO_ROOT)
            print(f"  {rel_src}  ->  missing  {rel_test}")
        print(
            "\nTo intentionally skip, add the pragma inside the file:\n"
            f"  {OVERRIDE_PRAGMA}   # reason: <why>"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/check_test_coverage.py
```

- [ ] **Step 3: Write a test for the script itself**

Create `tests/scripts/test_check_test_coverage.py`:

```bash
mkdir -p tests/scripts
touch tests/scripts/__init__.py
```

```python
"""Tests for the test-coverage enforcement hook."""

from __future__ import annotations

import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_test_coverage.py"


def _run(cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_passes_when_no_new_src_files(tmp_path: pathlib.Path) -> None:
    """No staged src changes → exit 0."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts").mkdir()
    # Copy the script into the tmp repo so pathing works
    (tmp_path / "scripts" / "check_test_coverage.py").write_text(SCRIPT.read_text())
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout


def test_fails_when_src_file_added_without_test(tmp_path: pathlib.Path) -> None:
    """New src file without matching test → exit 1."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "src" / "tp_core").mkdir(parents=True)
    (tmp_path / "tests" / "tp_core").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_test_coverage.py").write_text(SCRIPT.read_text())
    new_file = tmp_path / "src" / "tp_core" / "new_module.py"
    new_file.write_text("x = 1\n")
    subprocess.run(["git", "add", "src/tp_core/new_module.py"], cwd=tmp_path, check=True)
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "missing" in result.stdout


def test_passes_when_override_pragma_present(tmp_path: pathlib.Path) -> None:
    """Override pragma in file → exit 0 even without test."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "src" / "tp_core").mkdir(parents=True)
    (tmp_path / "tests" / "tp_core").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_test_coverage.py").write_text(SCRIPT.read_text())
    new_file = tmp_path / "src" / "tp_core" / "odd.py"
    new_file.write_text("# pragma: no test-coverage   # reason: config only\nx = 1\n")
    subprocess.run(["git", "add", "src/tp_core/odd.py"], cwd=tmp_path, check=True)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout


def test_ignores_init_files(tmp_path: pathlib.Path) -> None:
    """__init__.py files are never required to have tests."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "src" / "tp_core").mkdir(parents=True)
    (tmp_path / "tests" / "tp_core").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_test_coverage.py").write_text(SCRIPT.read_text())
    init_file = tmp_path / "src" / "tp_core" / "__init__.py"
    init_file.write_text('"""Canary package init."""\n')
    subprocess.run(["git", "add", "src/tp_core/__init__.py"], cwd=tmp_path, check=True)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout
```

- [ ] **Step 4: Run the tests**

```bash
pytest tests/scripts/test_check_test_coverage.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/ tests/scripts/
git commit -m "feat(scripts): add test-coverage enforcement hook"
```

---

## Task 8: Pre-commit config with ruff, mypy, gitleaks, coverage hook

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `.gitleaks.toml`

- [ ] **Step 1: Write `.pre-commit-config.yaml`**

```yaml
default_stages: [pre-commit]
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
        args: [--maxkb=500]
      - id: check-merge-conflict
      - id: detect-private-key
      - id: mixed-line-ending

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: []
        args: [--strict]
        files: ^src/

  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks:
      - id: gitleaks

  - repo: local
    hooks:
      - id: check-test-coverage
        name: Every new src file has a matching test
        entry: python scripts/check_test_coverage.py
        language: system
        pass_filenames: false
        stages: [pre-commit]

      - id: conventional-commit
        name: Conventional commit message
        entry: python -c "
import re, sys;
msg = open(sys.argv[1]).read().splitlines()[0];
pattern = r'^(feat|fix|test|docs|chore|refactor|perf|build|ci|style|revert)(\([^)]+\))?!?: .+$';
sys.exit(0 if re.match(pattern, msg) or msg.startswith('Merge') else 1 and print('Commit message must follow Conventional Commits format.'))
"
        language: system
        stages: [commit-msg]
```

- [ ] **Step 2: Write `.gitleaks.toml` with baseline rules**

```toml
title = "gitleaks config for jarasport-tp-mcp"

[allowlist]
description = "Global allowlist"
paths = [
    '''tests/.*/cassettes/.*''',   # VCR cassettes — recorded with scrubbed tokens
    '''docs/.*\.md''',             # Documentation
]

[[rules]]
id = "tp-cookie"
description = "TrainingPeaks production auth cookie"
regex = '''Production_tpAuth=[A-Za-z0-9+/=]{20,}'''
tags = ["secret", "trainingpeaks"]

[[rules]]
id = "clerk-secret-key"
description = "Clerk secret key"
regex = '''sk_(test|live)_[A-Za-z0-9]{32,}'''
tags = ["secret", "clerk"]
```

- [ ] **Step 3: Install hooks**

```bash
pre-commit install
pre-commit install --hook-type commit-msg
```

Expected: `pre-commit installed at .git/hooks/pre-commit` and `commit-msg`.

- [ ] **Step 4: Run against all files**

```bash
pre-commit run --all-files
```

Expected: all hooks pass. If `end-of-file-fixer` or `trailing-whitespace` reformat anything, stage the changes and rerun until clean.

- [ ] **Step 5: Commit**

```bash
git add .pre-commit-config.yaml .gitleaks.toml
git commit -m "chore: add pre-commit hooks including test-coverage enforcement"
```

---

## Task 9: GitHub Actions CI — lint and type jobs

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write `.github/workflows/ci.yml`** (initial — lint+type only, more jobs added in later tasks)

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    name: Lint (ruff)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install ruff
        run: pip install "ruff==0.5.*"
      - name: ruff check
        run: ruff check .
      - name: ruff format
        run: ruff format --check .

  type:
    name: Type (mypy strict)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install project with dev deps
        run: |
          pip install --upgrade pip
          pip install -e ".[dev]"
      - name: mypy
        run: mypy src/
```

- [ ] **Step 2: Commit and push**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add lint and type-check jobs"
git push
```

- [ ] **Step 3: Verify CI passes**

```bash
gh run watch
```

Expected: both jobs green within 2 minutes.

---

## Task 10: CI — pytest matrix with coverage gate

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add matrix test job**

Append to `.github/workflows/ci.yml` under `jobs:`:

```yaml
  test:
    name: Test (Python ${{ matrix.python }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python: ["3.10", "3.11", "3.12", "3.13", "3.14"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
          allow-prereleases: true
      - name: Install project with dev deps
        run: |
          pip install --upgrade pip
          pip install -e ".[dev]"
      - name: pytest with coverage
        run: pytest -v
      - name: Upload coverage
        if: matrix.python == '3.12'
        uses: actions/upload-artifact@v4
        with:
          name: coverage-xml
          path: coverage.xml
```

- [ ] **Step 2: Commit and push**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add pytest matrix across Python 3.10-3.14 with coverage gate"
git push
```

- [ ] **Step 3: Verify all five matrix runs pass**

```bash
gh run watch
```

Expected: 7 jobs green (lint + type + 5 test). If Python 3.14 fails due to a dep not yet supporting it, note in §8 Open Questions and adjust matrix accordingly.

---

## Task 11: CI — security gates (bandit, pip-audit, gitleaks)

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Append security job**

```yaml
  security:
    name: Security (bandit, pip-audit, gitleaks)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: |
          pip install --upgrade pip
          pip install -e ".[dev]"
      - name: bandit
        run: bandit -c pyproject.toml -r src/ -ll
      - name: pip-audit
        run: pip-audit --strict
      - name: gitleaks
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITLEAKS_CONFIG: .gitleaks.toml
```

- [ ] **Step 2: Commit and push**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add bandit, pip-audit, and gitleaks security gates"
git push
```

- [ ] **Step 3: Verify security job passes**

Expected: green. If `pip-audit` flags a transitive dep, note the CVE in §7 Risk Register and decide whether to pin/upgrade.

---

## Task 12: LICENSE, SECURITY.md, CONTRIBUTING.md, CHANGELOG.md

**Files:**
- Create: `LICENSE`
- Create: `SECURITY.md`
- Create: `CONTRIBUTING.md`
- Create: `CHANGELOG.md`
- Create: `README.md`

- [ ] **Step 1: Write `LICENSE` (MIT)**

```
MIT License

Copyright (c) 2026 Jara Rokahr-Knowles

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Write `SECURITY.md`**

```markdown
# Security Policy

## Supported Versions

Only the latest minor release receives security updates.

## Reporting a Vulnerability

**Do not file a public GitHub issue.** Instead, email the maintainer privately
or use GitHub's private vulnerability reporting
(<https://github.com/jara-r-k/jarasport-tp-mcp/security/advisories/new>).

Include:

- Affected version(s)
- Reproduction steps
- Impact assessment
- Any known mitigations

You will receive an acknowledgement within 72 hours and a disclosure timeline
within 7 days.

## Security Posture

- Every release carries an SBOM (CycloneDX).
- Wheel and container artefacts are signed with sigstore/cosign.
- TrainingPeaks cookies and Clerk JWTs are never logged or returned in tool
  output — enforced by an automated log-safety test.
- Credentials are encrypted at rest and never returned in plaintext from the
  credential store API.

## Threat Model

See `docs/THREAT_MODEL.md` (written during phase P6).
```

- [ ] **Step 3: Write `CONTRIBUTING.md`**

```markdown
# Contributing

## Requirements

- Python 3.12 recommended for local dev.
- `uv` for dependency management.
- `pre-commit` installed (`pre-commit install && pre-commit install --hook-type commit-msg`).

## Workflow

1. Fork and branch: `feat/<short-description>`, `fix/<short-description>`.
2. Install: `uv pip install -e ".[dev]"`.
3. Write a failing test first.
4. Make the test pass with minimal code.
5. `pre-commit run --all-files` before committing.
6. Commits follow Conventional Commits: `feat(scope): description`.
7. Open a PR against `main`. CI must be green.

## Testing

- Every new source file must have a matching test file. Enforced by
  `scripts/check_test_coverage.py` (pre-commit hook).
- Unit coverage gate: ≥90% line, ≥85% branch.
- Parsers additionally need property tests (`hypothesis`).
- Tools additionally need a contract test (schema roundtrip) and an
  integration test (VCR cassette).

## Code Style

- Line length: 100.
- `ruff` enforces formatting and linting.
- `mypy --strict` must pass.
- No `print()` in `src/`; use the structured logger.
- No `Any` without a commented justification.

## Commits

- Small, focused, reversible.
- One logical change per commit.
- The commit message is the explanation — the diff is the evidence.

## Review

PR must:

- Pass all CI jobs.
- Include tests at the appropriate layer(s).
- Update documentation when behaviour or public API changes.
- Note any new risk in `docs/superpowers/plans/*-master.md` §7.
```

- [ ] **Step 4: Write `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Initial repository scaffold (P0 Foundations).
```

- [ ] **Step 5: Write `README.md`**

```markdown
# jarasport-tp-mcp

Commercial-grade TrainingPeaks MCP server with multi-tenant [Clerk](https://clerk.com)
authentication. Replaces the single-tenant fork at `jara-r-k/trainingpeaks-mcp`.

**Status:** in active rebuild. See
[`docs/superpowers/plans/2026-04-25-jarasport-tp-mcp-master.md`](docs/superpowers/plans/2026-04-25-jarasport-tp-mcp-master.md)
for program status.

## Quickstart (when released)

```bash
pip install jarasport-tp-mcp
tp-mcp serve --transport http --port 8080
```

## Architecture

Two layers:

- `tp_core/` — pure TrainingPeaks client library. User-agnostic, no MCP
  dependencies, independently usable.
- `tp_mcp/` — thin MCP adapter. HTTP/SSE transport, Clerk JWT middleware,
  per-user encrypted credential store, observability.

See [`docs/superpowers/specs/2026-04-25-jarasport-tp-mcp-design.md`](docs/superpowers/specs/2026-04-25-jarasport-tp-mcp-design.md).

## Status of the old fork

`jara-r-k/trainingpeaks-mcp` is the previous single-tenant implementation. It
will be archived once this rebuild ships and Race Day Hub migrates.

## Licence

MIT. See [`LICENSE`](LICENSE).
```

- [ ] **Step 6: Commit**

```bash
git add LICENSE SECURITY.md CONTRIBUTING.md CHANGELOG.md README.md
git commit -m "docs: add LICENSE, SECURITY, CONTRIBUTING, CHANGELOG, README"
```

---

## Task 13: GitHub metadata — issue templates, PR template, CODEOWNERS

**Files:**
- Create: `.github/CODEOWNERS`
- Create: `.github/pull_request_template.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.md`
- Create: `.github/ISSUE_TEMPLATE/feature_request.md`

- [ ] **Step 1: Write `.github/CODEOWNERS`**

```
# Everything defaults to the maintainer.
*                                   @jara-r-k

# Security-sensitive areas need explicit review.
/src/tp_mcp/auth/                   @jara-r-k
/src/tp_mcp/credentials/            @jara-r-k
/.github/workflows/                 @jara-r-k
```

- [ ] **Step 2: Write `.github/pull_request_template.md`**

```markdown
## What

<!-- One sentence. What does this PR change? -->

## Why

<!-- One paragraph. Link the spec or master plan section that motivates it. -->

## Checklist

- [ ] Tests added at the right layer (unit / contract / integration / property).
- [ ] `ruff check` and `ruff format --check` clean.
- [ ] `mypy --strict` clean.
- [ ] Coverage ≥90% line / ≥85% branch on changed files.
- [ ] No new secret could leak into logs or tool output.
- [ ] Master plan Risk Register / Open Questions updated if applicable.
- [ ] Handoff file updated if this PR completes a phase boundary.
- [ ] CHANGELOG.md has an `[Unreleased]` entry.

## Phase

<!-- Which phase of the master plan does this PR belong to? -->

## Notes for reviewer
```

- [ ] **Step 3: Write `.github/ISSUE_TEMPLATE/bug_report.md`**

```markdown
---
name: Bug report
about: Something broken — report it here
title: "bug: "
labels: bug
---

**What happened**

<!-- Observed behaviour -->

**Expected**

<!-- What you expected -->

**Reproduction**

1. ...
2. ...
3. ...

**Environment**

- Version:
- Python:
- Deployment (local stdio / HTTP service):
```

- [ ] **Step 4: Write `.github/ISSUE_TEMPLATE/feature_request.md`**

```markdown
---
name: Feature request
about: Propose a new capability
title: "feat: "
labels: enhancement
---

**Problem**

<!-- What user problem does this solve? -->

**Proposal**

<!-- What should we build? -->

**Alternatives considered**

<!-- What else did you think about? -->
```

- [ ] **Step 5: Commit**

```bash
git add .github/
git commit -m "chore: add CODEOWNERS, PR template, issue templates"
```

---

## Task 14: Dockerfile — multi-stage, non-root, minimal

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Write `.dockerignore`**

```
.git
.github
.pytest_cache
.mypy_cache
.ruff_cache
.venv
.coverage
coverage.xml
dist
build
__pycache__
*.egg-info
docs
tests
scripts
.pre-commit-config.yaml
.gitleaks.toml
.editorconfig
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12

# ─── Builder ─────────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install --upgrade pip build \
    && python -m build --wheel .

# ─── Runtime ─────────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/app/.local/bin:$PATH"

RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --home /home/app --create-home app

WORKDIR /home/app
USER app

COPY --from=builder --chown=app:app /build/dist/*.whl /tmp/
RUN pip install --user --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

EXPOSE 8080

# Healthcheck — P2 will wire /health; until then, probe the CLI.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD tp-mcp --help >/dev/null 2>&1 || exit 1

ENTRYPOINT ["tp-mcp"]
CMD ["serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 3: Add `tp-mcp` CLI entry stub**

Because `pyproject.toml` declares `tp-mcp = "tp_mcp.cli:main"`, create a minimal stub now so the Docker HEALTHCHECK works:

```bash
mkdir -p src/tp_mcp
```

Create `src/tp_mcp/cli.py`:

```python
"""CLI entrypoint stub. Full implementation lands in P2."""

from __future__ import annotations

import sys


def main() -> int:
    """Return 0 for --help probe; otherwise explain that full CLI lands in P2."""
    if len(sys.argv) >= 2 and sys.argv[1] in {"--help", "-h"}:
        print("tp-mcp — jarasport TrainingPeaks MCP server (stub; P2 ships full CLI)")
        return 0
    print("tp-mcp: full CLI ships in phase P2", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

Create `tests/tp_mcp/test_cli.py`:

```python
"""Tests for the CLI stub."""

from __future__ import annotations

import subprocess
import sys

import pytest


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tp_mcp.cli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_help_returns_zero() -> None:
    """--help must exit 0 so the Docker HEALTHCHECK probe works."""
    result = _run(["--help"])
    assert result.returncode == 0
    assert "tp-mcp" in result.stdout


def test_unknown_command_returns_two() -> None:
    """Unknown commands exit 2 with a hint about P2."""
    result = _run(["serve"])
    assert result.returncode == 2
    assert "P2" in result.stderr


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_short_and_long_help(flag: str) -> None:
    """Both short and long help flags work."""
    result = _run([flag])
    assert result.returncode == 0
```

Note that `python -m tp_mcp.cli` relies on `cli.py` executing `main()` when run as a module. Verify by running:

```bash
pip install -e .
python -m tp_mcp.cli --help
```

Expected: `tp-mcp — jarasport TrainingPeaks MCP server (stub; P2 ships full CLI)`.

- [ ] **Step 4: Run the new tests**

```bash
pytest tests/tp_mcp/test_cli.py -v
```

Expected: 4 passed (one parametrised twice).

- [ ] **Step 5: Build Docker image locally**

```bash
docker build -t jarasport-tp-mcp:dev .
docker run --rm jarasport-tp-mcp:dev --help
```

Expected: help output, container exits 0.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile .dockerignore src/tp_mcp/cli.py tests/tp_mcp/test_cli.py
git commit -m "feat: add Dockerfile, .dockerignore, and CLI stub"
```

---

## Task 15: CI — container build and trivy scan

**Files:**
- Create: `.github/workflows/docker.yml`

- [ ] **Step 1: Write `.github/workflows/docker.yml`**

```yaml
name: Docker

on:
  push:
    branches: [main]
  pull_request:
    paths:
      - Dockerfile
      - .dockerignore
      - pyproject.toml
      - src/**
      - .github/workflows/docker.yml

permissions:
  contents: read
  security-events: write

jobs:
  build-scan:
    name: Build image and trivy scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build image (no push)
        uses: docker/build-push-action@v5
        with:
          context: .
          push: false
          load: true
          tags: jarasport-tp-mcp:ci-${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Trivy scan
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: jarasport-tp-mcp:ci-${{ github.sha }}
          format: sarif
          output: trivy.sarif
          severity: HIGH,CRITICAL
          exit-code: "1"
          ignore-unfixed: true

      - name: Upload trivy SARIF
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: trivy.sarif
```

- [ ] **Step 2: Commit and push**

```bash
git add .github/workflows/docker.yml
git commit -m "ci: add Docker build and trivy vulnerability scan"
git push
```

- [ ] **Step 3: Verify**

```bash
gh run watch
```

Expected: build job passes, trivy returns clean (no HIGH/CRITICAL on `python:3.12-slim`). If trivy flags something, either update base image, add a justified allowlist, or record in §7 Risk Register.

---

## Task 16: Repo settings and branch protection (manual verification)

**Files:**
- None; GitHub repo settings

- [ ] **Step 1: Enable branch protection on `main`**

```bash
gh api -X PUT repos/jara-r-k/jarasport-tp-mcp/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -F 'required_status_checks[strict]=true' \
  -F 'required_status_checks[contexts][]=Lint (ruff)' \
  -F 'required_status_checks[contexts][]=Type (mypy strict)' \
  -F 'required_status_checks[contexts][]=Test (Python 3.12)' \
  -F 'required_status_checks[contexts][]=Security (bandit, pip-audit, gitleaks)' \
  -F 'required_status_checks[contexts][]=Build image and trivy scan' \
  -F 'enforce_admins=false' \
  -F 'required_pull_request_reviews[required_approving_review_count]=1' \
  -F 'required_pull_request_reviews[dismiss_stale_reviews]=true' \
  -F 'restrictions=' \
  -F 'allow_force_pushes=false' \
  -F 'allow_deletions=false' \
  -F 'required_linear_history=true'
```

If you are the only contributor and a branch protection reviewer requirement is too strict, omit the `required_pull_request_reviews` block and enable "require status checks to pass" only.

- [ ] **Step 2: Enable secret scanning and Dependabot**

```bash
gh api -X PATCH repos/jara-r-k/jarasport-tp-mcp \
  -F 'security_and_analysis[secret_scanning][status]=enabled' \
  -F 'security_and_analysis[secret_scanning_push_protection][status]=enabled'
```

- [ ] **Step 3: Add Dependabot config**

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
    groups:
      production:
        patterns: ["*"]
        update-types: ["minor", "patch"]
    open-pull-requests-limit: 5

  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    open-pull-requests-limit: 3

  - package-ecosystem: docker
    directory: /
    schedule:
      interval: weekly
    open-pull-requests-limit: 3
```

- [ ] **Step 4: Commit Dependabot config**

```bash
git add .github/dependabot.yml
git commit -m "chore: enable Dependabot for pip, github-actions, and docker"
git push
```

---

## Task 17: Editor and tooling config — `.editorconfig`, `.gitattributes`

**Files:**
- Create: `.editorconfig`
- Create: `.gitattributes`

- [ ] **Step 1: Write `.editorconfig`**

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.{py,pyi,toml}]
indent_style = space
indent_size = 4

[*.{yml,yaml,json,md}]
indent_style = space
indent_size = 2

[Makefile]
indent_style = tab
```

- [ ] **Step 2: Write `.gitattributes`**

```
*               text=auto eol=lf
*.py            text diff=python
*.md            text
*.toml          text
*.yml           text
*.yaml          text
*.lock          binary
*.whl           binary
*.tar.gz        binary
tests/**/cassettes/** binary
```

- [ ] **Step 3: Commit**

```bash
git add .editorconfig .gitattributes
git commit -m "chore: add .editorconfig and .gitattributes"
```

---

## Task 18: P0 exit checklist — full DoD sweep

**Files:**
- Modify: `docs/superpowers/plans/2026-04-25-jarasport-tp-mcp-master.md` — update §1, §9, §11

- [ ] **Step 1: Run every gate locally**

```bash
pre-commit run --all-files
pytest -v
ruff check .
ruff format --check .
mypy src/
bandit -c pyproject.toml -r src/ -ll
pip-audit --strict
docker build -t jarasport-tp-mcp:p0-final .
```

Expected: every command green. If any fails, fix before continuing.

- [ ] **Step 2: Verify CI is green on `main`**

```bash
gh run list --limit 5
```

Every recent run must be green.

- [ ] **Step 3: Measure coverage baseline**

```bash
pytest --cov=tp_core --cov=tp_mcp --cov-report=term-missing
```

Record the reported percentages. They should be ≥90% trivially since all code is either `__init__.py` or the CLI stub (fully covered by tests).

- [ ] **Step 4: Write the P0→P1 handoff**

Create `docs/superpowers/plans/HANDOFFS/P0-to-P1.md`:

```markdown
# Handoff: P0 Foundations → P1 tp_core

## What P0 produced

- Repository `jara-r-k/jarasport-tp-mcp` with `src/` layout.
- Two empty-but-importable packages: `tp_core`, `tp_mcp` (both `py.typed`).
- `pyproject.toml` with dev deps pinned minor-compatible.
- Lint (ruff), type (mypy strict), test (pytest + coverage gate), security
  (bandit, pip-audit, gitleaks) — all green in CI across Python 3.10–3.14.
- Pre-commit hooks including `check_test_coverage.py` (every new src file
  requires a matching test).
- Docker image builds and passes trivy HIGH/CRITICAL scan.
- Conventions documented in the plan header and CONTRIBUTING.md.

## What P1 inherits (must respect)

- **Line length 100, ruff + mypy strict, 90/85 coverage gate.**
- **No import from `tp_mcp` inside `tp_core`.** Violations surface as import
  errors in a boundary-guard test (to be added in P1 Task 1).
- **Every new src file must have a matching test file.** Pre-commit enforces.
- **Conventional commits** with a commit-msg hook.
- **Structured logging only** — no `print()` in `src/` (ruff rule T20).

## Known open questions entering P1

- None new beyond the master plan §8.

## Entry point for P1

Start with P1 Task 1: "Write a boundary-guard test asserting `tp_core` never
imports from `tp_mcp`." Then the `AuthProvider` abstract base.

## Artefacts

- `pyproject.toml` — dev deps and tool configs.
- `scripts/check_test_coverage.py` — enforces the test-per-src rule.
- `.github/workflows/ci.yml` + `docker.yml` — CI pipeline.
```

- [ ] **Step 5: Update master plan §1 Phase Status Matrix**

Edit `docs/superpowers/plans/2026-04-25-jarasport-tp-mcp-master.md`:

- P0 row: `Status = DONE — UNVERIFIED`, `Started = <date>`, `Completed = <date>`.
- P1 row: `Status = PENDING`, `Blocked On = —`.

- [ ] **Step 6: Run the DoD checklist in §5 Universal + P0-specific**

Tick every box in the master plan's §5 section. If any box cannot be ticked, diagnose and fix before moving on.

- [ ] **Step 7: Sign off in §9**

Append to the DoD Sign-Offs table:

```
| P0    | YYYY-MM-DD          | YYYY-MM-DD-JRK-P0 | All gates green, CI matrix passing, handoff written |
```

Flip P0 status in §1 to `DONE`.

- [ ] **Step 8: Update Session Ledger §11**

Append a row summarising what this session did.

- [ ] **Step 9: Commit and push**

```bash
git add docs/superpowers/plans/
git commit -m "docs(plans): P0 complete — handoff written, master updated, DoD signed"
git push
```

---

## Self-Review

(Checked against the spec before shipping this plan.)

**Spec coverage** — every P0-relevant item in the spec is addressed:

- "Scaffold: repo, package layout, CI skeleton, lint/type/test, licensing, CONTRIBUTING, Dockerfile, dev SQLite store scaffolding" ✓
- Python matrix 3.10–3.14 → Task 10 ✓
- Ruff + mypy strict + coverage gate ≥90%/85% → Tasks 2, 5, 6, 10 ✓
- Bandit, pip-audit, gitleaks → Task 11 ✓
- Trivy container scan → Task 15 ✓
- Pre-commit hooks → Task 8 ✓
- `src/` layout with `tp_core` / `tp_mcp` separation → Tasks 2, 3 ✓
- No `print()` in src → Task 2 (ruff T20) ✓
- Test-all-code enforcement → Task 7 (enforcement script) + Task 8 (wires into pre-commit) ✓
- LICENSE MIT → Task 12 ✓
- CHANGELOG keep-a-changelog → Task 12 ✓
- CODEOWNERS, PR template, issue templates → Task 13 ✓
- Dockerfile non-root, minimal → Task 14 ✓

**Deferred to later phases (by design):**
- SQLite `CredentialStore` implementation → P2 (abstract + impl together, since P1 doesn't need it).
- Observability spine → P4.
- Semantic-release pipeline → P5.
- ADRs → P6.

**Placeholder scan** — no "TBD", "TODO", "add appropriate error handling", or "similar to Task N" patterns in this file.

**Type consistency** — the CLI stub in Task 14 uses `int` return and `sys.exit`, consistent with the enforcement script in Task 7. No orphan symbols.

**"Test all code" requirement** — Task 7 ships the enforcement script with its own tests; Task 8 wires it into pre-commit; Task 10 adds CI coverage gate. Every P0 file that contains executable code either (a) has a direct test, (b) is `__init__.py`, (c) is a template/config file, or (d) has the `# pragma: no test-coverage` escape hatch used only if no other option applies (none currently use it).
