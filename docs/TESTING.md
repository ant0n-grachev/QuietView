# Testing

The extension has no build dependencies. Tests require Node.js for syntax checks, Python 3.10 or later, and the pinned Playwright version in [`requirements-dev.txt`](../requirements-dev.txt).

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
export CHROMIUM_PATH="$(python -c 'from playwright.sync_api import sync_playwright; p = sync_playwright().start(); print(p.chromium.executable_path); p.stop()')"

for script in extension/*.js; do node --check "$script"; done
python tests/check_version.py
python tests/test_core.py
python tests/test_timeline_fixtures.py
python tests/test_attention_regressions.py
python tests/test_browser.py --headless
```

On Windows, use `.venv\Scripts\Activate.ps1`, set `$env:CHROMIUM_PATH` to the Playwright Chromium executable, and run `Get-ChildItem extension\*.js | ForEach-Object { node --check $_.FullName }` for the JavaScript check. On headless Linux, use `python -m playwright install --with-deps chromium` and run the core suite with `xvfb-run -a`. CI uses these Linux commands with a read-only workflow.

The core and fixture suites inject the script into Chromium DOM contexts. The integration suite loads the unpacked extension into a disposable profile and checks its page-start behavior, page reload, and popup. For desktop visibility checks, also run `python tests/test_browser.py` without `--headless`. Use the Playwright browser for automated installation. `python tests/test_browser.py --headless --baseline` repeats the protection assertions without the extension and is expected to fail them.

## Latest verification

Source version **v1.0.0**, November 12, 2026. Chrome for Testing 147.0.7727.15, Playwright 1.59.0, macOS 27.0.1 (Apple silicon).

| Suite | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| Core DOM checks | 34 | 0 | 0 |
| Timeline fixtures | 9 | 0 | 0 |
| Attention regressions | 19 | 0 | 0 |
| Installed extension, headless | 61 | 0 | 2 |
| Unpatched headless control, expected failures | 37 | 23 | 2 |

The unpatched control produced trusted blur and lost focus. With the extension loaded, the suite observed a focused readout and suppressed blur. The control did not produce a native hidden transition, so native visibility and timeline assertions were skipped. Synthetic fixtures cover hidden records separately. The browser suite also checks native fullscreen entry and exit, ordinary form focus, regular performance marks, and permission behavior.

## Manual checks

The [local diagnostic](DETAILS.md#local-diagnostic) supports checks such as switching windows, minimizing Chrome, and moving it across displays. Physical multi-monitor checks remain unverified. Related-frame tests record an immediate-access race before final-document injection. See [behavior and limitations](DETAILS.md#important-limits-and-possible-breakage) for worker and service-worker behavior, timing, screen sharing, and compatibility. Test runs write local output files that Git ignores.
