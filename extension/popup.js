'use strict';

const protection = document.getElementById('protection');
const state = document.getElementById('state');
const status = document.getElementById('status');

async function getEnabled(request) {
  const response = await chrome.runtime.sendMessage(request);
  if (typeof response?.enabled !== 'boolean') {
    throw new Error(response?.error || 'QuietView protection state unavailable.');
  }
  return response.enabled;
}

function render(enabled) {
  protection.checked = enabled;
  protection.disabled = false;
  state.textContent = enabled ? 'On' : 'Off';
  status.textContent = 'Reload open pages after switching.';
}

function unavailable() {
  protection.disabled = true;
  state.textContent = 'Unavailable';
  status.textContent = 'Reopen QuietView to try again.';
}

protection.addEventListener('change', async () => {
  const enabled = protection.checked;
  protection.disabled = true;
  state.textContent = 'Saving…';
  status.textContent = '';

  try {
    render(await getEnabled({ type: 'set-protection', enabled }));
  } catch {
    try {
      render(await getEnabled({ type: 'get-protection' }));
      status.textContent = 'Could not change protection.';
    } catch {
      unavailable();
    }
  }
});

getEnabled({ type: 'get-protection' }).then(render, unavailable);
