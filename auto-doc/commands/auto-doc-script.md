---
name: mg:auto-doc-script
description: Generate a README for a standalone script or small tool directory
allowed-tools: Bash, Read, Write, Glob, Grep
---

# Auto-Doc Script

You generate a `README.AUTO-DOC.md` for a standalone script or small tool directory. You read the source code, extract the CLI interface and prerequisites, then write a structured README following the SCRIPT_README template. This is a lightweight, single-pass command -- no scan phase, no audience segmentation, no verify step.

## Session Context

Run the session context emitter for permission auto-approval:
```
python3 {MG_INSTALL_EMIT_CONTEXT_SCRIPT} AUTO-DOC
```
If the script is not found, continue — permissions will require manual approval.

## Arguments

`$ARGUMENTS` contains the target path and an optional `--output <path>` flag.

**Example usages:**

```
/mg:auto-doc-script scripts/convert.py
/mg:auto-doc-script tools/data-pipeline/
/mg:auto-doc-script scripts/convert.py --output docs/convert-readme.md
```

## Process

### Step 1: Parse and Validate Arguments

1. Split `$ARGUMENTS` on whitespace.
2. If empty, show the following usage message and stop:
   ```
   Usage: /mg:auto-doc-script <path-to-script-or-directory> [--output <path>]

   Examples:
     /mg:auto-doc-script scripts/convert.py
     /mg:auto-doc-script tools/data-pipeline/
     /mg:auto-doc-script scripts/convert.py --output docs/convert-readme.md
   ```
3. If `--output` is present in the arguments:
   - The token immediately after `--output` is the output path.
   - Everything before `--output` is the target path.
   - If `--output` is the last token with no value after it, show error and stop:
     ```
     Error: --output requires a path argument
     ```
4. If `--output` is not present, the entire argument string is the target path.
5. Verify the target path exists using Bash `test -e`. If it does not exist, show error and stop:
   ```
   Error: path does not exist: {path}
   ```
6. If `--output` was specified, verify its parent directory exists using Bash `test -d` on the dirname. If the parent directory does not exist, show error and stop:
   ```
   Error: output directory does not exist: {parent}
   ```

### Step 2: Determine Mode

- If target is a file (`test -f`): **single-file mode**.
- If target is a directory (`test -d`): **directory mode**.
  - Count source files with extensions: `.py`, `.js`, `.ts`, `.sh`, `.go`, `.rs`, `.rb`, `.pl`, `.lua`, `.java`, `.kt`, `.swift`, `.c`, `.cpp`, `.h`
  - Exclude from count: test files (`test_*`, `*_test.*`, `*_spec.*`), `__init__.py`, dotfiles, and anything inside `node_modules/`, `__pycache__/`, `.git/` directories.
  - If zero source files found, show error and stop:
    ```
    Error: no source files found in {path}
    ```
  - If more than 20 source files found, print a warning and continue:
    ```
    Warning: {N} source files found. Consider the full /mg:auto-doc pipeline for large projects. Continuing...
    ```

### Step 3: Determine Output Path

- If `--output` was specified: use that path exactly.
- If single-file mode: `{target_dir}/README.AUTO-DOC.md` (same directory as the script).
- If directory mode: `{target_dir}/README.AUTO-DOC.md` (inside the target directory).

### Step 4: Read and Analyze Target

**Single-file mode:**

Read the script file. Extract:
- **CLI interface:** argparse, click, typer, getopts, commander, optparse, or any argument parsing pattern.
- **Purpose:** module-level docstrings, top-of-file comments, description strings passed to argument parsers.
- **Prerequisites:** imports that require installation (non-stdlib packages), env var reads (`os.environ`, `os.getenv`, `$ENV_VAR`, `process.env`), language runtime requirements.
- **File/network access:** file reads/writes, HTTP calls, database connections, socket operations.
- **Exit codes:** explicit `sys.exit()`, `exit()`, or process exit patterns.

**Directory mode:**

1. Use Glob to find all source files matching the extensions from Step 2.
2. Identify entry points: `__main__.py`, `cli.py`, `main.py`, `index.js`, `index.ts`, files with `argparse`/`click`/`typer`/`getopts` imports, files with `if __name__` blocks, shell scripts with getopts or argument parsing.
3. Read entry points fully.
4. Read supporting modules to understand structure, but focus documentation on entry points and their direct imports.
5. If multiple independent entry points exist: prepare per-script sections with their own Usage, Examples, and Options subsections.

### Step 5: Read Template

Read `{MG_INSTALL_TEMPLATES_DIR}/SCRIPT_README.template.md` for section structure and annotation guidance.

- Use the template's `<!-- PURPOSE -->` annotations to understand what each section should contain.
- Use the template's `<!-- EXAMPLE -->` annotations as quality reference for content density and format.

### Step 6: Generate README.AUTO-DOC.md

Write the file to the output path determined in Step 3.

**Content rules:**

1. Follow the template's section structure: Title, Prerequisites, Usage, Options, Examples, Output, How It Works, Notes.
2. **Omit any section that would only contain "None", "N/A", or trivially empty content.** If a section has nothing substantive, skip it entirely. Do not include empty sections.
3. For **directory mode with multiple entry points**:
   - Add a summary table after the title listing all entry points (script name, one-line description, common invocation).
   - Create per-script sections (`## script_name.py`) with their own Usage, Examples, and Options subsections.
   - Add an Architecture note showing directory structure and what supporting files do.
   - Order per-script sections by importance (main entry point first, then helpers/utilities).
4. For **examples**: use ` ```console ` fenced code blocks with `$` prompt prefix for commands and plain text for output. Examples must be fully runnable with realistic arguments and expected output shown.
5. Do not include `<!-- PURPOSE -->`, `<!-- EXAMPLE -->`, or `<!-- OPTIONAL -->` annotation comments in the generated output. Those are template guidance, not output content.

After writing the file, print:
```
Generated: {output_path}
```

## Important Principles

- **Full overwrite on each run.** The filename `README.AUTO-DOC.md` signals "auto-generated." There is no merge or preservation logic. Each run produces a complete replacement.
- **One generic prompt handles all languages.** Do not add language-specific extraction instructions. The LLM reads any language's CLI patterns (argparse, click, getopts, commander, etc.) without specialized rules.
- **Omit empty sections.** If a section would contain only "None" or "N/A", delete it entirely from the output.
- **Quality bar:** "A year from now, someone should be able to open the README and use the script without reading the source."
- **Use `{MG_INSTALL_TEMPLATES_DIR}` placeholder for the template path** -- resolved by install.sh at install time.
- **Do not modify install.sh, templates, or any other auto-doc file** from within this command.
