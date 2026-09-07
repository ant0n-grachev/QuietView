#!/usr/bin/env python3
"""Exercise the default visible/focused/single-screen contract in Chromium.

Requires playwright. Linux: xvfb-run -a python tests/test_browser.py
CHROMIUM_PATH selects the executable. --headless is useful for API coverage,
but native visibility transitions are reported as skipped if Chrome does not
produce them. --baseline omits the extension and intentionally runs the same
protection assertions to show which results depend on the extension.
"""
import argparse
import http.server
import json
import os
from pathlib import Path
import tempfile
import threading
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parents[1]
PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('--baseline', action='store_true')
PARSER.add_argument('--headless', action='store_true')
ARGS = PARSER.parse_args()
TIMEOUT = 5000
FIRST_STATE = '''window.firstState = {
  visibility:document.visibilityState, focus:document.hasFocus(),
  full:!!document.fullscreenElement,
  pointer:(()=>{const e=new MouseEvent('mousemove',
    {clientX:7,clientY:9,screenX:777,screenY:999});return[e.screenX,e.screenY]})()
};'''
FRAME_HTML = '<!doctype html><script>' + FIRST_STATE + '</script><p>frame</p>'
POINTER_READOUT = "(()=>{const e=new MouseEvent('mousemove',{clientX:7,clientY:9,screenX:777,screenY:999});return[e.screenX,e.screenY]})()"
VISIBLE_ENTRY = {'name':'visible','entryType':'visibility-state','startTime':0,'duration':0}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/worker.js':
            body = "postMessage({idle:typeof IdleDetector, focus:typeof document});"
            mime = 'text/javascript'
        elif self.path == '/frame':
            body = FRAME_HTML
            mime = 'text/html'
        else:
            body = '''<!doctype html><meta charset="utf-8"><title>Privacy test</title>
            <script>''' + FIRST_STATE + '''</script>
            <style>:root{--native-fullscreen:no}
            @media (display-mode:fullscreen){:root{--native-fullscreen:yes}}</style>
            <input id="a"><input id="b"><button id="button">Click</button><p>Test page</p>'''
            mime = 'text/html'
        self.send_response(200)
        self.send_header('Content-Type', mime)
        if self.path == '/csp':
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'")
        self.end_headers()
        self.wfile.write(body.encode())


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://localhost:{server.server_port}'
results = []
observations = []


def check(name, actual, expected=True):
    success = actual == expected
    results.append({'test':name,'status':'pass' if success else 'fail',
                    'pass':success,'actual':actual,'expected':expected})
    print(('PASS ' if success else 'FAIL ') + name
          + ('' if success else f': {actual!r} != {expected!r}'), flush=True)


def skip(name, reason, actual=None):
    results.append({'test':name,'status':'skip','pass':None,'reason':reason,'actual':actual})
    print('SKIP ' + name + ': ' + reason, flush=True)


def launch(p, profile, extension=False):
    args = ['--no-sandbox']
    if extension:
        ext = str(ROOT / 'extension')
        args += [f'--disable-extensions-except={ext}', f'--load-extension={ext}']
    ctx = p.chromium.launch_persistent_context(
        profile, executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'),
        headless=ARGS.headless, args=args, no_viewport=True,
        # Do not let Playwright's usual background flags hide native behavior.
        ignore_default_args=['--disable-backgrounding-occluded-windows',
                             '--disable-renderer-backgrounding'],
    )
    ctx.set_default_timeout(TIMEOUT)
    ctx.set_default_navigation_timeout(TIMEOUT)
    return ctx


def disable_focus_emulation(ctx, page):
    # Playwright enables focus emulation separately on EVERY new main page.
    session = ctx.new_cdp_session(page)
    session.send('Emulation.setFocusEmulationEnabled', {'enabled':False})
    return session


def background_probe(ctx, page):
    """Apply the same real tab switch to patched and unpatched browsers."""
    session = disable_focus_emulation(ctx, page)
    other = ctx.new_page()
    other.goto(base + '/other')
    other_session = disable_focus_emulation(ctx, other)
    page.bring_to_front()
    page.evaluate('''()=>{
      window.nativeTransitionEvents={visibility:0,blur:0};
      document.addEventListener('visibilitychange',e=>{
        if(e.isTrusted)nativeTransitionEvents.visibility++;
      });
      window.addEventListener('blur',e=>{
        if(e.isTrusted)nativeTransitionEvents.blur++;
      });
    }''')
    readout = '''({visibility:document.visibilityState,focus:document.hasFocus(),
      events:{...nativeTransitionEvents},
      history:performance.getEntriesByType('visibility-state').map(e=>e.toJSON())})'''
    before = page.evaluate(readout)
    other.bring_to_front()
    try:
        page.wait_for_function("document.visibilityState === 'hidden'", timeout=600)
    except PlaywrightTimeoutError:
        pass
    after = page.evaluate(readout)
    page.bring_to_front()
    other.close()
    session.detach()
    # Closing a page also detaches its CDP session.
    del other_session
    return {'before':before,'after':after}


try:
    with sync_playwright() as p:
        # A separate extension-free browser proves whether the environment can
        # exercise native focus/visibility changes; a visible patched value alone
        # is insufficient evidence. Never grant any browser permissions here.
        with tempfile.TemporaryDirectory(prefix='quietview-native-') as native_profile:
            native_ctx = launch(p, native_profile)
            native_page = native_ctx.pages[0]
            native_page.goto(base)
            native_marker = native_page.evaluate('firstState.pointer')
            native_probe = background_probe(native_ctx, native_page)
            native_ctx.close()
        check('native reference has no extension substitutions',native_marker,[777,999])
        native_focus_changed = (native_probe['before']['focus'] is True
            and native_probe['after']['focus'] is False
            and native_probe['after']['events']['blur'] > 0)
        native_visibility_changed = (native_probe['before']['visibility'] == 'visible'
            and native_probe['after']['visibility'] == 'hidden'
            and native_probe['after']['events']['visibility'] > 0)
        observations.append({'test':'unpatched native background reference','actual':native_probe})
        print('Native background reference: ' + json.dumps(native_probe),flush=True)

        with tempfile.TemporaryDirectory(prefix='quietview-test-') as profile:
            ctx = launch(p, profile, extension=not ARGS.baseline)
            page = ctx.pages[0]
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base)
            browser_version = ctx.browser.version if ctx.browser else page.evaluate('navigator.userAgent')
            print('Browser:',browser_version,flush=True)
            check('substitutions present before first inline script',page.evaluate('firstState.pointer'),[7,9])
            check('visibility readout',page.evaluate('document.visibilityState'),'visible')
            check('hidden readout',page.evaluate('document.hidden'),False)
            check('focused readout',page.evaluate('document.hasFocus()'))
            check('default fullscreen readout remains native',page.evaluate('firstState.full'),False)
            check('default fullscreen element remains null',page.evaluate('document.fullscreenElement'),None)
            check('default fullscreen matchMedia remains native',page.evaluate("matchMedia('(display-mode: fullscreen)').matches"),False)
            check('browser display-mode remains native',page.evaluate("matchMedia('(display-mode: browser)').matches"))
            check('unrelated media query remains native',page.evaluate("matchMedia('(min-width: 0px)').matches"))
            page.evaluate('''()=>{
              window.realFullscreenEvents=0;window.fullscreenAttempt=null;
              document.addEventListener('fullscreenchange',()=>realFullscreenEvents++);
              button.addEventListener('click',async()=>{
                try{await document.documentElement.requestFullscreen();fullscreenAttempt='entered'}
                catch(e){fullscreenAttempt=e.name}
              },{once:true});
            }''')
            page.click('#button')
            page.wait_for_function('fullscreenAttempt !== null')
            check('real fullscreen request remains usable with user activation',page.evaluate('fullscreenAttempt'),'entered')
            check('real fullscreen exposes the actual requested element',page.evaluate('document.fullscreenElement===document.documentElement'))
            exit_fullscreen = page.evaluate('''async()=>Promise.race([
              document.exitFullscreen().then(()=>'exited',e=>e.name),
              new Promise(r=>setTimeout(()=>r('fullscreen timeout'),1500))])''')
            check('real fullscreen exit remains usable',exit_fullscreen,'exited')
            try:
                page.wait_for_function('realFullscreenEvents===2',timeout=1500)
            except PlaywrightTimeoutError:
                pass
            check('real fullscreen entry and exit events remain native',page.evaluate('realFullscreenEvents'),2)
            check('fullscreen element returns to null after exit',page.evaluate('document.fullscreenElement'),None)
            check('single display readout',page.evaluate('screen.isExtended'),False)
            check('window coordinates normalized',page.evaluate('[screenX,screenY,screenLeft,screenTop]'),[0,0,0,0])
            check('pointer screen coordinates normalized',page.evaluate(POINTER_READOUT),[7,9])
            check('screen dimensions remain positive and internally consistent',page.evaluate('''()=>
              screen.width>0 && screen.height>0 && screen.availWidth===screen.width
              && screen.availHeight===screen.height && screen.availLeft===0 && screen.availTop===0'''))
            permission_query = '''async()=>Object.fromEntries(await Promise.all(
              ['window-management','idle-detection'].map(async name=>{
                try{return[name,(await navigator.permissions.query({name})).state]}
                catch(e){return[name,e.name]}
              })))'''
            permissions_before = page.evaluate(permission_query)
            check('fresh profile has no relevant permission grants',
                  all(value != 'granted' for value in permissions_before.values()))
            # A bounded race keeps the intentionally unpatched baseline's native
            # screen-details permission gate from hanging the suite.
            details = page.evaluate('''async()=>{
              if(typeof getScreenDetails!=='function')return 'unavailable';
              try{return await Promise.race([
                (async()=>{const d=await getScreenDetails(),again=await getScreenDetails();
                  const s=d.currentScreen;return{count:d.screens.length,
                    same:d===again&&d.screens===again.screens&&s===d.screens[0]&&s===again.currentScreen,
                    frozen:Object.isFrozen(d.screens),extended:s.isExtended,
                    origin:[s.left,s.top,s.availLeft,s.availTop],primary:s.isPrimary,
                    dimensions:s.width===screen.width&&s.height===screen.height
                      &&s.availWidth===screen.availWidth&&s.availHeight===screen.availHeight,
                    events:typeof d.addEventListener,screenEvents:typeof s.addEventListener,
                    handlerProperties:d.onscreenschange===null&&d.oncurrentscreenchange===null
                      &&s.onchange===null};})(),
                new Promise(r=>setTimeout(()=>r('permission pending'),700))]);
              }catch(e){return e.name}
            }''')
            check('virtual screen details are stable and internally consistent',details,
                  {'count':1,'same':True,'frozen':True,'extended':False,
                   'origin':[0,0,0,0],'primary':True,'dimensions':True,
                   'events':'function','screenEvents':'function','handlerProperties':True})
            page.evaluate('''()=>{
              window.counts={visibility:0,blur:0,fullscreen:0,inputBlur:0,inputFocus:0};
              document.addEventListener('visibilitychange',()=>counts.visibility++);
              window.addEventListener('blur',()=>counts.blur++);
              document.addEventListener('fullscreenchange',()=>counts.fullscreen++);
              a.addEventListener('blur',()=>counts.inputBlur++);
              b.addEventListener('focus',()=>counts.inputFocus++);
              a.focus(); b.focus();
              document.dispatchEvent(new Event('visibilitychange'));
              window.dispatchEvent(new Event('blur'));
              document.documentElement.dispatchEvent(new Event('fullscreenchange',{bubbles:true}));
            }''')
            check('direct visibility and window blur events suppressed',page.evaluate('[counts.visibility,counts.blur]'),[0,0])
            check('default fullscreen events remain native',page.evaluate('counts.fullscreen'),1)
            check('form focus and blur preserved',page.evaluate('[counts.inputBlur,counts.inputFocus]'),[1,1])
            page.evaluate('''()=>{
              window.visibilityObservations=[];
              window.visibilityObserver=new PerformanceObserver(list=>{
                visibilityObservations.push(list.getEntries().map(e=>e.toJSON()));
              });
              visibilityObserver.observe({type:'visibility-state',buffered:true});
            }''')
            try:
                page.wait_for_function('visibilityObservations.length > 0')
            except PlaywrightTimeoutError:
                pass
            protected_probe = background_probe(ctx,page)
            observations.append({'test':'tested background readouts','actual':protected_probe})
            if native_focus_changed:
                check('background focus masks demonstrated native focus loss',protected_probe['after']['focus'])
                check('trusted window blur event suppressed after native focus loss',protected_probe['after']['events']['blur'],0)
            else:
                skip('native background focus protection',
                     'Unpatched Chrome did not produce a trusted focus-loss transition.',native_probe)
            if native_visibility_changed:
                check('background visibility masks demonstrated native hidden state',protected_probe['after']['visibility'],'visible')
                check('trusted visibility event suppressed after native hidden transition',protected_probe['after']['events']['visibility'],0)
            else:
                skip('native hidden-state and visibility-event protection',
                     'Unpatched Chrome remained visible during the tab switch; real hidden-state coverage is inconclusive.',native_probe)
            check('visible timeline readout normalized',page.evaluate("performance.getEntriesByType('visibility-state').map(e=>e.toJSON())"),[VISIBLE_ENTRY])
            check('hidden history absent from readout',page.evaluate("performance.getEntriesByName('hidden','visibility-state').length"),0)
            check('visible history by name normalized',page.evaluate("performance.getEntriesByName('visible','visibility-state').map(e=>e.toJSON())"),[VISIBLE_ENTRY])
            check('visibility observer delivers initial normalized visible state',page.evaluate('visibilityObservations'),[[VISIBLE_ENTRY]])
            if not native_visibility_changed:
                skip('native hidden timeline entries and observer events filtered',
                     'The native reference generated no hidden transition; synthetic fixture coverage is separate.')
            perf = page.evaluate('''async()=>Promise.race([
              new Promise(resolve=>{
                const observer=new PerformanceObserver(list=>{
                  const e=list.getEntriesByType('mark');observer.disconnect();
                  resolve({name:e[0]?.name,byName:list.getEntriesByName('test-mark').length});
                });observer.observe({type:'mark'});performance.mark('test-mark');
              }),new Promise(r=>setTimeout(()=>r('observer timeout'),1500))])''')
            check('ordinary performance observers preserved',perf,{'name':'test-mark','byName':1})
            check('ordinary performance marks preserved',page.evaluate("performance.getEntriesByName('test-mark','mark').length"),1)
            idle = page.evaluate("()=>typeof IdleDetector==='function' ? [new IdleDetector().userState,new IdleDetector().screenState] : 'unavailable'")
            check('main-world idle readouts normalized',idle,['active','unlocked'])
            check('idle permission and start methods remain native',page.evaluate('''()=>({
              requestPermission:typeof IdleDetector.requestPermission,
              start:typeof IdleDetector.prototype.start,
              nativeRequestPermission:Function.prototype.toString.call(IdleDetector.requestPermission).includes('[native code]'),
              nativeStart:Function.prototype.toString.call(IdleDetector.prototype.start).includes('[native code]')
            })'''),{'requestPermission':'function','start':'function',
                    'nativeRequestPermission':True,'nativeStart':True})
            check('synthetic inputs remain untrusted',page.evaluate("new MouseEvent('click').isTrusted"),False)
            idle_permission = page.evaluate('''async()=>Promise.race([
              (async()=>{try{await new IdleDetector().start({threshold:60000});return 'allowed'}
                catch(e){return e.name}})(),
              new Promise(r=>setTimeout(()=>r('permission timeout'),1500))])''')
            check('native idle start still requires permission',idle_permission,'NotAllowedError')
            check('screen details and idle reads do not grant native permissions',
                  page.evaluate(permission_query),permissions_before)
            page.evaluate('''()=>{window.unloadTest=0;
              addEventListener('beforeunload',()=>unloadTest++);
              dispatchEvent(new Event('beforeunload'));}''')
            check('unsaved-work event handling preserved',page.evaluate('unloadTest'),1)
            for label, url in [('same-origin',base+'/frame'),
                               ('cross-origin',f'http://127.0.0.1:{server.server_port}/frame')]:
                with page.expect_event('frameattached') as attached:
                    page.evaluate('''({label,url})=>{const f=document.createElement('iframe');
                      f.name=label;f.src=url;document.body.append(f)}''',{'label':label,'url':url})
                frame = attached.value
                frame.wait_for_function('window.firstState !== undefined')
                check(label+' frame injected before inline script',frame.evaluate('firstState.pointer'),[7,9])
                check(label+' frame visible and focused',frame.evaluate('[document.visibilityState,document.hasFocus()]'),['visible',True])
                check(label+' frame retains native fullscreen state',frame.evaluate('firstState.full'),False)
            for kind in ['about:blank','srcdoc','blob']:
                # Immediate access to a newly created child realm can precede
                # extension injection. Record that observation without claiming
                # the manifest closes every page-created-frame timing race.
                with page.expect_event('frameattached') as attached:
                    immediate = page.evaluate('''({kind,html})=>{
                      const f=document.createElement('iframe');f.name=kind;
                      if(kind==='srcdoc')f.srcdoc=html;
                      else if(kind==='blob')f.src=URL.createObjectURL(new Blob([html],{type:'text/html'}));
                      else f.src='about:blank';
                      document.body.append(f);
                      try{const e=new f.contentWindow.MouseEvent('mousemove',
                        {clientX:7,clientY:9,screenX:777,screenY:999});return[e.screenX,e.screenY]}
                      catch(e){return e.name}
                    }''',{'kind':kind,'html':FRAME_HTML})
                observations.append({'test':kind+' immediate child-realm readout (timing diagnostic)','actual':immediate})
                frame = attached.value
                if kind == 'about:blank':
                    try:
                        frame.wait_for_function(POINTER_READOUT + '.join() === "7,9"',timeout=1500)
                    except PlaywrightTimeoutError:
                        pass
                else:
                    frame.wait_for_function('window.firstState !== undefined')
                    check(kind+' frame injected before its inline script',frame.evaluate('firstState.pointer'),[7,9])
                check(kind+' related frame receives substitutions after load',frame.evaluate(POINTER_READOUT),[7,9])
                check(kind+' related frame visible and focused',frame.evaluate('[document.visibilityState,document.hasFocus()]'),['visible',True])
                check(kind+' related frame retains native fullscreen state',frame.evaluate('!!document.fullscreenElement'),False)
                if kind == 'blob':
                    page.evaluate('(url)=>URL.revokeObjectURL(url)',frame.url)
            csp = ctx.new_page()
            csp.goto(base+'/csp')
            check('strict CSP page receives substitutions',csp.evaluate(POINTER_READOUT),[7,9])
            check('CSS fullscreen rendering remains native',page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--native-fullscreen').trim()"),'no')
            worker = page.evaluate('''()=>new Promise(resolve=>{
              const w=new Worker('/worker.js');const timeout=setTimeout(()=>{w.terminate();resolve('worker timeout')},1500);
              w.onmessage=e=>{clearTimeout(timeout);w.terminate();resolve(e.data)};
              w.onerror=()=>{clearTimeout(timeout);w.terminate();resolve('worker error')};
            })''')
            check('worker remains outside main-window patches (known limitation)',worker,{'idle':'function','focus':'undefined'})
            check('no uncaught page errors',errors,[])
            report = {'baseline':ARGS.baseline,'headless':ARGS.headless,'browser':browser_version,
                      'results':results,'observations':observations,
                      'passed':sum(r['status']=='pass' for r in results),
                      'failed':sum(r['status']=='fail' for r in results),
                      'skipped':sum(r['status']=='skip' for r in results),'total':len(results)}
            target = ROOT/'tests'/('baseline-results.json' if ARGS.baseline else 'test-results.json')
            target.write_text(json.dumps(report,indent=2)+'\n')
            ctx.close()
finally:
    server.shutdown()
print(f"{sum(r['status']=='pass' for r in results)} passed, "
      f"{sum(r['status']=='fail' for r in results)} failed, "
      f"{sum(r['status']=='skip' for r in results)} skipped",flush=True)
raise SystemExit(1 if any(r['status']=='fail' for r in results) else 0)
