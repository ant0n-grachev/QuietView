#!/usr/bin/env python3
"""Visibility timeline regressions in Chromium, with labeled transition fixtures.

Native Chromium covers constructor paths, observer lifecycle, ordinary entries and
argument conversion. Explicit fixtures supply hidden initial/history entries and
transitions that headless Chromium cannot reliably produce by changing tabs.
No extension installation, network, persistent browser profile or hardware access.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CHROMIUM = os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium')
results = []


def check(name, actual, expected):
    passed = actual == expected
    results.append({'test': name, 'passed': passed, 'actual': actual, 'expected': expected})
    print(('PASS ' if passed else 'FAIL ') + name + (f': {actual!r}' if not passed else ''), flush=True)


FIXTURE = r'''() => {
  // Native conversion/validation is retained for every observer.observe call.
  const NativeObserver = window.PerformanceObserver;
  const validators = new WeakMap();
  const nativeObserve = NativeObserver.prototype.observe;
  const nativeDisconnect = NativeObserver.prototype.disconnect;
  const slots = new WeakMap();
  const listSlots = new WeakMap();
  for (const key of ['name', 'entryType', 'startTime', 'duration']) {
    const original = Object.getOwnPropertyDescriptor(PerformanceEntry.prototype, key);
    Object.defineProperty(PerformanceEntry.prototype, key, {...original,
      get() { return slots.has(this) ? slots.get(this)[key] : original.get.call(this); }});
  }
  const nativeJSON = PerformanceEntry.prototype.toJSON;
  PerformanceEntry.prototype.toJSON = function() {
    return slots.has(this) ? {...slots.get(this)} : nativeJSON.call(this);
  };
  window.makeFixtureEntry = (name, startTime, entryType = 'visibility-state') => {
    const entry = Object.create(PerformanceEntry.prototype);
    slots.set(entry, {name, entryType, startTime, duration: 0});
    return entry;
  };
  window.rawRecords = [makeFixtureEntry('hidden', 0), makeFixtureEntry('visible', 100),
    makeFixtureEntry('hidden', 250), makeFixtureEntry('kept', 300, 'mark')];
  const nativeAll = Performance.prototype.getEntries;
  const nativeByType = Performance.prototype.getEntriesByType;
  const nativeByName = Performance.prototype.getEntriesByName;
  Performance.prototype.getEntries = function() {
    nativeAll.apply(this, arguments); return rawRecords.slice();
  };
  Performance.prototype.getEntriesByType = function(type) {
    // Forward conversion through native WebIDL exactly once.
    let converted;
    nativeByType.call(this, {[Symbol.toPrimitive]() { return converted = `${type}`; }});
    return rawRecords.filter(e => e.entryType === converted);
  };
  Performance.prototype.getEntriesByName = function(name, type) {
    if (!arguments.length) return nativeByName.call(this);
    let convertedName, convertedType;
    nativeByName.call(this, {[Symbol.toPrimitive]() { return convertedName = `${name}`; }},
      type === undefined ? undefined : {[Symbol.toPrimitive]() { return convertedType = `${type}`; }});
    return rawRecords.filter(e => e.name === convertedName &&
      (convertedType === undefined || e.entryType === convertedType));
  };
  const originalList = PerformanceObserverEntryList.prototype.getEntries;
  PerformanceObserverEntryList.prototype.getEntries = function() {
    return listSlots.has(this) ? listSlots.get(this).slice() : originalList.call(this);
  };
  window.PerformanceObserver = class FixtureObserver {
    static get supportedEntryTypes() { return NativeObserver.supportedEntryTypes; }
    constructor(callback) { this.callback = callback; this.queued = []; validators.set(this, new NativeObserver(() => {})); }
    observe(options) {
      nativeObserve.call(validators.get(this), options);
      nativeDisconnect.call(validators.get(this));
      this.active = true;
    }
    disconnect() { this.active = false; this.queued = []; }
    takeRecords() { const result = this.queued; this.queued = []; return result; }
    deliver(entries) {
      if (!this.active) return;
      const list = Object.create(PerformanceObserverEntryList.prototype);
      listSlots.set(list, entries);
      this.callback.call(this, list, this, {droppedEntriesCount: 0});
    }
  };
}'''

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROMIUM, headless=True, args=['--no-sandbox'])
    fixture = browser.new_page()
    fixture.set_content('<title>Explicit visibility transition fixtures</title>')
    fixture.evaluate(FIXTURE)
    fixture.add_script_tag(content=(ROOT / 'extension/shield.js').read_text())
    visible = [{'name': 'visible', 'entryType': 'visibility-state', 'startTime': 0, 'duration': 0}]
    check('fixture: boxed hidden query exposes no history', fixture.evaluate(
        "performance.getEntriesByName(new String('hidden'),new String('visibility-state')).map(e=>e.toJSON())"), [])
    check('fixture: boxed visible query finds normalized initial state', fixture.evaluate(
        "performance.getEntriesByName(new String('visible'),new String('visibility-state')).map(e=>e.toJSON())"), visible)
    check('fixture: prototype getters cannot recover hidden native state', fixture.evaluate('''() => {
      const entry = performance.getEntriesByType('visibility-state')[0];
      const read = fn => { try { return fn(); } catch (error) { return error.name; } };
      return [read(() => Object.getOwnPropertyDescriptor(PerformanceEntry.prototype,'name').get.call(entry)),
        read(() => PerformanceEntry.prototype.toJSON.call(entry).name)];
    }'''), ['TypeError', 'TypeError'])
    for route in ['PerformanceObserver', 'PerformanceObserver.prototype.constructor', 'Object.getPrototypeOf(PerformanceObserver)']:
        check('fixture: constructor route blocks hidden callbacks: ' + route, fixture.evaluate('''route => {
          const Ctor = eval(route);
          // Function.prototype is deliberately not a constructor alias.
          if (Ctor === Function.prototype) return [];
          const observations = [];
          const observer = new Ctor(list => observations.push(...list.getEntries().map(e => e.name)));
          observer.observe({type:'visibility-state',buffered:true});
          observer.deliver([makeFixtureEntry('hidden',450)]);
          return observations.filter(name => name === 'hidden');
        }''', route), [])
    check('fixture: unbuffered callbacks do not reveal first transition time', fixture.evaluate('''() => {
      const observations = [];
      const observer = new PerformanceObserver(list => observations.push(...list.getEntries().map(e=>e.toJSON())));
      observer.observe({type:'visibility-state'});
      observer.deliver([makeFixtureEntry('hidden',500)]);
      observer.deliver([makeFixtureEntry('visible',600)]);
      return observations;
    }'''), [])
    check('fixture: unbuffered takeRecords does not reveal first transition', fixture.evaluate('''() => {
      const observer = new PerformanceObserver(() => {});
      observer.observe({entryTypes:['visibility-state']});
      observer.queued = [makeFixtureEntry('hidden',700)];
      return observer.takeRecords().map(e=>e.toJSON());
    }'''), [])
    check('fixture: buffered reconnect gets one initial record per subscription', fixture.evaluate('''() => {
      const observations = [];
      const observer = new PerformanceObserver(list => observations.push(list.getEntries().map(e=>e.toJSON())));
      observer.observe({type:'visibility-state',buffered:true});
      observer.deliver([makeFixtureEntry('hidden',800)]);
      observer.disconnect();
      observer.observe({type:'visibility-state',buffered:true});
      observer.deliver([makeFixtureEntry('hidden',900)]);
      observer.deliver([makeFixtureEntry('visible',1000)]);
      return observations;
    }'''), [visible, visible])
    check('fixture: mixed callbacks retain marks without a visibility signal', fixture.evaluate('''() => {
      const observations = [];
      const observer = new PerformanceObserver(list => observations.push(list.getEntries().map(e=>e.name)));
      observer.observe({entryTypes:['visibility-state','mark']});
      observer.deliver([makeFixtureEntry('hidden',1100),makeFixtureEntry('kept',1101,'mark')]);
      return observations;
    }'''), [['kept']])
    check('fixture: failed observe cannot enable synthetic delivery', fixture.evaluate('''() => {
      const observations = [];
      const observer = new PerformanceObserver(list=>observations.push(list.getEntries().map(e=>e.name)));
      observer.observe({type:'visibility-state'});
      try { observer.observe({entryTypes:['visibility-state'],type:'visibility-state',buffered:true}); } catch {}
      observer.deliver([makeFixtureEntry('hidden',1200)]);
      return observations;
    }'''), [])
    check('fixture: projected list converts filters once and rejects missing arguments', fixture.evaluate('''() => {
      let output;
      const observer = new PerformanceObserver(list => {
        const calls=[];
        const errors=[];
        for (const invoke of [()=>list.getEntriesByType(),()=>list.getEntriesByName(),
          ()=>list.getEntriesByType(Symbol()),()=>list.getEntriesByName(Symbol())]) {
          try {invoke();errors.push('none')} catch(e) {errors.push(e.name)}
        }
        const found=list.getEntriesByName({toString(){calls.push('name');return 'kept'}},
          {toString(){calls.push('type');return 'mark'}}).map(e=>e.name);
        output={found,calls,errors};
      });
      observer.observe({type:'visibility-state',buffered:true});
      observer.deliver([makeFixtureEntry('hidden',1300),makeFixtureEntry('kept',1301,'mark'),
        makeFixtureEntry('also-kept',1302,'mark')]);
      return output;
    }'''), {'found':['kept'],'calls':['name','type'],'errors':['TypeError']*4})

    page = browser.new_page()
    page.set_content('<title>Native Chromium timeline regressions</title>')
    errors = []
    warnings = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: warnings.append(message.text)
            if message.type == 'warning' and 'QuietView:' in message.text else None)
    page.evaluate('''() => {
      window.nativeByName = Performance.prototype.getEntriesByName;
      window.nativeObserve = PerformanceObserver.prototype.observe;
    }''')
    page.add_script_tag(content=(ROOT / 'extension/shield.js').read_text())
    check('native: ordinary observer subclass and callback identity preserved', page.evaluate('''() => new Promise(resolve => {
      class CustomObserver extends PerformanceObserver { custom() { return 'works'; } }
      const observer = new CustomObserver(function(list, delivered) {
        observer.disconnect();
        resolve([observer instanceof CustomObserver, observer.custom?.(), this === observer,
          delivered === observer, list.getEntriesByName('regression-mark','mark').length]);
      });
      observer.observe({type:'mark'});
      performance.mark('regression-mark');
    })'''), [True,'works',True,True,1])
    check('native: by-name query coercions happen once in native order', page.evaluate('''() => {
      const calls=[];
      const records=performance.getEntriesByName({toString(){calls.push('name');return 'regression-mark'}},
        {toString(){calls.push('type');return 'mark'}});
      return {calls,names:records.map(e=>e.name)};
    }'''), {'calls':['name','type'],'names':['regression-mark']})
    check('native: by-name exceptions and receiver validation preserved', page.evaluate('''() => {
      const compare = method => {
        const calls=[];
        for (const invoke of [()=>method.call(performance),()=>method.call(performance,Symbol()),
          ()=>method.call(performance,'x',Symbol()),()=>method.call({}, {toString(){calls.push('converted');return 'x'}})]) {
          try {invoke();calls.push('none')} catch(e) {calls.push(e.name)}
        }
        return calls;
      };
      return [compare(nativeByName),compare(Performance.prototype.getEntriesByName)];
    }'''), [['TypeError']*4,['TypeError']*4])
    check('native: buffered takeRecords drains once then reconnects', page.evaluate('''() => {
      const observer=new PerformanceObserver(()=>{});
      observer.observe({type:'visibility-state',buffered:true});
      const first=observer.takeRecords().map(e=>e.toJSON());
      const empty=observer.takeRecords();
      observer.disconnect();
      observer.observe({type:'visibility-state',buffered:true});
      const second=observer.takeRecords().map(e=>e.toJSON());
      observer.disconnect();
      return [first,empty,second];
    }'''), [visible,[],visible])
    check('native: observe getters and coercion match native behavior', page.evaluate('''() => {
      const run = observe => {
        const calls=[];
        const observer=new PerformanceObserver(()=>{});
        observe.call(observer, {
          get buffered(){calls.push('buffered');return true},
          get durationThreshold(){calls.push('durationThreshold');return undefined},
          get entryTypes(){calls.push('entryTypes');return undefined},
          get type(){calls.push('type');return {toString(){calls.push('type string');return 'visibility-state'}}}
        });
        observer.disconnect();return calls;
      };
      const native=run(nativeObserve),patched=run(PerformanceObserver.prototype.observe);
      return {equal:JSON.stringify(native)===JSON.stringify(patched),native,patched};
    }'''), {'equal':True,'native':['buffered','durationThreshold','entryTypes','type','type string'],
            'patched':['buffered','durationThreshold','entryTypes','type','type string']})
    check('native: frozen observe options accept boxed type values', page.evaluate('''() => {
      const observer=new PerformanceObserver(()=>{});
      try {
        observer.observe(Object.freeze({type:new String('visibility-state'),buffered:true}));
        const records=observer.takeRecords().map(e=>e.toJSON());
        observer.disconnect();return records;
      } catch(error) { return error.name; }
    }'''), visible)
    check('native: no script errors or installation warnings', [errors,warnings], [[],[]])
    browser.close()

print(f"{sum(result['passed'] for result in results)}/{len(results)} passed")
if os.environ.get('ATTENTION_RESULTS_PATH'):
    Path(os.environ['ATTENTION_RESULTS_PATH']).write_text(json.dumps(results,indent=2)+'\n')
raise SystemExit(0 if all(result['passed'] for result in results) else 1)
