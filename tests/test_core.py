#!/usr/bin/env python3
"""Real Chromium DOM tests; no extension installation or network is required.
The optional secure-context Screen Details and Idle APIs use labeled fixtures.
Run: xvfb-run -a python tests/test_core.py [--baseline]
"""
import argparse, json, os
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--baseline',action='store_true')
args=parser.parse_args(); results=[]
def check(name,actual,expected=True):
    ok=actual==expected
    results.append(dict(test=name,passed=ok,actual=actual,expected=expected))
    print(('PASS ' if ok else 'FAIL ')+name+(f': {actual!r}' if not ok else ''),flush=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),headless=False,args=['--no-sandbox'])
    context=browser.new_context(); page=context.new_page(); errors=[]; warnings=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('console',lambda msg: warnings.append(msg.text) if msg.type=='warning' and 'QuietView:' in msg.text else None)
    page.set_content('''<!doctype html><title>Script tests</title>
      <style>:root{--native-full:no}@media(display-mode:fullscreen){:root{--native-full:yes}}</style>
      <input id="a"><input id="b"><p>Tests</p>''')
    # about:blank has no secure-context hardware APIs. Explicit test fixtures,
    # not a claim that native hardware enumeration was tested.
    page.evaluate('''()=>{
      Object.defineProperty(Screen.prototype,'isExtended',{configurable:true,get(){return true}});
      window.getScreenDetails=async()=>({screens:[{},{}]});
      window.IdleDetector=class IdleDetector extends EventTarget{
        get userState(){return 'idle'} get screenState(){return 'locked'}
        start(){return Promise.reject(new DOMException('No permission','NotAllowedError'))}
        static requestPermission(){return Promise.resolve('denied')}
      };
      window.savedIdleStart=IdleDetector.prototype.start;
    }''')
    if not args.baseline:
      page.add_script_tag(content=(ROOT/'extension/shield.js').read_text())
    check('visibility',page.evaluate('document.visibilityState'),'visible')
    check('hidden',page.evaluate('document.hidden'),False)
    check('focus',page.evaluate('document.hasFocus()'))
    check('fullscreen toggle correctly chooses enter',page.evaluate("document.fullscreenElement ? 'exit' : 'enter'"),'enter')
    check('fullscreen boolean remains native',page.evaluate('document.fullscreen'),False)
    check('fullscreen matchMedia remains native',page.evaluate("matchMedia('(display-mode: fullscreen)').matches"),False)
    check('browser-mode matchMedia remains native',page.evaluate("matchMedia('(display-mode: browser)').matches"))
    check('unrelated media query',page.evaluate("matchMedia('(min-width:0px)').matches"))
    check('screen extended (fixture)',page.evaluate('screen.isExtended'),False)
    check('screen origin',page.evaluate('[screen.availLeft,screen.availTop,screenX,screenY]'),[0,0,0,0])
    check('pointer coordinates',page.evaluate("(()=>{const e=new MouseEvent('mousemove',{clientX:7,clientY:9,screenX:777,screenY:999});return[e.screenX,e.screenY]})()"),[7,9])
    check('one stable screen (fixture)',page.evaluate('''async()=>{const d=await getScreenDetails();return [d.screens.length,d.currentScreen===d.screens[0],d===await getScreenDetails(),typeof d.addEventListener]}'''),[1,True,True,'function'])
    check('screen details agree with public single-display readouts',page.evaluate('''async()=>{
      const d=await getScreenDetails(),s=d.currentScreen;
      return [s.isExtended,s.left,s.top,s.availLeft,s.availTop,s.width===screen.width,
        s.height===screen.height,s.availWidth===screen.availWidth,s.availHeight===screen.availHeight];
    }'''),[False,0,0,0,0,True,True,True,True])
    page.evaluate('''()=>{
      window.events={v:0,b:0,f:0,ib:0,if:0,u:0};
      document.addEventListener('visibilitychange',()=>events.v++);
      window.addEventListener('blur',()=>events.b++);
      document.addEventListener('fullscreenchange',()=>events.f++);
      a.addEventListener('blur',()=>events.ib++);b.addEventListener('focus',()=>events.if++);
      a.focus();b.focus();
      document.dispatchEvent(new Event('visibilitychange'));
      window.dispatchEvent(new Event('blur'));
      document.documentElement.dispatchEvent(new Event('fullscreenchange',{bubbles:true}));
      window.addEventListener('beforeunload',()=>events.u++);
      window.dispatchEvent(new Event('beforeunload'));
    }''')
    check('attention events suppressed while fullscreen events stay functional',page.evaluate('[events.v,events.b,events.f]'),[0,0,1])
    check('element focus/blur preserved',page.evaluate('[events.ib,events.if]'),[1,1])
    check('beforeunload preserved',page.evaluate('events.u'),1)
    page.evaluate('''()=>{
      window.observations=[];
      window.observer=new PerformanceObserver(l=>observations.push(l.getEntries().map(e=>e.toJSON())));
      observer.observe({type:'visibility-state',buffered:true});
    }''')
    page.wait_for_timeout(100)
    other=context.new_page();other.set_content('<title>Another tab</title>');other.bring_to_front()
    page.wait_for_timeout(200)
    check('background visibility',page.evaluate('document.visibilityState'),'visible')
    check('background focus',page.evaluate('document.hasFocus()'))
    page.bring_to_front();page.wait_for_timeout(200)
    expected=[dict(name='visible',entryType='visibility-state',startTime=0,duration=0)]
    check('visibility history',page.evaluate("performance.getEntriesByType('visibility-state').map(e=>e.toJSON())"),expected)
    check('hidden history by name',page.evaluate("performance.getEntriesByName('hidden','visibility-state').length"),0)
    check('visible history by name',page.evaluate("performance.getEntriesByName('visible','visibility-state').length"),1)
    check('visibility observer',page.evaluate('observations'),[expected])
    check('other performance observers',page.evaluate('''()=>new Promise(r=>{
      const p=new PerformanceObserver((l,o)=>{o.disconnect();r(l.getEntriesByName('check','mark').length)});
      p.observe({type:'mark'});performance.mark('check');})'''),1)
    check('other performance entries',page.evaluate("performance.getEntriesByName('check','mark').length"),1)
    check('idle readouts (fixture)',page.evaluate('[new IdleDetector().userState,new IdleDetector().screenState]'),['active','unlocked'])
    check('native idle start preserved (fixture)',page.evaluate('IdleDetector.prototype.start===savedIdleStart'))
    check('idle events suppressed through accessible constructor paths (fixture)',page.evaluate('''()=>{
      let count=0;
      const candidates=[IdleDetector,IdleDetector.prototype.constructor,
        Object.getPrototypeOf(IdleDetector),Object.getPrototypeOf(IdleDetector.prototype).constructor];
      for (const C of new Set(candidates)) {
        if (!C?.prototype || typeof C.prototype.start!=='function') continue;
        const d=new C();d.addEventListener('change',()=>count++);d.dispatchEvent(new Event('change'));
      }
      return count;
    }'''),0)
    check('idle subclass retains readouts and event suppression (fixture)',page.evaluate('''()=>{
      class Child extends IdleDetector {};
      const d=new Child();let events=0;d.addEventListener('change',()=>events++);
      d.dispatchEvent(new Event('change'));
      return [d instanceof Child,d instanceof IdleDetector,d.userState,d.screenState,events];
    }'''),[True,True,'active','unlocked',0])
    check('idle permission request stays native (fixture)',page.evaluate('IdleDetector.requestPermission()'),'denied')
    check('idle permission remains denied (fixture)',page.evaluate('''async()=>{try{await new IdleDetector().start();return 'allowed'}catch(e){return e.name}}'''),'NotAllowedError')
    check('trusted-input semantics preserved',page.evaluate("new MouseEvent('click').isTrusted"),False)
    check('CSS fullscreen is NOT spoofed (known gap)',page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--native-full').trim()"),'no')
    check('no uncaught errors',errors,[])
    check('no failed feature installations',warnings,[])
    report=dict(browser=browser.version,baseline=args.baseline,mode='script-injection into real DOM; not installed extension',
                hardware='Screen Details and Idle Detection API fixtures; no physical multi-monitor test',
                passed=sum(r['passed'] for r in results),total=len(results),results=results)
    (ROOT/'tests'/('baseline-core-results.json' if args.baseline else 'core-results.json')).write_text(json.dumps(report,indent=2)+'\n')
    browser.close()
print(f"{report['passed']}/{report['total']} passed")
raise SystemExit(0 if report['passed']==report['total'] else 1)
