# decoct CLI Reference

Complete reference for the `decoct` command-line interface.

## Global Options

| Option | Description |
|---|---|
| `--version` | Print the decoct version (`0.1.0`) and exit. |
| `--help` | Show top-level help and exit. |

```
decoct --version
decoct --help
```

Each subcommand also accepts `--help` to show its own usage.

---

## `decoct compress`

```
decoct compress [FILES...] [OPTIONS]
```

Runs the compression pipeline on infrastructure data files, stripping secrets, platform defaults, conformant values, and noise. Outputs compressed YAML.

### FILES Argument

`FILES` accepts zero or more positional arguments. Each argument may be a file path or a directory path.

- **Files**: Processed directly. Format is auto-detected by extension.
- **Directories**: Expanded to all matching files in the directory. Only files with recognised extensions are included: `.yaml`, `.yml`, `.json`, `.ini`, `.conf`, `.cfg`, `.cnf`, `.properties`.
- **Omitted / no arguments**: Reads from stdin (YAML or JSON expected).

When multiple files are processed, each output section is prefixed with a `# --- <filename> ---` header comment.

### Format Auto-Detection

File extension determines the input parser:

| Extension | Parser |
|---|---|
| `.json` | JSON (converted to CommentedMap internally) |
| `.ini`, `.conf`, `.cfg`, `.cnf`, `.properties` | INI / key-value (converted to CommentedMap) |
| `.yaml`, `.yml` (and all others) | YAML round-trip |

### Platform Auto-Detection

When `--schema` is not provided, decoct inspects the document structure and auto-detects the platform. Supported auto-detections:

| Platform | Detection heuristic |
|---|---|
| `docker-compose` | Has `services` key containing a mapping |
| `kubernetes` | Has `apiVersion` and `kind` keys |
| `terraform-state` | Has `terraform_version` and `resources` keys |
| `cloud-init` | Has 2+ keys from `packages`, `runcmd`, `write_files`, `users`, etc. |
| `ansible-playbook` | Top-level list where first item has `hosts` and `tasks`/`roles` |
| `github-actions` | Has `on` and `jobs` keys |
| `traefik` | Has `entryPoints` or (`providers` and `api`/`log`) |
| `prometheus` | Has `scrape_configs` key |

If auto-detection succeeds, the corresponding bundled schema is loaded automatically. If it fails, the pipeline runs without schema-aware passes.

### Options

#### `--schema <PATH_OR_NAME>`

- **Type:** String
- **Default:** Auto-detected from document content
- **Description:** Schema file path or bundled schema name. When a bundled name is given (e.g. `docker-compose`, `kubernetes`), decoct resolves it from bundled schemas. When a file path is given, the schema is loaded from disk. Enables the strip-defaults and emit-classes passes.

```
decoct compress deployment.yaml --schema kubernetes
decoct compress docker-compose.yml --schema ./my-schemas/compose.yaml
```

#### `--assertions <PATH>`

- **Type:** File path (must exist)
- **Default:** None
- **Description:** Path to an assertions file. Enables the strip-conformant, annotate-deviations, and deviation-summary passes.

```
decoct compress docker-compose.yml --assertions company-standards.yaml
```

#### `--profile <PATH_OR_NAME>`

- **Type:** String
- **Default:** None
- **Description:** Profile file path or bundled profile name. A profile bundles references to a schema, assertions, and pass configuration into a single file. When provided, the profile controls the entire pass pipeline -- `--schema` and `--assertions` are ignored.

```
decoct compress docker-compose.yml --profile docker-compose
decoct compress config.yaml --profile ./profiles/custom.yaml
```

#### `--stats`

- **Type:** Flag
- **Default:** Off
- **Description:** Print token statistics to stderr after compression. Shows input tokens, output tokens, tokens saved, and percentage reduction. For multi-file runs, per-file stats are printed followed by an aggregate total.

```
decoct compress deployment.yaml --stats
```

#### `--stats-only`

- **Type:** Flag
- **Default:** Off
- **Description:** Print only token statistics to stderr. Suppresses the compressed YAML output entirely. Useful for measuring compression ratios without generating output.

```
decoct compress deployment.yaml --stats-only
```

#### `-o, --output <PATH>`

- **Type:** File path
- **Default:** None (stdout)
- **Description:** Write compressed output to a file instead of stdout.

```
decoct compress deployment.yaml -o compressed.yaml
```

#### `--show-removed`

- **Type:** Flag
- **Default:** Off
- **Description:** Print details about what each pass stripped. Output goes to stderr. For each pass that removed items, shows the pass name, count of items removed, and per-item details.

```
decoct compress docker-compose.yml --show-removed
```

#### `-r, --recursive`

- **Type:** Flag
- **Default:** Off
- **Description:** When a directory is given as a `FILES` argument, recurse into subdirectories. Without this flag, only top-level files in the directory are processed.

```
decoct compress ./configs/ -r --stats
```

#### `--encoding <NAME>`

- **Type:** String
- **Default:** `cl100k_base`
- **Description:** Tiktoken encoding name used for token counting. Relevant when `--stats` or `--stats-only` is active. Use `o200k_base` for newer OpenAI models.

```
decoct compress deployment.yaml --stats --encoding o200k_base
```

### Examples

Compress a single file with auto-detected schema, printing stats:

```
decoct compress docker-compose.yml --stats
```

Compress from stdin:

```
cat deployment.yaml | decoct compress
kubectl get deployment nginx -o yaml | decoct compress --schema kubernetes
```

Compress with assertions and write to file:

```
decoct compress docker-compose.yml \
  --schema docker-compose \
  --assertions team-standards.yaml \
  -o compressed.yaml \
  --stats
```

Compress all YAML/JSON files in a directory tree:

```
decoct compress ./infra/ -r --stats-only
```

Inspect what was removed without generating output:

```
decoct compress deployment.yaml --stats-only --show-removed
```

---

## `decoct schema learn`

```
decoct schema learn [OPTIONS]
```

Derives a decoct schema from example configuration files and/or documentation using an LLM. The generated schema captures platform defaults so that `strip-defaults` can remove them.

**Requires `decoct[llm]`** (`pip install decoct[llm]`). Uses the Anthropic API and requires the `ANTHROPIC_API_KEY` environment variable.

### Options

#### `-e, --example <PATH>`

- **Type:** File path (must exist). Repeatable.
- **Default:** None
- **Description:** Example configuration files for the target platform. The LLM analyses these to infer default values. Can be specified multiple times.

```
decoct schema learn -e nginx.conf -e nginx-alt.conf
```

#### `-d, --doc <PATH>`

- **Type:** File path (must exist). Repeatable.
- **Default:** None
- **Description:** Documentation files describing the platform's configuration options and their defaults. Can be specified multiple times.

```
decoct schema learn -d nginx-docs.md -e nginx.conf
```

#### `-p, --platform <NAME>`

- **Type:** String
- **Default:** None
- **Description:** Platform name hint provided to the LLM for better context (e.g. `nginx`, `haproxy`, `redis`).

```
decoct schema learn -e redis.conf -p redis
```

#### `-o, --output <PATH>`

- **Type:** File path
- **Default:** None (stdout)
- **Description:** Write the generated schema to a file instead of stdout.

```
decoct schema learn -e example.yaml -o schema.yaml
```

#### `-m, --merge <PATH>`

- **Type:** File path (must exist)
- **Default:** None
- **Description:** Merge the newly generated schema into an existing schema file. The result is written to `--output` or stdout.

```
decoct schema learn -e new-example.yaml -m existing-schema.yaml -o merged-schema.yaml
```

#### `--model <MODEL_ID>`

- **Type:** String
- **Default:** `claude-sonnet-4-20250514`
- **Description:** Anthropic model ID to use for generation.

```
decoct schema learn -e example.yaml --model claude-sonnet-4-20250514
```

### Validation

At least one `--example` or `--doc` must be provided. The command exits with code 1 if neither is given.

### Examples

Generate a schema from example configs:

```
decoct schema learn -e docker-compose.yml -p docker-compose -o docker-compose-schema.yaml
```

Generate from documentation and examples, merging into an existing schema:

```
decoct schema learn \
  -d haproxy-docs.txt \
  -e haproxy.cfg \
  -p haproxy \
  -m existing-schema.yaml \
  -o merged.yaml
```

---

## `decoct assertion learn`

```
decoct assertion learn [OPTIONS]
```

Derives assertions (design standards) from standards documents, example configurations, or a corpus of configuration files using an LLM. Generated assertions can be used by the `strip-conformant` and `annotate-deviations` passes.

**Requires `decoct[llm]`** (`pip install decoct[llm]`). Uses the Anthropic API and requires the `ANTHROPIC_API_KEY` environment variable.

### Options

#### `-s, --standard <PATH>`

- **Type:** File path (must exist). Repeatable.
- **Default:** None
- **Description:** Standards documents (Markdown, plain text, etc.) describing design rules and conventions. Can be specified multiple times.

```
decoct assertion learn -s standards.md
```

#### `-e, --example <PATH>`

- **Type:** File path (must exist). Repeatable.
- **Default:** None
- **Description:** Example configuration files that demonstrate the desired conventions. The LLM infers assertions from patterns in these files. **Mutually exclusive with `--corpus`.**

```
decoct assertion learn -e good-compose.yml -s standards.md
```

#### `-c, --corpus <PATH>`

- **Type:** File path (must exist). Repeatable.
- **Default:** None
- **Description:** Configuration files for cross-file pattern analysis. The LLM analyses commonalities across all corpus files to infer assertions. **Mutually exclusive with `--example`.** Can be specified multiple times.

```
decoct assertion learn -c service-a.yml -c service-b.yml -c service-c.yml
```

#### `-p, --platform <NAME>`

- **Type:** String
- **Default:** None
- **Description:** Platform name hint (e.g. `docker-compose`, `kubernetes`) provided to the LLM for context.

```
decoct assertion learn -s standards.md -p kubernetes
```

#### `-o, --output <PATH>`

- **Type:** File path
- **Default:** None (stdout)
- **Description:** Write the generated assertions to a file instead of stdout.

```
decoct assertion learn -s standards.md -o assertions.yaml
```

#### `-m, --merge <PATH>`

- **Type:** File path (must exist)
- **Default:** None
- **Description:** Merge newly generated assertions into an existing assertions file. The result is written to `--output` or stdout.

```
decoct assertion learn -s standards.md -m existing.yaml -o merged.yaml
```

#### `--model <MODEL_ID>`

- **Type:** String
- **Default:** `claude-sonnet-4-20250514`
- **Description:** Anthropic model ID to use for generation.

### Validation

- At least one of `--standard`, `--example`, or `--corpus` must be provided. The command exits with code 1 if none are given.
- `--corpus` and `--example` are mutually exclusive. The command exits with code 1 if both are given.

### Examples

Derive assertions from a standards document:

```
decoct assertion learn -s team-standards.md -p docker-compose -o assertions.yaml
```

Derive assertions from example configs and a standards doc:

```
decoct assertion learn \
  -s standards.md \
  -e reference-compose.yml \
  -p docker-compose \
  -o assertions.yaml
```

Learn assertions from a corpus of production configs:

```
decoct assertion learn \
  -c configs/service-a.yml \
  -c configs/service-b.yml \
  -c configs/service-c.yml \
  -p docker-compose \
  -o corpus-assertions.yaml
```

Merge new assertions into an existing file:

```
decoct assertion learn \
  -s updated-standards.md \
  -m assertions.yaml \
  -o assertions.yaml
```

---

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | Error: missing input, invalid schema, parse error, missing required options, LLM API error, merge failure, or any other runtime error. |

---

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key. Required for `schema learn` and `assertion learn` commands. Not used by `compress`. |

---

## stdin / stdout / stderr Behavior

### `decoct compress`

| Stream | Content |
|---|---|
| **stdin** | Input data when no `FILES` arguments are provided. |
| **stdout** | Compressed YAML output (suppressed when `--stats-only` is active, redirected when `-o` is used). |
| **stderr** | Token statistics (`--stats`, `--stats-only`), removal details (`--show-removed`), error messages. |

### `decoct schema learn` / `decoct assertion learn`

| Stream | Content |
|---|---|
| **stdout** | Generated schema or assertions YAML (when `-o` is not used). |
| **stderr** | Progress messages ("Analysing input files..."), merge confirmations, output path confirmations, error messages. |

This separation allows piping compressed output or generated schemas directly to other tools while keeping diagnostics visible in the terminal:

```
decoct compress deployment.yaml --stats | pbcopy
decoct schema learn -e example.yaml | decoct compress config.yaml --schema /dev/stdin
```
