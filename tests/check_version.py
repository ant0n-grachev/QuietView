"""Check the machine and display versions in the Chrome manifest."""
import json
from pathlib import Path
import re

manifest_path = Path(__file__).resolve().parents[1] / 'extension' / 'manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
version = manifest['version']
if not re.fullmatch(r'(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*)){2}', version):
    raise SystemExit('Use three numeric Chrome version components without leading zeroes.')

parts = [int(part) for part in version.split('.')]
if not any(parts) or max(parts) > 65535:
    raise SystemExit('Chrome requires at least one nonzero component and a maximum of 65535 per component.')

if manifest.get('version_name') != f'v{version}':
    raise SystemExit('Set manifest version_name to the display form vX.Y.Z.')
print(f'Chrome manifest version and display agree: v{version}')
