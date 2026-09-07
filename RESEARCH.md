# Attention and display privacy in Chromium

Research date: **September 7, 2026**. Implementation updated to **v1** after the attention-masking review. Scope: information an ordinary website can obtain about page attention, window state and connected displays, plus related fingerprinting surfaces. This is a prioritized inventory, not a claim to enumerate every possible side channel. It distinguishes web-platform behavior from the implementation choices in the accompanying prototype.

## Main finding

A coherent goal is **visible + focused + one display**, with tightly scoped handling of fullscreen and idle readouts. Returning `true` for everything is not coherent: `hidden` and `isExtended` must be false; `visibilityState` is a string; `fullscreenElement` is an element; screen enumeration is an object containing a one-element array. Those types and their relationships matter. [1][2][3]

More importantly, a webpage's `document` is not the only place attention state appears. The HTML performance timeline records visibility changes, and a service worker can obtain its window clients' visibility and focus through a separate execution environment. Replacing one getter does not replace these other channels. [1][4]

The supplied extension covers selected direct page-world readouts and normal visibility-timeline delivery. **It is not a browser-engine privacy boundary, an anonymity tool, or a reliable way to make every website believe the user is attentive.** Chrome explicitly warns that MAIN-world content scripts share an execution environment with the page and can be interfered with. [5]

## High-priority surfaces for this particular goal

Priority here refers to relevance to attention/display disclosure, not a formal security-severity score.

| Surface | What it exposes | Suitable treatment | Prototype status |
|---|---|---|---|
| `document.hidden`, `visibilityState`, `visibilitychange` | Native document visibility and changes | Coherent visible/false readouts and suppress corresponding transitions | Implemented for the injected page realm and supported legacy aliases |
| `document.hasFocus()`, window/document `focus` and `blur` | Whether focus is routed to the document | Report focused; distinguish window focus from input-element focus | Implemented; normal form focus and blur kept |
| `VisibilityStateEntry`, performance queries and observers | Initial visibility and timestamped transitions | One initial visible record; no later hidden/visible records or visibility-only callback timing | Implemented for normal entry queries, observer callbacks and `takeRecords`; not a native internal-state replacement |
| `screen.isExtended` | Whether the desktop extends across more than one screen | Report false | Implemented where the property exists |
| `getScreenDetails()`, `screenschange`, `currentscreenchange` | Screen count, geometry, labels and changes | One stable synthetic display with no real monitor-change notifications | Implemented with API-shaped data; not a genuine native `ScreenDetailed` |
| Screen origin, `screenX/Y`, pointer/touch screen coordinates | Coordinates that can expose a virtual-desktop layout | Normalize origin and related coordinate reads together | Implemented for common JavaScript reads; not the browser's internal coordinates |
| `fullscreenElement`, fullscreen booleans/events | DOM element fullscreen state | Return an element and suppress direct transitions only when willing to accept compatibility risks | Optional **readout-only** substitution; disabled by default in v1 |
| JavaScript `matchMedia('(display-mode: fullscreen)')` | Browser display-mode state, distinct from element fullscreen | Treat consistently with the requested display-mode profile | Optional simple-query substitution, disabled by default; compound queries and native CSS remain native |
| `IdleDetector.userState`, `.screenState`, `change` | User idle/active and screen lock state | Prefer denying unnecessary real access; optional page-world readout masking | Readouts masked in Window; native permissions intact; worker version unpatched |

The APIs and separate concepts above are documented in the HTML, Fullscreen, Window Management, CSS Media Queries, and Idle Detection specifications. [1][2][3][6][7] The coordinate substitution and choice to keep form events working are implementation decisions, not guarantees supplied by those specifications.

### Permissions are not all the same

The Window Management specification exposes `screen.isExtended` in secure contexts without a permission prompt. Detailed enumeration is permission-controlled. A document's **Permissions Policy** can disable the feature and make `isExtended` false, but that is not the same as merely rejecting a site's permission prompt. It is incorrect to assume those two controls always have identical effects. [3]

The prototype returns synthetic details without requesting access to real monitor data. It does **not** change the actual permission grant. A site can compare the result with a native permission query or try passing the fake object to a native screen-placement API and discover the inconsistency. This is an explicit limitation, not an invisible polyfill.

Idle Detection has both Window and DedicatedWorker exposure. A Window-only patch cannot cover both. Keeping real idle-detection permission denied avoids giving a separate worker that access in the first place. [7]

## Additional attention signals that should not be advertised as solved

### Service-worker visibility and focus — major gap

A site's service worker can use client APIs to obtain `WindowClient.visibilityState` and `.focused`. Client enumeration also has focus-related ordering. These are not aliases of a page's monkey-patched `document` properties. The current extension does not replace service-worker scripts or their client objects. [4]

A production design must explicitly address this separate environment rather than claim that a content script covers the entire origin. Blanket disabling service workers is a compatibility choice, not an implemented feature of this prototype.

### Background scheduling and lifecycle

Chrome can throttle timers, suspend animation frames, freeze pages or discard them. Page lifecycle events and `document.wasDiscarded` expose some of that behavior; an application can also observe gaps in its normal operation. A site or server may notice missed requests even when a getter says `visible`. Such gaps are evidence of inactivity or interruption, not conclusive proof of a tab switch. [8][9]

The prototype deliberately does not replace clocks or attempt to keep a discarded page alive. Rewriting every timer would have major performance and correctness implications and still would not control an external server's clock. It leaves `pagehide`, `beforeunload`, `freeze`, `resume`, navigation timing and normal state-save paths alone.

### Native CSS, layout and fullscreen

Element fullscreen (`:fullscreen`) and a browser's display mode are separate concepts. A browser can be fullscreen without a DOM element being fullscreen. CSS media queries, element selectors and layout are evaluated by the browser, not by a JavaScript getter on `document`. [2][6]

Changing `fullscreenElement` or a simple `matchMedia()` result therefore leaves several comparison paths: CSS computed styles, compound queries, shadow-root fullscreen state, permission-gated operations, window geometry and resize events. When optional fullscreen spoofing is enabled, the diagnostic displays this disagreement. Faking fullscreen globally can also confuse a video player's fullscreen controls.

### Screen wake locks and pointer locks

Screen wake locks are released when relevant visibility conditions cease to hold. Pointer lock must be exited when the user agent, window or tab loses focus. Those mechanisms create additional observable state changes even when ordinary page visibility/focus events are intercepted. [10][11]

The prototype does not fake wake-lock success, prevent release, spoof pointer-lock ownership or disable the user's escape controls. These are operational APIs, not passive Boolean readouts.

### Real input and event timing

Mouse/pointer departure, keyboard and scroll behavior, focus-related selectors, input timestamps, user-activation state and event timing provide other evidence of interaction. Script-dispatched events do not acquire browser-generated trust merely because code changes an unrelated property. Event Timing exposes information about actual interactions; it is not equivalent to page visibility. [1][12][13]

The prototype generates no mouse movements, clicks, keystrokes or scrolls; does not alter `Event.isTrusted`; and preserves actual user-activation semantics. It does not claim a site cannot distinguish an untouched page from someone actively operating it. Visible and focused never prove that a human is looking at a screen.

### Rendered-element visibility and geometry

`IntersectionObserver` concerns element intersection with a root/viewport, and visibility-tracking features add rendering-related checks. It is not simply another API for whether a browser tab is selected. Returning `isIntersecting=true` for everything would affect lazy loading, scrolling interfaces, ads and rendering logic. [14]

The prototype leaves intersection/resize observers, element geometry, CSS layout, visual viewport, orientation and most display characteristics alone. These are not comprehensively safe to spoof through one small extension.

### Actual navigation, sharing and external observation

Switching away while a document remains loaded differs from navigating that same tab to another page. Once the old document is destroyed or frozen, getter substitutions do not continue its application session. Its server may detect a closed connection or missing activity. [8]

Likewise, browser-controlled screen capture exposes a user-selected display surface under browser permissions. Changing a page's screen-count readout does not change actual captured pixels or make additional applications unaware of hardware. This extension does not alter screen capture, other extensions or installed monitoring software. [15]

## Broader privacy surfaces: important, but a different layer

The following deserve a privacy review, but should not be folded into this extension by indiscriminately returning constants:

| Group | Representative surfaces | Recommended approach for a broader privacy design |
|---|---|---|
| Persistent identifiers | Cookies, local storage, IndexedDB, cached state, account identity | Storage partitioning/restriction, appropriate clearing and separate profiles; a visibility patch does not address identity |
| Network identification | IP address, request headers, cross-site requests and correlation | Browser/network controls and content filtering; do not fake API success while silently dropping legitimate requests |
| Rendering fingerprints | Canvas, WebGL/WebGPU, audio rendering, font measurements | Coordinated browser-level normalization or carefully designed randomization, tested across related APIs |
| Device and browser characteristics | User-Agent/Client Hints, CPU/memory hints, screen resolution, language, time zone | Reduce exposed detail using a coherent profile; inconsistent or rare combinations may themselves be identifying |
| Privileged personal/hardware access | Camera/microphone, geolocation, screen sharing, local fonts, USB/Bluetooth/HID/serial access | Audit actual permission grants and decline unnecessary access; do not report arbitrary `granted` status |
| Load and environment signals | Compute pressure, CPU performance tiers, connection information, battery and sensor data where supported | Evaluate availability, granularity, permission/policy rules and practical relevance individually |

The categories of stateful/stateless fingerprinting, identifier correlation and entropy reduction are covered by W3C's fingerprinting guidance. That document supports treating defenses as a coordinated design rather than assuming more missing or constant values always yield more privacy. [16] Permission state is its own API contract; cosmetic readout changes do not revoke an actual grant. [17] Chromium's Compute Pressure and CPU Performance documentation illustrate why the hardware/environment inventory must evolve rather than be treated as a permanent exhaustive list. [18][19]

## Practical conclusion

For this request, scoped visible/focused/single-display substitutions are reasonable as an **additional privacy experiment**. They should sit alongside browser tracking protections and carefully controlled permissions, not replace them. Fullscreen should be regarded as the most compatibility-sensitive part of the profile.

A claim of comprehensive protection would require coverage of workers and service workers, JavaScript and CSS consistency, fresh-frame behavior, native methods, scheduling, permission state, and observable interactions. It would also require adversarial tests across browser versions and platforms. That work has not been completed here. No custom extension can honestly promise that every site will always believe a person is paying attention, especially after navigation or disconnection.

The shipped prototype is deliberately inspectable: no server, telemetry, storage, remote code, or synthetic input. Its coverage is described in [behavior and limitations](docs/DETAILS.md), with [verification results and test instructions](docs/TESTING.md). The diagnostic displays native-state signals that remain observable.

## Primary sources

1. WHATWG HTML — page visibility, VisibilityStateEntry, user activation and focus: https://html.spec.whatwg.org/multipage/interaction.html
2. WHATWG Fullscreen API: https://fullscreen.spec.whatwg.org/
3. W3C Window Management, including permission versus Permissions Policy: https://www.w3.org/TR/window-management/
4. W3C Service Workers — WindowClient and client enumeration: https://w3c.github.io/ServiceWorker/#windowclient
5. Chrome extension content scripts and MAIN-world behavior: https://developer.chrome.com/docs/extensions/reference/manifest/content-scripts
6. W3C Media Queries Level 5 — display mode: https://www.w3.org/TR/mediaqueries-5/
7. WICG Idle Detection API: https://wicg.github.io/idle-detection/
8. Chrome Page Lifecycle API: https://developer.chrome.com/docs/web-platform/page-lifecycle-api
9. Chrome background timer throttling: https://developer.chrome.com/blog/timer-throttling-in-chrome-88
10. W3C Screen Wake Lock API: https://www.w3.org/TR/screen-wake-lock/
11. W3C Pointer Lock 2.0: https://www.w3.org/TR/pointerlock-2/
12. WHATWG DOM — event trust: https://dom.spec.whatwg.org/#dom-event-istrusted
13. W3C Event Timing: https://www.w3.org/TR/event-timing/
14. W3C Intersection Observer: https://w3c.github.io/IntersectionObserver/
15. W3C Screen Capture: https://www.w3.org/TR/screen-capture/
16. W3C Mitigating Browser Fingerprinting in Web Specifications: https://www.w3.org/TR/fingerprinting-guidance/
17. W3C Permissions: https://www.w3.org/TR/permissions/
18. Chrome 125 release notes — Compute Pressure: https://developer.chrome.com/release-notes/125
19. Chrome 152 release notes — CPU Performance: https://developer.chrome.com/release-notes/152
20. Chrome unpacked-extension installation: https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world
