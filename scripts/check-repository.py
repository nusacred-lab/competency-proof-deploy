"""Validate syntax, documentation links and repository hygiene without deployment."""
import ast
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / 'scripts').glob('*.py'):
    ast.parse(path.read_text(), filename=str(path))
for path in [ROOT / 'README.md', *(ROOT / 'docs').glob('*.md')]:
    text = path.read_text()
    if text.count('```') % 2:
        raise SystemExit('Unclosed code fence: ' + path.name)
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', text):
        if not target.startswith(('https://', 'http://', '#', 'mailto:')):
            if not (path.parent / target.split('#')[0]).exists():
                raise SystemExit('Broken local link: ' + target)
tracked = subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines()
for name in tracked:
    if any(part in {'runtime', 'output', '__pycache__', 'signing'} for part in Path(name).parts):
        raise SystemExit('Private/generated path tracked: ' + name)
    if name == 'config/reviewer.json' or Path(name).suffix in {'.p12', '.jks', '.apk', '.pem'}:
        raise SystemExit('Private configuration/key/build tracked: ' + name)
for path in (ROOT / '.github/workflows').glob('*.yml'):
    text = path.read_text()
    for action in re.findall(r'uses:\s*([^\s#]+)', text):
        if not re.fullmatch(r'[\w.-]+/[\w./-]+@[a-f0-9]{40}', action):
            raise SystemExit('Unpinned action: ' + action)
    for forbidden in ('pull_request_target', 'secrets.', 'write-all', 'self-hosted'):
        if forbidden in text: raise SystemExit('Privileged workflow pattern: ' + forbidden)
print('PASS: syntax, local documentation links, workflow pins and private-file policy')
