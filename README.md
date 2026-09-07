# QuietView

Version: **v1**

A lightweight Chrome extension for **attention and display privacy**. It masks selected browser signals so webpage scripts see a visible, focused page and one virtual monitor.

## What it does

- Reports the page as visible and focused.
- Masks visibility history and main-window idle/lock readouts.
- Reports one display and normalizes screen coordinates.
- Keeps ordinary form input and native fullscreen controls working by default.

No analytics, remote code, browsing-history collection, or data uploads.

## Install

Requires desktop Chrome or Chromium 119+. Use an up-to-date browser.

1. Download this repository using **Code → Download ZIP** and extract it.
2. Open `chrome://extensions` and enable **Developer mode**.
3. Click **Load unpacked** and select the `extension` folder.
4. Reload your webpages. After an update, reload the extension and webpages again.

Use Chrome’s extension controls to pause it or restrict site access. This is an unpacked extension; updates are manual.

## Limits

**Best-effort masking, not an invisibility guarantee.** Service workers, timing, and newly created frames can still reveal state. It does not simulate human activity, hide your IP, block trackers, or change screen-sharing output. Some sites may behave differently.

See [behavior and limitations](docs/DETAILS.md) and the [privacy policy](PRIVACY.md).

## Development

Plain JavaScript, Manifest V3, no build step. [Testing instructions](docs/TESTING.md) · [Research notes](RESEARCH.md)

[MIT License](LICENSE)
