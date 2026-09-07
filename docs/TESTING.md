# Testing

The extension has no build dependencies. Tests require Python 3.10+, Playwright, and Chromium/Chrome for Testing.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
export CHROMIUM_PATH="$(python -c 'from playwright.sync_api import sync_playwright; p = sync_playwright().start(); print(p.chromium.executable_path); p.stop()')"

python tests/test_core.py
python tests/test_timeline_fixtures.py
python tests/test_attention_regressions.py
python tests/test_browser.py --headless
```

On Windows, use `.venv\Scripts\Activate.ps1` and set `$env:CHROMIUM_PATH` to your Chromium executable. On headless Linux, run the core suite with `xvfb-run -a` and install browser system dependencies with `python -m playwright install --with-deps chromium`.

For desktop visibility checks, also run `python tests/test_browser.py` without `--headless`. Use Chrome for Testing: regular Chrome may reject command-line extension loading. `--baseline` runs the integration assertions without the extension and is expected to fail protection checks.

## Latest verification

Version v1, Chrome for Testing 151.0.7922.34 on macOS:

| Suite | Result |
| --- | --- |
| Core DOM checks | 34 passed |
| Timeline fixtures | 9 passed |
| Attention regressions | 19 passed |
| Installed extension | 59 passed, 2 skipped |

The unpatched integration baseline failed 25 protection assertions. Native focus loss and blur masking were verified. Native hidden-state transitions could not be reliably produced, so those checks were skipped; hidden-state coverage uses labeled fixtures. Physical multiple-monitor hardware was not tested.

Related-frame tests also found an immediate-access race before final-document injection. Passing tests do not establish protection against every detection method. Test runs write local output files, which are excluded from Git.
