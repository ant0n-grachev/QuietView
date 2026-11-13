'use strict';

const { version, version_name: versionName } = chrome.runtime.getManifest();
document.getElementById('version').textContent = `${versionName || `v${version}`} · Local prototype`;
