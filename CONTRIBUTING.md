# Contributing to kuake-pipe

Thanks for thinking about contributing. This project is a small focused tool, so
the bar for changes is "is it specific, tested, and within scope."

---

## Most useful contributions

### 1. Selector fixes (highest-leverage)

When AutoDL or Quark update their web UI, kuake's scrapers stop working.
**This is the most common kind of breakage and the easiest to fix.**

All scrapers consult `src/kuake/browser/selectors.py`, which lists 2-4 fallback
strategies for each DOM target. If kuake fails at:

- `kuake init` with `SCRAPER_FAILED`
- `kuake start`/`stop` cannot find power buttons
- `kuake refresh` cannot find AutoPanel API requests

the fix is usually adding a new strategy to the relevant `SelectorSet`:

```python
AUTODL_INSTANCE_ROW = SelectorSet(
    "autodl_instance_row",
    (
        "[class*='instance-item']",
        "[class*='InstanceItem']",
        "tr[data-instance-id]",
        "[data-testid='instance-row']",
        # ↓ Add new strategy here when the existing ones stop matching
        "[class*='your-new-class']",
    ),
)
```

Open an issue with the **broken selector name** + **a screenshot of current
page DOM** (F12 → Elements → right-click → Copy → outerHTML), and we can
work out the new strategy together.

### 2. Bug reports

Use the bug-report issue template. Always include:

- Output of `kuake doctor`
- The full traceback with `KUAKE_DEBUG=1 kuake <cmd>`
- OS / Python version

### 3. Feature requests

Open an issue first to discuss scope. The project explicitly stays away from:

- Linux support (Quark has no Linux client)
- Direct Quark Web API uploads (out of scope — backup-folder is the model)
- Multi-account / multi-profile (v1.5 roadmap)
- AutoDL billing / account management

---

## Development setup

```bash
git clone https://github.com/PYgdMIE/kuake-pipe
cd kuake-pipe
python -m venv .venv
source .venv/bin/activate    # or .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -v
```

You should see 74+ tests passing.

### Running with a clean config

Set `KUAKE_HOME` to a temp directory:

```bash
KUAKE_HOME=/tmp/kuake-test kuake init
```

This avoids touching your real `~/.kuake/`.

### Building the wheel

```bash
python -m build --wheel
# → dist/kuake_pipe-<version>-py3-none-any.whl
```

---

## Code style

- Python 3.9+ syntax (no `match` statements, no `|` type unions in annotations
  except via `from __future__ import annotations`)
- Type annotations on all function signatures
- Black-formatted (line length 100)
- Errors raise English; display layer (`i18n.py`) translates to Chinese
- One responsibility per module; if a file exceeds ~300 lines, split it

---

## Testing

```bash
pytest -v                      # all tests
pytest tests/test_pack.py      # one file
pytest --cov=src/kuake         # with coverage
```

### What to test

| Layer | Test | Tooling |
|---|---|---|
| Foundation (errors, config, lock, pack) | Unit | pytest + tmp_path |
| Protocol (panel_api expiry, retry) | Mock HTTP | requests-mock |
| Browser scrapers | Selector table sanity only | pytest |
| CLI parser | argparse smoke | pytest + pytest.raises(SystemExit) |
| Real DOM scrape | `docs/MANUAL_TEST.md` | Human |

Coverage gate: foundation modules ≥ 80%.

---

## Commit messages

Conventional commits:

```
<type>: <description>

<optional body>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `perf`, `ci`

Examples:
- `feat: add kuake stop --force option`
- `fix(scraper): add fallback selector for new AutoDL UI`
- `docs: clarify Quark client setup steps`

---

## Pull request checklist

- [ ] `pytest` passes
- [ ] No new dependencies unless justified in PR description
- [ ] If changing a scraper, also update `tests/fixtures/` with a current
      DOM snapshot
- [ ] If changing CLI surface, update `README.md` and `docs/MANUAL_TEST.md`
- [ ] `CHANGELOG.md` entry under `[Unreleased]`

---

## License

By contributing, you agree your contributions are licensed under MIT.
