'use strict';

const script = {
  id: 'quietview-shield',
  js: ['shield.js'],
  matches: chrome.runtime.getManifest().host_permissions,
  runAt: 'document_start',
  world: 'MAIN',
  allFrames: true,
  matchOriginAsFallback: true,
  persistAcrossSessions: true,
};

let pending = Promise.resolve();

function serialize(operation) {
  const result = pending.then(operation);
  pending = result.catch(() => {});
  return result;
}

async function setRegistration(enabled) {
  const filter = { ids: [script.id] };
  const [registered] = await chrome.scripting.getRegisteredContentScripts(filter);
  if (enabled && !registered) await chrome.scripting.registerContentScripts([script]);
  if (!enabled && registered) await chrome.scripting.unregisterContentScripts(filter);
}

async function restoreProtection() {
  const { protectionEnabled } = await chrome.storage.local.get({ protectionEnabled: true });
  await setRegistration(protectionEnabled);
  return protectionEnabled;
}

function initialize() {
  serialize(restoreProtection).catch(error => console.error('QuietView setup failed:', error));
}

chrome.runtime.onInstalled.addListener(initialize);
chrome.runtime.onStartup.addListener(initialize);

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.url !== chrome.runtime.getURL('popup.html')) return false;
  const set = message?.type === 'set-protection' && typeof message.enabled === 'boolean';
  if (!set && message?.type !== 'get-protection') return false;

  serialize(async () => {
    if (!set) return restoreProtection();

    await setRegistration(message.enabled);
    try {
      await chrome.storage.local.set({ protectionEnabled: message.enabled });
    } catch (error) {
      await restoreProtection();
      throw error;
    }
    return message.enabled;
  }).then(enabled => reply({ enabled }), () => reply({ error: 'Could not update protection.' }));
  return true;
});
