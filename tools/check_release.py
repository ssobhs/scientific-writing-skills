"""Check portable skill packaging; does not score scientific writing quality."""
from pathlib import Path
import ast
import re
import sys
from urllib.parse import unquote, urlsplit


def main():
    root = Path(__file__).resolve().parents[1]
    errors = []
    entries = sorted((root / 'skills').glob('*/SKILL.md'))
    if not entries:
        errors.append('No skill entrypoints found')
    names = set()
    for entry in entries:
        body = entry.read_text(encoding='utf-8-sig')
        front = re.match(r'\A---\s*\n(.*?)\n---(?:\n|$)', body, re.S)
        if not front:
            errors.append(f'{entry.relative_to(root)}: missing frontmatter')
            continue
        fields = dict(re.findall(r'^(name|description):\s*(.+)$', front[1], re.M))
        name = fields.get('name', '').strip('\"\'')
        if name != entry.parent.name or name in names:
            errors.append(f'{entry.relative_to(root)}: invalid or duplicate name')
        if not fields.get('description'):
            errors.append(f'{entry.relative_to(root)}: missing description')
        names.add(name)

    links = scripts = 0
    for file in root.rglob('*'):
        relative = file.relative_to(root)
        if any(part in {'.git', '.venv', 'venv', '__pycache__', 'output', 'scratch'} for part in relative.parts):
            continue
        if not file.is_file():
            continue
        if file.suffix == '.py':
            try:
                ast.parse(file.read_text(encoding='utf-8-sig'), filename=str(relative))
                scripts += 1
            except SyntaxError as exc:
                errors.append(f'{relative}: {exc}')
        if file.suffix != '.md':
            continue
        body = file.read_text(encoding='utf-8-sig')
        # Skip fenced code examples; inspect actual inline Markdown links.
        body = re.sub(r'```.*?```', '', body, flags=re.S)
        for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', body):
            target = target.strip().strip('<>')
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith('#'):
                continue
            resolved = (file.parent / unquote(parsed.path)).resolve()
            if not resolved.is_relative_to(root) or not resolved.exists():
                errors.append(f'{relative}: missing or external local link {target}')
            links += 1
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print(f'PASS: {len(entries)} skills, {scripts} Python syntax checks, {links} local links')
    print('Scope: package structure only; no model evaluation, Word rendering, or remote-link check.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
