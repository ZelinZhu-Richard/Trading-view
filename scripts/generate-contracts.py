"""Generate TypeScript from Pydantic's serialization schema; unsupported nodes fail visibly."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pydantic import BaseModel

from backend import models, providers, research_models

root = Path(__file__).resolve().parent.parent
definitions = {}
for module in (models, providers, research_models):
    for name, model in vars(module).items():
        if isinstance(model, type) and issubclass(model, BaseModel) and model.__module__ == module.__name__:
            schema = model.model_json_schema(mode='serialization')
            definitions.update(schema.pop('$defs', {}))
            definitions[name] = schema


def translate(schema):
    if '$ref' in schema:
        return schema['$ref'].split('/')[-1]
    if 'const' in schema:
        return json.dumps(schema['const'])
    if 'enum' in schema:
        return ' | '.join(json.dumps(v) for v in schema['enum'])
    if 'anyOf' in schema:
        return '(' + ' | '.join(translate(v) for v in schema['anyOf']) + ')'
    kind = schema.get('type')
    if kind == 'array':
        return f'Array<{translate(schema["items"])}>'
    if kind == 'object':
        if 'properties' in schema:
            return '{\n' + '\n'.join(f'  {json.dumps(k)}{"" if k in schema.get("required", []) else "?"}: {translate(v)};' for k, v in schema['properties'].items()) + '\n}'
        additional = schema.get('additionalProperties', {})
        return 'Record<string, ' + ('unknown' if isinstance(additional, bool) else translate(additional)) + '>'
    if kind in ('integer', 'number'):
        return 'number'
    if kind in ('string', 'boolean', 'null'):
        return kind
    if not schema:
        return 'unknown'
    raise ValueError(f'Unsupported contract schema: {schema}')


out = '// Generated from backend/models.py. Run npm run contracts; do not edit.\n\n'
out += '\n\n'.join(f'export type {k} = {translate(v)};' for k, v in sorted(definitions.items())) + '\n'
(root / 'src').mkdir(exist_ok=True)
(root / 'src' / 'contracts.ts').write_text(out)
(root / 'docs' / 'contracts.schema.json').write_text(json.dumps(definitions, indent=2) + '\n')
print(f'Generated {len(definitions)} contract types')
