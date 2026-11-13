# Behavior and limitations

Commands below run from the project root.

## Local diagnostic

In the extension's **Details**, enable **Allow access to file URLs**, then open `extension/diagnostic.html` from the extracted folder in Chrome. Reload it after changing permissions. The diagnostic does not inject the extension itself, so it can help check whether your actual installation is taking effect. You can turn file access off afterwards.

An alternative is to serve the extension directory locally:

```bash
python3 -m http.server 8000 --bind 127.0.0.1 --directory extension
```

Then open `http://127.0.0.1:8000/diagnostic.html`. The diagnostic has no remote dependencies or upload behavior. Its screen-details button may prompt for real permission if the extension is not running; do not grant access just to make the test pass.

Switch to another tab or window, minimize Chrome, resize it, then return. Inspect the readouts, event history and remaining native signals. A passing diagnostic is **not** proof of resistance to an adversarial site.

## What is substituted

| Surface | Page-visible result in a covered execution context |
|---|---|
| `document.hidden` / supported legacy alias | `false` |
| `document.visibilityState` / supported legacy alias | `"visible"` |
| `document.hasFocus()` | `true` |
| Document visibility and window/document focus/blur events | Suppressed; ordinary input element focus/blur stays functional |
| Fullscreen elements, booleans, events, and display-mode queries | Native by default; optional spoofing available in CONFIG |
| `screen.isExtended` | `false`, where the API exists |
| `getScreenDetails()` | Promise for one stable, synthetic screen/details object; no real monitor enumeration |
| Screen size | Initial current-screen snapshot; does **not** anonymize monitor resolution |
| Screen origin and mouse/touch screen coordinates | Origin zero; event screen coordinates follow client coordinates |
| Main-window `IdleDetector.userState` / `.screenState` | `"active"` / `"unlocked"`; changes suppressed; actual permission checks unchanged |
| Normal visibility performance entry queries / buffered observers | One synthetic initial `visible` entry at time zero; later visibility transitions suppressed |
| Unbuffered visibility observers | No callbacks or queued records for native visibility transitions |

No fake zero-monitor result: one screen is the coherent basic shape for a visible browser window. A fullscreen element is a DOM element, not the Boolean `true`. Returning `true` for every API would be incorrect.

The source uses static, `document_start`, `MAIN`-world content scripts with eligible-frame matching. It does not rely on injecting a DOM `<script>` element. See https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts and https://developer.chrome.com/docs/extensions/reference/manifest/content-scripts.

## Pause, restrict sites or customize

Use Chrome's extension controls to disable the extension or change its **Site access**, then reload affected pages. Disabling an extension does not reliably undo JavaScript changes already made to a loaded page.

For individual feature switches, edit the `CONFIG` object at the top of `extension/shield.js`. Set unwanted features to `false`, click **Reload** on the extension at `chrome://extensions`, then reload webpages. `fullscreenReadouts` and `displayModeReadouts` are disabled by default so native fullscreen controls work. Enable them only if you explicitly want their readout substitutions and accept compatibility risks. Use site restrictions for important applications rather than accepting unexplained behavior.

## Important limits and possible breakage

**Optional fullscreen spoofing is not actual fullscreen.** Native `:fullscreen`, CSS `@media (display-mode: fullscreen)`, compound media queries, `ShadowRoot.fullscreenElement`, `fullscreenEnabled`, outer/inner dimensions and resize events remain native. The reported fullscreen element can disagree with these. During initial document construction, no document element exists yet, so the getter can temporarily return `null`.

**Not a native screen object.** The synthetic `ScreenDetailed`-shaped object has event-listener methods and stable identity, but lacks native internal slots. Passing it to `requestFullscreen({screen: ...})` can fail. Native permission queries can disagree with successful synthetic `getScreenDetails()` results. The native permission is neither requested nor granted. Screen orientation and device pixel ratio are not fully normalized, and frames on different origins may retain differing snapshots. Real screen-sharing pixels and metadata are untouched.

**Workers and fresh realms.** Service-worker `WindowClient.visibilityState`, `.focused` and client ordering are unpatched. Dedicated workers have a separate Idle Detection API. A page can inspect new frames before injection, use native methods from another realm, compare descriptors, or simply replace these patches. Standard eligible-frame injection is not a proof against all such races. Other extensions run in separate contexts.

**Timing and real interactions.** Chrome may throttle, freeze or discard a background page. This code does not alter timers, `requestAnimationFrame`, `Date`, event timing, user-activation state or `Event.isTrusted`. It does not generate mouse, keyboard or scroll activity. Focus-related CSS, pointer departure, wake-lock release, pointer-lock loss and many lifecycle signals remain observable. Lack of activity is not proof of tab switching, but a site can use it as a signal.

**Navigation.** Moving to another tab leaves the original page available for these substitutions. Navigating the same tab to another URL, closing it, suspending the computer or losing network connectivity does not keep the old page alive or make its server believe it remains active. `beforeunload`, `pagehide`, `freeze`, `resume` and normal save-state behavior are deliberately not suppressed. Some sites save on `visibilitychange`; suppressing that event can still affect autosave or session handling.

**Not an ad blocker or anonymity tool.** Cookies, account IDs, IP addresses, network headers, tracking requests, canvas/audio/GPU/font fingerprints and hardware identifiers are not covered. A distinctive combination of spoofed values can contribute to fingerprinting. Pairing more spoofing extensions is not automatically stronger privacy and can introduce conflicts.

**Performance and compatibility.** Sites that normally pause when hidden may keep working longer because they see `visible`. The browser can still throttle them. Modified event semantics can affect analytics, autosave, media, drawing tools and applications with screen-placement functionality. Use a separate browser profile for initial evaluation.
