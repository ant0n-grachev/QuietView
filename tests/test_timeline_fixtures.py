#!/usr/bin/env python3
"""Tests hostile/hidden visibility records with explicit input fixtures.
Chromium DOM is real; source Performance/Observer records below are fixtures.
"""
import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
results=[]
def check(name,actual,expected):
    ok=actual==expected;results.append(dict(test=name,passed=ok,actual=actual,expected=expected))
    print(('PASS ' if ok else 'FAIL ')+name+(f': {actual!r}' if not ok else ''),flush=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
    page=browser.new_page();page.set_content('<title>Timeline fixture tests</title>')
    page.evaluate('''()=>{
      // Start from a genuinely "hidden"-shaped document API fixture.
      Object.defineProperty(Document.prototype,'hidden',{configurable:true,get:()=>true});
      Object.defineProperty(Document.prototype,'visibilityState',{configurable:true,get:()=> 'hidden'});
      Document.prototype.hasFocus=()=>false;
      const entry=(name,startTime,type='visibility-state')=>({name,entryType:type,startTime,duration:0,
        toJSON(){return{name:this.name,entryType:this.entryType,startTime:this.startTime,duration:this.duration}}});
      window.rawRecords=[entry('hidden',0),entry('visible',100),entry('hidden',250),entry('mark',300,'mark')];
      Performance.prototype.getEntries=function(){return rawRecords.slice()};
      // Keep WebIDL string conversion in this fixture: the production wrapper
      // relies on the native API converting strings, including boxed arguments.
      Performance.prototype.getEntriesByType=function(type){
        const converted=`${type}`;return rawRecords.filter(e=>e.entryType===converted)};
      Performance.prototype.getEntriesByName=function(name,type){
        const convertedName=`${name}`,convertedType=type===undefined?undefined:`${type}`;
        return rawRecords.filter(e=>e.name===convertedName&&
          (convertedType===undefined||e.entryType===convertedType))};
      const originalListGetter=PerformanceObserverEntryList.prototype.getEntries;
      PerformanceObserverEntryList.prototype.getEntries=function(){
        return this.fixtureEntries?this.fixtureEntries.slice():originalListGetter.call(this);
      };
      window.nativeFixtureObservers=[];
      const NativeObserver=window.PerformanceObserver;
      const validateObserve=NativeObserver.prototype.observe;
      window.PerformanceObserver=class FixtureObserver {
        static supportedEntryTypes=['visibility-state','mark'];
        constructor(callback){this.callback=callback;this.queued=[];
          this.validator=new NativeObserver(()=>{});nativeFixtureObservers.push(this)}
        observe(options){return validateObserve.call(this.validator,options)}
        disconnect(){this.validator.disconnect();this.queued=[]}
        takeRecords(){const q=this.queued;this.queued=[];return q}
        deliver(entries){const list=Object.create(PerformanceObserverEntryList.prototype);
          list.fixtureEntries=entries;this.callback(list,this,{droppedEntriesCount:0})}
      };
      window.makeFixtureEntry=entry;
    }''')
    page.add_script_tag(content=(ROOT/'extension/shield.js').read_text())
    check('hidden document fixture substituted',page.evaluate('[document.hidden,document.visibilityState,document.hasFocus()]'),[False,'visible',True])
    expected=[dict(name='visible',entryType='visibility-state',startTime=0,duration=0)]
    check('initial hidden and subsequent transitions collapsed',page.evaluate("performance.getEntriesByType('visibility-state').map(e=>e.toJSON())"),expected)
    check('all-entry lookup has one visibility record',page.evaluate("performance.getEntries().filter(e=>e.entryType==='visibility-state').map(e=>e.toJSON())"),expected)
    check('by-name hidden lookup is empty',page.evaluate("performance.getEntriesByName('hidden','visibility-state').length"),0)
    check('by-name visible lookup is normalized',page.evaluate("performance.getEntriesByName('visible','visibility-state').map(e=>e.toJSON())"),expected)
    check('ordinary marks survive',page.evaluate("performance.getEntriesByName('mark','mark').length"),1)
    page.evaluate('''()=>{window.deliveries=[];
      window.observer=new PerformanceObserver(l=>deliveries.push(l.getEntries().map(e=>e.toJSON())));
      observer.observe({type:'visibility-state',buffered:true});
      observer.deliver([makeFixtureEntry('hidden',100)]);
      observer.deliver([makeFixtureEntry('visible',200)]);
      observer.deliver([makeFixtureEntry('hidden',300)]);
    }''')
    check('observer emits only one initial visible state',page.evaluate('deliveries'),[expected])
    page.evaluate("observer.queued=[makeFixtureEntry('hidden',400)]")
    check('takeRecords does not expose later transitions',page.evaluate('observer.takeRecords().length'),0)
    page.evaluate('''()=>{window.mixed=[];window.mixedObserver=new PerformanceObserver(l=>mixed.push(l.getEntriesByType('mark').map(e=>e.name)));
      mixedObserver.deliver([makeFixtureEntry('hidden',50),makeFixtureEntry('kept',60,'mark')]);
      mixedObserver.deliver([makeFixtureEntry('hidden',70),makeFixtureEntry('kept2',80,'mark')]);}''')
    check('mixed observer preserves other records',page.evaluate('mixed'),[['kept'],['kept2']])
    report=dict(browser=browser.version,mode='explicit hidden-document and timeline fixtures',results=results,passed=sum(r['passed'] for r in results),total=len(results))
    (ROOT/'tests/timeline-fixture-results.json').write_text(json.dumps(report,indent=2)+'\n')
    browser.close()
print(f"{report['passed']}/{report['total']} passed")
raise SystemExit(0 if report['passed']==report['total'] else 1)
