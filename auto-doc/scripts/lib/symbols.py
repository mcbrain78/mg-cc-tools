"""Shared AST-based Python symbol extraction.

Used by add-manifest-entry.py (advisory validation),
verify-references.py (reference integrity checking), and
verify-xml-refs.py (deterministic XML ref verification).

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


def extract_sqlalchemy_models(source):
    """Extract SQLAlchemy model metadata from Python source.

    Detects classes with __tablename__ and Column() definitions.
    Returns dict mapping table_name -> {"schema": str, "columns": [str], "class_name": str}.
    Schema comes from __table_args__ {"schema": "..."} if present.

    Returns empty dict on SyntaxError.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    models = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        table_name = None
        schema_name = ""
        columns = []

        for item in node.body:
            # __tablename__ = "..."
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "__tablename__":
                        if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                            table_name = item.value.value

                    # __table_args__ = {"schema": "..."}  or  (... {"schema": "..."})
                    if isinstance(target, ast.Name) and target.id == "__table_args__":
                        schema_name = _extract_schema_from_table_args(item.value)

            # column = Column(...)  or  column: Mapped[...] = mapped_column(...)
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        if _is_column_call(item.value):
                            columns.append(target.id)
            elif isinstance(item, ast.AnnAssign):
                if isinstance(item.target, ast.Name) and item.value is not None:
                    if _is_column_call(item.value):
                        columns.append(item.target.id)

        if table_name is not None:
            models[table_name] = {
                "schema": schema_name,
                "columns": columns,
                "class_name": node.name,
            }

    return models


def _extract_schema_from_table_args(node):
    """Extract schema string from __table_args__ value."""
    # Dict literal: {"schema": "name"}
    if isinstance(node, ast.Dict):
        return _extract_schema_from_dict(node)
    # Tuple: ({...}, {"schema": "name"})  — last element is often a dict
    if isinstance(node, ast.Tuple):
        for elt in reversed(node.elts):
            if isinstance(elt, ast.Dict):
                result = _extract_schema_from_dict(elt)
                if result:
                    return result
    return ""


def _extract_schema_from_dict(dict_node):
    """Extract 'schema' value from a dict literal node."""
    for key, value in zip(dict_node.keys, dict_node.values):
        if (isinstance(key, ast.Constant)
                and key.value == "schema"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)):
            return value.value
    return ""


def _is_column_call(node):
    """Check if a node is a Column() or mapped_column() call."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in ("Column", "mapped_column")
    if isinstance(func, ast.Attribute):
        return func.attr in ("Column", "mapped_column")
    return False


def extract_class_attributes(source, class_name):
    """Extract attribute names defined on a specific class.

    Includes:
    - Class-level assignments: x = ...
    - Annotated assignments: x: type = ...
    - Annotated declarations: x: type (no value)
    - Method definitions: def name(self): / async def name(self):

    Returns a set of attribute names. Returns empty set on SyntaxError
    or if class not found.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            attrs = set()
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            attrs.add(target.id)
                elif isinstance(item, ast.AnnAssign):
                    if isinstance(item.target, ast.Name):
                        attrs.add(item.target.id)
                elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    attrs.add(item.name)
            return attrs

    return set()


def extract_enum_values(source, enum_class):
    """Extract enum member values from a specific class.

    Handles:
    - NAME = "value"  (string literal)
    - NAME = value    (any constant)
    - auto() values   (returns member name as value)

    Returns dict mapping member_name -> value (as string).
    Returns empty dict on SyntaxError or if class not found.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == enum_class:
            members = {}
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            val = _extract_constant_value(item.value)
                            if val is not None:
                                members[target.id] = str(val)
                            elif _is_auto_call(item.value):
                                members[target.id] = target.id
            return members

    return {}


def extract_literal_values(source, name):
    """Extract string values from a Literal type alias assignment.

    Matches: Name = Literal["a", "b", "c"]  and  Name = typing.Literal["a", "b"]
    Returns set of string values, or empty set if not found.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                if isinstance(node.value, ast.Subscript):
                    func = node.value.value
                    # Match Literal or typing.Literal
                    is_literal = (
                        (isinstance(func, ast.Name) and func.id == "Literal")
                        or (isinstance(func, ast.Attribute) and func.attr == "Literal")
                    )
                    if is_literal:
                        return _extract_literal_strings(node.value.slice)
    return set()


def _extract_literal_strings(node):
    """Extract string constants from a Literal subscript slice."""
    values = set()
    if isinstance(node, ast.Tuple):
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                values.add(elt.value)
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        values.add(node.value)
    return values


def _extract_constant_value(node):
    """Extract constant value from an AST node, or None."""
    if isinstance(node, ast.Constant):
        return node.value
    return None


def _is_auto_call(node):
    """Check if a node is auto() call."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id == "auto"
    return False


def extract_decorated_functions(source, decorator):
    """Extract names of functions/methods decorated with a specific decorator.

    Matches decorators by name (e.g., "flow" matches @flow and @flow(...)).

    Returns list of function names. Returns empty list on SyntaxError.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    names = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                dec_name = None
                if isinstance(dec, ast.Name):
                    dec_name = dec.id
                elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                    dec_name = dec.func.id
                elif isinstance(dec, ast.Attribute):
                    dec_name = dec.attr
                elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    dec_name = dec.func.attr
                if dec_name == decorator:
                    names.append(node.name)
                    break
    return names
