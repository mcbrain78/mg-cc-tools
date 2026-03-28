"""Shared AST-based Python symbol extraction.

Used by add-manifest-entry.py (advisory validation) and
verify-references.py (reference integrity checking).

Zero external dependencies -- stdlib only.
"""

import ast


def extract_python_symbols(source):
    """Extract all defined symbol names from Python source via ast.

    Returns a set of names defined at any nesting level:
    FunctionDef, AsyncFunctionDef, ClassDef, Assign Name targets,
    AnnAssign Name targets, Import/ImportFrom aliases.

    Returns empty set on SyntaxError.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname if alias.asname else alias.name)
    return names


def extract_function_signatures(source):
    """Extract function/method parameter names from Python source via ast.

    Returns dict mapping function name -> list of parameter names
    (excluding 'self' and 'cls'). Includes FunctionDef and AsyncFunctionDef
    at any nesting level.

    Returns empty dict on SyntaxError.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    signatures = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = []
            for arg in node.args.args + node.args.kwonlyargs:
                name = arg.arg
                if name not in ("self", "cls"):
                    params.append(name)
            if node.args.kwarg:
                params.append("**")
            signatures[node.name] = params
    return signatures
