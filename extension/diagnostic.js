'use strict';
(() => {
  const rows = document.getElementById('rows');
  const timeline = document.getElementById('timeline');
  const eventOutput = document.getElementById('events');
  let maxFrameGap = 0;
  let lastFrame;
  const events = [];
  function frame(time) {
    if (lastFrame !== undefined) maxFrameGap = Math.max(maxFrameGap, time - lastFrame);
    lastFrame = time;
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  function display(value) {
    if (value === undefined) return 'unavailable';
    return typeof value === 'string' ? value : JSON.stringify(value);
  }
  const readings = [
    ['document.visibilityState', () => document.visibilityState, 'visible'],
    ['document.hidden', () => document.hidden, 'false'],
    ['document.hasFocus()', () => document.hasFocus(), 'true'],
    ['document.fullscreenElement', () => document.fullscreenElement?.tagName ?? null, 'Native by default; null unless actually fullscreen'],
    ['document.fullscreen', () => document.fullscreen, 'Native by default'],
    ['JS display-mode: fullscreen', () => matchMedia('(display-mode: fullscreen)').matches, 'Native by default'],
    ['Native CSS display-mode', () => getComputedStyle(document.documentElement).getPropertyValue('--native-fullscreen').trim(), 'Native browser display mode'],
    ['Native :fullscreen selector', () => document.documentElement.matches(':fullscreen'), 'Native element fullscreen state'],
    ['screen.isExtended', () => screen.isExtended, 'false, where supported'],
    ['Window screen position', () => [screenX, screenY], '[0, 0]'],
    ['Reported screen dimensions', () => [screen.width, screen.height], 'Initial screen snapshot, not anonymous'],
    ['Actual viewport dimensions', () => [innerWidth, innerHeight], 'Not substituted'],
    ['Actual outer dimensions', () => [outerWidth, outerHeight], 'Not substituted'],
    ['devicePixelRatio', () => devicePixelRatio, 'Not substituted'],
    ['IdleDetector readouts', () => typeof IdleDetector === 'function' ?
      [new IdleDetector().userState, new IdleDetector().screenState] : undefined, 'active, unlocked; Window realm only'],
    ['Largest animation-frame gap', () => `${Math.round(maxFrameGap)} ms`, 'Real timing; not hidden'],
  ];
  const cells = readings.map(([name,,expected]) => {
    const row = document.createElement('tr');
    for (const text of [name, '', expected]) {
      const td = document.createElement('td'); td.textContent = text; row.append(td);
    }
    rows.append(row); return row.children[1];
  });
  function update() {
    readings.forEach(([,read], index) => {
      try { cells[index].textContent = display(read()); }
      catch (error) { cells[index].textContent = `${error.name}: ${error.message}`; }
    });
    try {
      timeline.textContent = JSON.stringify(performance.getEntriesByType('visibility-state').map(e => e.toJSON()), null, 2);
    } catch (error) { timeline.textContent = error.message; }
  }
  const log = text => {
    events.unshift(`${new Date().toLocaleTimeString()}  ${text}`);
    events.length = Math.min(events.length, 16); eventOutput.textContent = events.join('\n');
  };
  for (const type of ['focus', 'blur', 'visibilitychange', 'fullscreenchange'])
    window.addEventListener(type, event => {
      if (type === 'fullscreenchange' || event.target === window || event.target === document) log(`window/document: ${type}`);
    }, true);
  for (const id of ['first', 'second']) for (const type of ['focus', 'blur'])
    document.getElementById(id).addEventListener(type, () => log(`${id} input: ${type}`));
  document.getElementById('screens').addEventListener('click', async () => {
    const output = document.getElementById('screen-output');
    if (typeof getScreenDetails !== 'function') { output.textContent = 'API unavailable in this context.'; return; }
    output.textContent = 'Waiting for the API / permission decision.';
    try {
      const details = await getScreenDetails();
      output.textContent = JSON.stringify({count: details.screens.length,
        currentIsFirst: details.currentScreen === details.screens[0],
        screens: details.screens.map(s => ({label:s.label,width:s.width,height:s.height,
          left:s.left,top:s.top,isExtended:s.isExtended,isPrimary:s.isPrimary}))}, null, 2);
    } catch (error) { output.textContent = `${error.name}: ${error.message}`; }
  });
  if (location.protocol === 'chrome-extension:') document.getElementById('instructions').textContent =
    'This is an extension-internal URL, so the page is NOT covered. Open the diagnostic.html file from the extracted folder with file access enabled, or serve it on localhost.';
  update(); setInterval(update, 1000);
})();
