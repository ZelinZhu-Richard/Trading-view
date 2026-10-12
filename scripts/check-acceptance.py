"""Check source coverage and local evidence links; does not infer feature completion."""
import hashlib
import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parent.parent
report = json.loads((root / 'docs/requirements.json').read_text())
source = (root / report['source']).read_bytes()
assert hashlib.sha256(source).hexdigest() == report['source_sha256'], 'Specification changed; review the mapping'
lines = source.decode().splitlines()
expected = {n for n, line in enumerate(lines, 1) if line.strip() and not line.startswith('#')
            and not (line.startswith('|') and set(line) <= set('|- :'))}
counts = Counter()
identities = set()
for item in report['requirements']:
    assert item['id'] not in identities, f'Duplicate ID: {item["id"]}'
    identities.add(item['id'])
    line = item['source_line']
    counts[line] += 1
    assert item['requirement'] == lines[line - 1], f'Source mismatch at {item["id"]}'
    assert item['status'] in report['status_definitions'], item['id']
    assert item['evidence'], f'Missing evidence: {item["id"]}'
    if item['status'] == 'partial':
        assert item['notes'], f'Unexplained partial: {item["id"]}'
    for evidence in item['evidence']:
        assert (root / evidence).exists(), f'Missing evidence: {evidence}'
assert set(counts) == expected, f'Missing lines: {expected - set(counts)}; extra lines: {set(counts) - expected}'
assert all(count == 1 for count in counts.values()), 'Duplicate source rows'
print(json.dumps({'status': 'passed', 'mapped_rows': len(identities),
                  'source_sha256': report['source_sha256'],
                  'requirement_statuses': dict(Counter(i['status'] for i in report['requirements'])),
                  'scope': 'Source coverage, exact text and existing evidence paths; not whole-goal acceptance'}, indent=2))
