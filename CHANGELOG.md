# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Application versions follow [Semantic Versioning](https://semver.org/).

## Unreleased

### Added

- Add a Protection switch to pause or resume QuietView across eligible sites. The setting is saved locally and applies to pages after reload.
- Run JavaScript syntax checks, core and fixture suites, and the loaded-extension browser suite in GitHub Actions using Playwright’s pinned Chromium.
- Verify that the installed extension reapplies on page reload and gate native hidden-timeline claims on a demonstrated transition and observer delivery.

### Changed

- Simplify the popup to the switch and a short list of masked browser signals.
- Document unpacked installation, the privacy scope, and separate fixture, installed-browser, and hardware verification.

## v1.0.0 baseline (tag `v1`)

The [annotated `v1` tag](https://github.com/ant0n-grachev/QuietView/tree/v1) records the source baseline for manifest version `1.0.0`. The tag is dated 2026-09-07.

### Added

- Unpacked Manifest V3 extension with selected page visibility, focus, idle, and display substitutions, plus a local diagnostic page. Native fullscreen controls stay enabled by default.
