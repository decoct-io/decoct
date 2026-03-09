# Input Format Handling

decoct accepts infrastructure configuration in several formats and normalises
everything to ruamel.yaml round-trip types (`CommentedMap` / `CommentedSeq`)
before running the compression pipeline. Output is always YAML.

---

## YAML Input

YAML is the native format. Files are loaded with `ruamel.yaml` in round-trip
mode (`YAML(typ='rt')`), so comments, key ordering, and flow style are
preserved through the pipeline until a pass explicitly removes them (e.g. the
`strip-comments` pass).

| Detail | Value |
|---|---|
| Extensions | `.yaml`, `.yml` |
| Internal types | `CommentedMap`, `CommentedSeq` |
| Comment handling | Preserved until `strip-comments` runs |
| Multi-document | Single document per file |

When reading from **stdin** (`-` or no file argument), decoct always treats the
input as YAML -- no format auto-detection is performed.

---

## JSON Input

JSON files are auto-detected by the `.json` extension. The file is parsed with
Python's `json` module and then recursively converted to round-trip types via
`json_to_commented_map()`:

- `dict` becomes `CommentedMap`
- `list` becomes `CommentedSeq`
- Scalar types (`int`, `float`, `bool`, `None`) pass through unchanged

Because JSON has no comment syntax, there is nothing for `strip-comments` to
remove. The final output is still YAML, so JSON input effectively undergoes a
JSON-to-YAML conversion as part of compression.

| Detail | Value |
|---|---|
| Extension | `.json` |
| Conversion function | `json_to_commented_map()` in `formats.py` |
| Scalar preservation | `int`, `float`, `bool`, `null` retained |
| Output format | YAML |

This works well with Terraform state files, cloud provider API responses, and
any other JSON-based infrastructure data.

---

## INI / Config File Input

decoct handles INI-style and flat key=value configuration files. Format
detection is by extension.

| Detail | Value |
|---|---|
| Extensions | `.ini`, `.conf`, `.cfg`, `.cnf`, `.properties` |
| Conversion function | `ini_to_commented_map()` in `formats.py` |

### Two parsing modes

The parser inspects the raw text for `[section]` headers to decide which mode
to use:

**Sectioned INI** (files with `[section]` headers):

- Parsed with Python's `configparser` (interpolation disabled).
- Produces a nested `CommentedMap`: each section name maps to a `CommentedMap`
  of its keys and values.

**Flat key=value** (no section headers):

- Parsed line-by-line with a custom parser.
- Lines starting with `#` or `;` are treated as comments and skipped.
- Blank lines are skipped.
- Lines without `=` are skipped.
- Produces a flat `CommentedMap` of key-value pairs.

### Value type coercion

All values start as strings. The `_coerce_ini_value()` function converts them
to native types in this order:

| Input string | Resulting type |
|---|---|
| `true`, `yes`, `on` (case-insensitive) | `True` (bool) |
| `false`, `no`, `off` (case-insensitive) | `False` (bool) |
| Valid integer (e.g. `8080`) | `int` |
| Valid float (e.g. `3.14`) | `float` |
| Everything else | `str` |

---

## Format Auto-Detection

Format is determined by file extension in `detect_format()`. The mapping is:

| Extension | Detected format |
|---|---|
| `.json` | `json` |
| `.ini` | `ini` |
| `.conf` | `ini` |
| `.cfg` | `ini` |
| `.cnf` | `ini` |
| `.properties` | `ini` |
| `.yaml` | `yaml` |
| `.yml` | `yaml` |
| Anything else | `yaml` (default) |

The CLI's `_expand_sources()` function, which resolves directories to files,
only picks up files with extensions in `_INPUT_EXTENSIONS`:
`.yaml`, `.yml`, `.json`, `.ini`, `.conf`, `.cfg`, `.cnf`, `.properties`.

---

## Platform Auto-Detection

When `--schema` is not provided, decoct examines the parsed document content to
guess the platform and load the matching bundled schema automatically. This
happens in `detect_platform()` in `formats.py`.

Detection is tried in the following order (first match wins):

| Platform | Schema name | Detection rule |
|---|---|---|
| Ansible playbook | `ansible-playbook` | Document is a list whose first item is a dict containing `hosts` and either `tasks` or `roles` |
| Docker Compose | `docker-compose` | Top-level `services` key with a dict value |
| Terraform state | `terraform-state` | Has both `terraform_version` and `resources` keys |
| cloud-init | `cloud-init` | At least 2 keys from: `packages`, `runcmd`, `write_files`, `users`, `ssh_authorized_keys`, `growpart`, `ntp` |
| Kubernetes | `kubernetes` | Has both `apiVersion` and `kind` keys |
| GitHub Actions | `github-actions` | Has both `on` and `jobs` keys |
| Traefik | `traefik` | Has `entryPoints`, or has `providers` together with `api` or `log` |
| Prometheus | `prometheus` | Has `scrape_configs` key |

If none of the rules match, `detect_platform()` returns `None` and the pipeline
runs without a schema (generic passes only).

Note: Ansible detection is checked first because it requires the document to be
a list, which is tested before the dict-based checks.

---

## Limitations

- **XML** is not yet supported (planned for a future phase).
- **CLI output** normalisation is not yet supported (planned for a future phase).
- **INI comments** (`#` and `;` lines) are discarded during parsing -- they do
  not survive into the `CommentedMap`.
- **Flat key=value** format does not support multi-line values.
- **stdin** is always treated as YAML -- no extension-based format detection is
  possible.

---

## Examples

### Compressing a YAML file (Docker Compose)

```bash
decoct compress docker-compose.yml --stats
```

The platform is auto-detected as `docker-compose` because the file contains a
top-level `services` key. The bundled Docker Compose schema is loaded
automatically, and platform defaults are stripped.

### Compressing a JSON file (Terraform state)

```bash
decoct compress terraform.tfstate --stats
```

The `.json` extension is not present here, but if the file were named
`state.json`, it would be auto-detected as JSON. Regardless of extension, the
content is checked for `terraform_version` + `resources` and the
`terraform-state` schema is loaded.

For an explicitly JSON file:

```bash
decoct compress state.json --stats
```

The file is parsed as JSON, converted to `CommentedMap`/`CommentedSeq`, and
output as compressed YAML.

### Compressing an INI file

Given a `my.cnf` MySQL configuration:

```ini
[mysqld]
port = 3306
max_connections = 151
innodb_buffer_pool_size = 128M

[client]
port = 3306
socket = /var/run/mysqld/mysqld.sock
```

```bash
decoct compress my.cnf --stats
```

This is parsed as sectioned INI (because `[mysqld]` and `[client]` headers are
present) and converted to a nested structure:

```yaml
mysqld:
  port: 3306
  max_connections: 151
  innodb_buffer_pool_size: 128M
client:
  port: 3306
  socket: /var/run/mysqld/mysqld.sock
```

### Compressing a flat key=value file

Given a `server.properties` file:

```properties
# Minecraft server properties
server-port=25565
enable-command-block=false
max-players=20
view-distance=10
```

```bash
decoct compress server.properties --stats
```

Parsed as flat key=value (no section headers) and output as:

```yaml
server-port: 25565
enable-command-block: false
max-players: 20
view-distance: 10
```

### Processing from stdin

```bash
kubectl get deployment myapp -o yaml | decoct compress - --schema kubernetes --stats
```

stdin is always parsed as YAML. Platform auto-detection still works on the
parsed content, but here `--schema kubernetes` is passed explicitly.

### Batch-processing a directory

```bash
decoct compress ./configs/ -r --stats
```

The `-r` flag recurses into subdirectories. Only files with recognised
extensions (`.yaml`, `.yml`, `.json`, `.ini`, `.conf`, `.cfg`, `.cnf`,
`.properties`) are picked up. Each file's platform is auto-detected
independently.
