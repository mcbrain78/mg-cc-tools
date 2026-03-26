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
