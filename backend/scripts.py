"""Static script declarations and diagnostics. Saving/importing never executes code."""
import ast
import hashlib
import math

from pydantic import ValidationError

from .models import ScriptAnalysis, ScriptDiagnostic, ScriptParameter, StrategyDefinition


def validate_parameters(definitions: dict[str, ScriptParameter], supplied: dict) -> dict:
    unknown = set(supplied)-set(definitions)
    if unknown:
        raise ValueError('Unknown script parameters: '+', '.join(sorted(unknown)))
    result = {}
    for key, spec in definitions.items():
        value = supplied.get(key, spec.default)
        if spec.type in ('int', 'float'):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{key} must be a finite {spec.type}')
            if spec.type == 'int' and value != int(value):
                raise ValueError(f'{key} must be an integer')
            if (spec.minimum is not None and value < spec.minimum) or (spec.maximum is not None and value > spec.maximum):
                raise ValueError(f'{key} is outside the declared range')
            value = int(value) if spec.type == 'int' else float(value)
        elif spec.type == 'bool' and not isinstance(value, bool):
            raise ValueError(f'{key} must be a boolean')
        elif spec.type == 'str' and not isinstance(value, str):
            raise ValueError(f'{key} must be text')
        if spec.choices and value not in spec.choices:
            raise ValueError(f'{key} must be one of its declared choices')
        result[key] = value
    return result


def analyze_script(script: StrategyDefinition) -> ScriptAnalysis:
    diagnostics, definitions, hooks = [], {}, []
    try:
        tree = ast.parse(script.source, filename=script.name+'.py')
    except SyntaxError as exc:
        return ScriptAnalysis(valid=False, script_hash=hashlib.sha256(script.source.encode()).hexdigest(),
            diagnostics=[ScriptDiagnostic(line=exc.lineno or 1, column=exc.offset or 1, severity='error', message=exc.msg)],
            parameters={}, hooks=[])
    declarations = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            hooks.append(node.name)
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'PARAMETERS' for target in node.targets):
            declarations.append(node)
            try:
                value = ast.literal_eval(node.value)
                if not isinstance(value, dict):
                    raise TypeError('PARAMETERS must be a literal dictionary')
                for key, definition in value.items():
                    if not isinstance(key, str) or not key.isidentifier():
                        raise ValueError('Parameter names must be identifiers')
                    definitions[key] = ScriptParameter.model_validate(definition)
                validate_parameters(definitions, {})
            except (ValueError, TypeError, ValidationError) as exc:
                diagnostics.append(ScriptDiagnostic(line=node.lineno, column=node.col_offset+1, severity='error', message=str(exc)))
    if len(declarations) > 1:
        diagnostics.append(ScriptDiagnostic(line=declarations[-1].lineno, column=1, severity='error', message='Declare PARAMETERS once at module level'))
    required = 'on_bars' if script.kind == 'strategy' else 'calculate'
    if required not in hooks:
        diagnostics.append(ScriptDiagnostic(line=1, column=1, severity='error', message=f'Define {required}(ctx'+(', bars)' if script.kind == 'strategy' else ')')+' as a synchronous function'))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [item.name for item in node.names] if isinstance(node, ast.Import) else [node.module or '']
            if any(name.split('.')[0] in ('time', 'datetime', 'random') for name in names):
                diagnostics.append(ScriptDiagnostic(line=node.lineno, column=node.col_offset+1, severity='warning',
                    message='Use ctx.clock and ctx.random for reproducible strategy time and randomness'))
    return ScriptAnalysis(valid=not any(d.severity == 'error' for d in diagnostics),
        script_hash=hashlib.sha256(script.source.encode()).hexdigest(), diagnostics=diagnostics,
        parameters=definitions, hooks=hooks)
