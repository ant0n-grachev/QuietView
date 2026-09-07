/* QuietView — MIT License.
 * Version: v1.
 * Best-effort page-level substitutions, NOT an undetectable browser patch.
 * No network requests, telemetry, storage, or fabricated input events.
 * Edit CONFIG, reload the extension, then reload affected pages to customize.
 */
(() => {
  'use strict';
  const CONFIG = Object.freeze({
    visibility: true,
    visibilityTimeline: true,
    windowFocus: true,
    fullscreenReadouts: false, // Optional; can break native fullscreen controls.
    displayModeReadouts: false,// Optional; only simple JS matchMedia queries.
    singleScreen: true,        // One virtual Screen Details object, not zero screens.
    screenCoordinates: true,
    idleReadouts: true,        // Window realm only; native permission checks stay intact.
  });
  const define = Object.defineProperty;
  const descriptor = Object.getOwnPropertyDescriptor;
  const apply = Reflect.apply;
  const add = EventTarget.prototype.addEventListener;
  const stop = Event.prototype.stopImmediatePropagation;

  function getter(obj, key, get, onlyExisting = true) {
    if (!obj || (onlyExisting && !(key in obj))) return;
    const old = descriptor(obj, key);
    if (old && !old.configurable) return;
    define(obj, key, { configurable: true, enumerable: old?.enumerable ?? true, get });
  }
  function method(obj, key, value) {
    if (!obj || typeof obj[key] !== 'function') return;
    const old = descriptor(obj, key);
    if (old && !old.configurable && !old.writable) return;
    define(obj, key, { configurable: true, enumerable: old?.enumerable ?? true,
                       writable: true, value });
  }
  function suppress(target, type, predicate = () => true) {
    apply(add, target, [type, (event) => {
      if (predicate(event)) apply(stop, event, []);
    }, { capture: true }]);
  }
  // A failed optional patch must not prevent unrelated protections from loading.
  function feature(name, enabled, install) {
    if (!enabled) return;
    try { install(); }
    catch (error) { console.warn(`QuietView: ${name} not fully applied.`, error); }
  }

  feature('visibility', CONFIG.visibility, () => {
    for (const key of ['hidden', 'webkitHidden'])
      getter(Document.prototype, key, () => false);
    for (const key of ['visibilityState', 'webkitVisibilityState'])
      getter(Document.prototype, key, () => 'visible');
    for (const type of ['visibilitychange', 'webkitvisibilitychange']) {
      suppress(window, type);
      suppress(document, type);
    }
  });

  feature('window focus', CONFIG.windowFocus, () => {
    method(Document.prototype, 'hasFocus', function hasFocus() { return true; });
    for (const type of ['focus', 'blur', 'focusin', 'focusout']) {
      // Do not break focus/blur on inputs, buttons, editors, or other elements.
      suppress(window, type, e => e.target === window || e.target === document);
    }
  });

  feature('fullscreen readouts', CONFIG.fullscreenReadouts, () => {
    for (const key of ['fullscreenElement', 'webkitFullscreenElement', 'webkitCurrentFullScreenElement']) {
      const original = descriptor(Document.prototype, key)?.get;
      getter(Document.prototype, key, function () {
        // Preserve the real element during actual element-fullscreen sessions.
        return (original ? apply(original, this, []) : null)
          || this.documentElement || this.body || null;
      });
    }
    for (const key of ['fullscreen', 'webkitIsFullScreen'])
      getter(Document.prototype, key, () => true);
    for (const type of ['fullscreenchange', 'webkitfullscreenchange']) {
      suppress(window, type);
      suppress(document, type);
    }
    // Keep requestFullscreen(), exitFullscreen(), fullscreenEnabled and errors
    // authentic. Escape, browser controls and permission gates are not patched.
  });

  feature('display-mode readouts', CONFIG.displayModeReadouts, () => {
    const nativeMatchMedia = window.matchMedia;
    const simpleMode = /^\s*(?:all\s+and\s+)?\(\s*display-mode\s*:\s*(fullscreen|browser|standalone|minimal-ui|window-controls-overlay|picture-in-picture)\s*\)\s*$/i;
    method(window, 'matchMedia', function matchMedia(query) {
      const result = apply(nativeMatchMedia, this, arguments);
      const match = simpleMode.exec(result.media);
      if (match) {
        const matches = match[1].toLowerCase() === 'fullscreen';
        getter(result, 'matches', () => matches);
        suppress(result, 'change');
      }
      return result;
    });
    // Compound queries and CSS @media/:fullscreen are intentionally untouched.
  });

  feature('single screen', CONFIG.singleScreen, () => {
    const originalScreen = window.screen;
    const width = originalScreen.width;
    const height = originalScreen.height;
    const snapshot = Object.freeze({
      width, height, availWidth: width, availHeight: height,
      availLeft: 0, availTop: 0,
      colorDepth: originalScreen.colorDepth, pixelDepth: originalScreen.pixelDepth,
      isExtended: false,
    });
    for (const [key, value] of Object.entries(snapshot))
      getter(Screen.prototype, key, () => value);
    if ('onchange' in originalScreen) suppress(originalScreen, 'change');

    if (typeof window.getScreenDetails === 'function') {
      // This is API-shaped virtual data, not a native ScreenDetailed with native
      // internal slots. Do not claim it can be used for native window placement.
      class SingleScreen extends EventTarget {
        constructor() {
          super();
          const values = { ...snapshot, left: 0, top: 0, isPrimary: true,
            isInternal: false, label: 'Display', devicePixelRatio: window.devicePixelRatio,
            orientation: originalScreen.orientation };
          for (const [key, value] of Object.entries(values))
            define(this, key, { enumerable: true, get: () => value });
          this.onchange = null;
        }
      }
      const screen = new SingleScreen();
      const screens = Object.freeze([screen]);
      class SingleScreenDetails extends EventTarget {
        constructor() {
          super();
          define(this, 'screens', { enumerable: true, get: () => screens });
          define(this, 'currentScreen', { enumerable: true, get: () => screen });
          this.onscreenschange = null;
          this.oncurrentscreenchange = null;
        }
      }
      const details = new SingleScreenDetails();
      method(window, 'getScreenDetails', async function getScreenDetails() {
        return details;
      });
    }
    // Real window-management permission is not requested or silently granted.
    // Current-screen dimensions/DPR are retained, not anonymized.
  });

  feature('screen coordinates', CONFIG.screenCoordinates, () => {
    for (const key of ['screenX', 'screenY', 'screenLeft', 'screenTop'])
      getter(window, key, () => 0);
    for (const ctor of [window.MouseEvent, window.Touch]) {
      if (!ctor) continue;
      getter(ctor.prototype, 'screenX', function () { return this.clientX; });
      getter(ctor.prototype, 'screenY', function () { return this.clientY; });
    }
    // PointerEvent inherits MouseEvent. Layout, pointer input and trusted status
    // are otherwise unchanged. Viewport-exit events are not suppressed.
  });

  feature('idle readouts', CONFIG.idleReadouts, () => {
    const NativeIdleDetector = window.IdleDetector;
    if (typeof NativeIdleDetector !== 'function') return;
    getter(NativeIdleDetector.prototype, 'userState', () => 'active');
    getter(NativeIdleDetector.prototype, 'screenState', () => 'unlocked');
    function IdleDetector(...args) {
      if (!new.target) throw new TypeError("IdleDetector requires 'new'.");
      const detector = Reflect.construct(NativeIdleDetector, args, new.target);
      suppress(detector, 'change');
      return detector;
    }
    // Keep native methods/slots and subclassing, without exposing an unwrapped
    // constructor that could create detectors whose change events are unmasked.
    IdleDetector.prototype = NativeIdleDetector.prototype;
    define(IdleDetector.prototype, 'constructor', {
      value: IdleDetector, writable: true, configurable: true,
    });
    Object.setPrototypeOf(IdleDetector, Object.getPrototypeOf(NativeIdleDetector));
    for (const key of Reflect.ownKeys(NativeIdleDetector)) {
      if (['name', 'length', 'prototype', 'arguments', 'caller'].includes(key)) continue;
      define(IdleDetector, key, descriptor(NativeIdleDetector, key));
    }
    method(window, 'IdleDetector', IdleDetector);
    // Inherited start/requestPermission remain native. No permission prompt is
    // triggered by installation. Workers have their own, unpatched IdleDetector.
  });

  feature('visibility performance timeline', CONFIG.visibilityTimeline, () => {
    if (!window.Performance || !window.PerformanceObserver) return;
    const P = Performance.prototype;
    const nativeGetEntries = P.getEntries;
    const nativeByType = P.getEntriesByType;
    const nativeByName = P.getEntriesByName;
    const NativeObserver = window.PerformanceObserver;
    if (!NativeObserver.supportedEntryTypes.includes('visibility-state')) return;
    const nativeInitial = apply(nativeByType, performance, ['visibility-state'])[0];
    if (!nativeInitial) return;

    // This projection has the entry's API shape, but no native internal slots.
    // Retaining a real hidden entry would expose its original name/toJSON through
    // PerformanceEntry.prototype even if its own properties were replaced.
    const visibleValues = Object.freeze({
      name: 'visible', entryType: 'visibility-state', startTime: 0, duration: 0,
    });
    const initial = Object.create(Object.getPrototypeOf(nativeInitial));
    for (const [key, value] of Object.entries(visibleValues))
      define(initial, key, { enumerable: true, get: () => value });
    define(initial, 'toJSON', { value: function toJSON() { return { ...visibleValues }; } });
    const isVisibility = entry => entry.entryType === 'visibility-state';
    function sanitize(entries, includeInitial = true) {
      const out = [];
      let inserted = false;
      for (const entry of entries) {
        if (!isVisibility(entry)) out.push(entry);
        else if (includeInitial && !inserted) { out.push(initial); inserted = true; }
      }
      return out.sort((a, b) => a.startTime - b.startTime);
    }
    method(P, 'getEntries', function getEntries() {
      return sanitize(apply(nativeGetEntries, this, arguments));
    });
    method(P, 'getEntriesByType', function getEntriesByType(type) {
      return sanitize(apply(nativeByType, this, arguments));
    });
    method(P, 'getEntriesByName', function getEntriesByName(name, type) {
      if (!arguments.length) return apply(nativeByName, this, arguments);
      let convertedName, convertedType;
      // Let native WebIDL validate the receiver and perform conversions in its
      // normal order. Capture each converted string once, including boxed values;
      // native-first name filtering would otherwise reveal whether hidden existed.
      const nativeResult = apply(nativeByName, this, [
        { [Symbol.toPrimitive]() { return convertedName = `${name}`; } },
        type === undefined ? undefined :
          { [Symbol.toPrimitive]() { return convertedType = `${type}`; } },
      ]);
      if (convertedType !== undefined && convertedType !== 'visibility-state')
        return nativeResult;
      return sanitize(apply(nativeGetEntries, this, []))
        .filter(e => e.name === convertedName &&
          (convertedType === undefined || e.entryType === convertedType));
    });

    const List = PerformanceObserverEntryList.prototype;
    const nativeList = List.getEntries;
    const nativeListByType = List.getEntriesByType;
    const nativeListByName = List.getEntriesByName;
    const nativeObserve = NativeObserver.prototype.observe;
    const nativeDisconnect = NativeObserver.prototype.disconnect;
    const nativeTakeRecords = NativeObserver.prototype.takeRecords;
    const states = new WeakMap();
    const projectedLists = new WeakMap();
    function projectedList(entries) {
      const list = Object.create(List);
      projectedLists.set(list, entries);
      define(list, 'getEntries', { value: function getEntries() {
        const values = projectedLists.get(this);
        return values ? values.slice() : apply(nativeList, this, arguments);
      } });
      define(list, 'getEntriesByType', { value: function getEntriesByType(type) {
        const values = projectedLists.get(this);
        if (!values) return apply(nativeListByType, this, arguments);
        if (!arguments.length) throw new TypeError('An entry type is required.');
        const convertedType = `${type}`;
        return values.filter(e => e.entryType === convertedType);
      } });
      define(list, 'getEntriesByName', { value: function getEntriesByName(name, type) {
        const values = projectedLists.get(this);
        if (!values) return apply(nativeListByName, this, arguments);
        if (!arguments.length) throw new TypeError('An entry name is required.');
        const convertedName = `${name}`;
        const convertedType = type === undefined ? undefined : `${type}`;
        return values.filter(e => e.name === convertedName &&
          (convertedType === undefined || e.entryType === convertedType));
      } });
      return list;
    }
    function consume(entries, state) {
      const result = sanitize(entries, !!state?.pendingInitial);
      if (state && entries.some(isVisibility)) state.pendingInitial = false;
      return result;
    }
    function PerformanceObserver(callback) {
      if (!new.target) throw new TypeError("PerformanceObserver requires 'new'.");
      if (typeof callback !== 'function') throw new TypeError('Callback must be a function.');
      const state = { pendingInitial: false };
      const observer = Reflect.construct(NativeObserver, [(list, obs, options) => {
        const entries = apply(nativeList, list, []);
        if (!entries.some(isVisibility)) {
          apply(callback, obs, [list, obs, options]);
          return;
        }
        const sanitized = consume(entries, state);
        if (sanitized.length) apply(callback, obs, [projectedList(sanitized), obs, options]);
      }], new.target);
      states.set(observer, state);
      return observer;
    }
    // Do not inherit from the native constructor: that would hand pages an
    // unfiltered observer through Object.getPrototypeOf(PerformanceObserver).
    for (const key of Reflect.ownKeys(NativeObserver)) {
      if (!['length', 'name', 'prototype', 'arguments', 'caller'].includes(key))
        define(PerformanceObserver, key, descriptor(NativeObserver, key));
    }
    PerformanceObserver.prototype = NativeObserver.prototype;
    method(NativeObserver.prototype, 'constructor', PerformanceObserver);
    method(NativeObserver.prototype, 'observe', function observe(options) {
      let buffered = false, type, entryTypesProvided = false;
      let forwarded = options;
      if (options !== null && (typeof options === 'object' || typeof options === 'function')) {
        // A separate target also accepts frozen dictionaries whose type value
        // is a boxed string: the forwarding proxy has no source invariants.
        forwarded = new Proxy(Object.create(null), { get(target, key) {
          const value = Reflect.get(options, key, options);
          if (key === 'buffered') buffered = !!value;
          if (key === 'entryTypes') entryTypesProvided = value !== undefined;
          if (key === 'type' && value !== undefined) return type = `${value}`;
          return value;
        } });
      }
      const result = apply(nativeObserve, this, arguments.length ? [forwarded] : []);
      const state = states.get(this);
      // Buffered observation already schedules a native callback, independently
      // of a real visibility change. Unbuffered observation must never emit an
      // initial record on the first transition, which would reveal its timing.
      if (state && buffered && type === 'visibility-state' && !entryTypesProvided)
        state.pendingInitial = true;
      return result;
    });
    method(NativeObserver.prototype, 'disconnect', function disconnect() {
      const result = apply(nativeDisconnect, this, arguments);
      const state = states.get(this);
      if (state) state.pendingInitial = false;
      return result;
    });
    method(NativeObserver.prototype, 'takeRecords', function takeRecords() {
      return consume(apply(nativeTakeRecords, this, arguments), states.get(this));
    });
    method(window, 'PerformanceObserver', PerformanceObserver);
  });
})();
