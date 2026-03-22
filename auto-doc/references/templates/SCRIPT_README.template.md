<!-- DIATAXIS: how-to + reference -->
<!-- AUDIENCE: all -->

<!-- DIRECTORY MODE: When documenting a multi-file tool directory, adapt this
     template as follows:
     - Add a summary table after the title listing all entry points
       (script name, one-line description, common invocation)
     - Create per-script sections (## script_name.py) with their own
       Usage/Examples/Options subsections
     - Add a brief "Architecture" paragraph or bullet list showing directory
       structure and what supporting files do
     - Order per-script sections by importance (main entry point first) -->

# {Script/Tool Name}
<!-- PURPOSE: One-line description of what the script does, who would use it,
     and the core problem it solves. The title should be the script filename
     or tool directory name. The description should be specific enough that a
     reader can decide in 5 seconds whether this is the script they need. -->
<!-- EXAMPLE:
# convert.py

Convert CSV files to JSON, with support for nested field mappings and custom
delimiters. Reads from a file or stdin, writes to a file or stdout.
-->

## Prerequisites
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Language runtime, packages, environment variables, file access,
     or system dependencies needed before running the script. Only include
     items beyond the language's standard library. If the script has no
     external dependencies, delete this section entirely. -->
<!-- EXAMPLE:
- Python 3.8+
- `pyyaml` package (`pip install pyyaml`) -- only needed for YAML output format
- `DATA_DIR` environment variable set to the input directory path
-->

## Usage
<!-- PURPOSE: The primary invocation pattern with all required arguments.
     This is the first thing a user tries. Show the most common way to run
     the script with a realistic example that actually works. -->
<!-- EXAMPLE:
```console
$ python3 convert.py --input data.csv --format json
```
-->

## Options
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Complete reference of all flags and arguments with types,
     defaults, and descriptions. Users come here to find the exact flag
     they need. If the script has no flags (just positional args covered
     in Usage), delete this section. -->
<!-- EXAMPLE:
| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--input`, `-i` | `str` | -- (required) | Path to the input CSV file |
| `--format`, `-f` | `str` | `"json"` | Output format: `json`, `yaml`, `csv` |
| `--output`, `-o` | `str` | stdout | Path to write the output file |
| `--delimiter` | `str` | `","` | CSV field delimiter |
| `--nested` | flag | off | Enable nested field mapping (dot notation in headers) |
| `--pretty` | flag | off | Pretty-print JSON output with 2-space indent |
-->

## Examples
<!-- PURPOSE: Fully runnable examples with realistic arguments AND expected
     output. Each example should demonstrate a distinct use case. Use console
     fenced code blocks with $ prompt prefix for commands and plain text for
     output. A reader should be able to copy-paste these and get the shown
     results. -->
<!-- EXAMPLE:
### Basic conversion

```console
$ python3 convert.py --input employees.csv --format json
[
  {"name": "Alice", "department": "Engineering", "level": 5},
  {"name": "Bob", "department": "Marketing", "level": 3}
]
```

### With nested field mapping

```console
$ python3 convert.py --input config.csv --format json --nested
[
  {"database": {"host": "localhost", "port": 5432}},
  {"database": {"host": "prod-db", "port": 5432}}
]
```

### Empty input handling

```console
$ python3 convert.py --input empty.csv --format json
[]
```
-->

## Output
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: What the script produces: files created, stdout format, side
     effects (database writes, network calls), and exit codes. Users need
     to know what to expect after running the script and where to find
     the results. -->
<!-- EXAMPLE:
- **stdout** (default): JSON array, one object per CSV row
- **file** (with `--output`): writes to the specified path, overwrites if exists
- **Exit code 0**: success
- **Exit code 1**: input file not found or unreadable
- **Exit code 2**: invalid output format specified
-->

## How It Works
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Brief explanation of internal logic for non-trivial scripts.
     Helps users understand behavior in edge cases and debug unexpected
     output. Keep to 3-5 bullet points describing the processing steps.
     Skip this section for simple scripts where the Usage section tells
     the whole story. -->
<!-- EXAMPLE:
1. Reads the CSV file and auto-detects the delimiter if `--delimiter` is not set
2. Parses headers from the first row; if `--nested` is set, splits dotted names into nested objects
3. Converts each row to a dictionary, coercing numeric strings to numbers
4. Serializes to the requested format and writes to stdout or the output file
-->

## Notes
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Gotchas, limitations, related scripts, or version history that
     do not fit in the sections above. Users who hit unexpected behavior
     check here for known issues. -->
<!-- EXAMPLE:
- Maximum file size: limited by available memory (entire file is loaded at once)
- Unicode: input must be UTF-8 encoded; other encodings produce a decode error
- Related: `validate.py` checks CSV structure before conversion
- Added in v1.2: `--nested` flag for dotted field names
-->
