# Security Model

This document describes the security model of decoct, focusing on how secrets are
detected and redacted before infrastructure data is compressed or sent to an LLM.

## Threat Model

Infrastructure configuration data routinely contains secrets: database passwords,
API keys, bearer tokens, private keys, cloud connection strings, and other credentials.
decoct processes this data through a compression pipeline and, in its `learn` commands,
sends file contents to the Anthropic API for schema or assertion derivation.

The primary risk is **secret leakage** through two channels:

1. **Compressed output** -- secrets surviving in the compressed YAML that is then
   shared with humans or downstream tools.
2. **LLM API calls** -- secrets included in file contents sent to the Anthropic API
   during `decoct schema learn` or `decoct assertion learn` commands.

The mitigation for channel 1 is the **strip-secrets pass**, which runs first in every
pipeline before any other pass touches the data. Channel 2 is addressed differently --
see [LLM Data Flow](#llm-data-flow) below.

## strip-secrets as Security Boundary

The `StripSecretsPass` is the security boundary of the pipeline. It has the following
guarantees:

- It **MUST** be the first pass in every pipeline execution.
- It declares an **empty `run_after` list** (`run_after: list[str] = []`), meaning no
  pass is required before it.
- It declares an **empty `run_before` list**, imposing no ordering constraint in that
  direction. Other passes establish the ordering by declaring `run_after` dependencies
  that transitively depend on `strip-secrets` (e.g., `strip-defaults` declares
  `run_after = ["strip-secrets", "strip-comments"]`).
- The topological sort in `Pipeline.__init__()` resolves these constraints, placing
  `strip-secrets` at the front of the execution order.
- Every secret value is replaced with the **constant sentinel `[REDACTED]`**. No other
  replacement value is used anywhere in the codebase.

## Detection Methods

The pass uses three complementary detection strategies, applied in order. The first
match wins.

### Path-Based Rules

Any value whose dotted path matches one of the following `fnmatch` patterns is
unconditionally redacted:

| Pattern               | Matches                                         |
|-----------------------|-------------------------------------------------|
| `*.password`          | Any key named `password` at any depth           |
| `*.secret`            | Any key named `secret`                          |
| `*.secrets`           | Any key named `secrets`                         |
| `*.secrets.*`         | Any child of a key named `secrets`              |
| `*.credentials`       | Any key named `credentials`                     |
| `*.credentials.*`     | Any child of a key named `credentials`          |
| `*.private_key`       | Any key named `private_key`                     |
| `*.api_key`           | Any key named `api_key`                         |
| `*.connection_string` | Any key named `connection_string`               |
| `*.env.*`             | Any child of a key named `env`                  |

These patterns are defined in `DEFAULT_SECRET_PATHS` and can be extended via the
`secret_paths` parameter or through profile configuration.

### Regex Patterns

If no path pattern matches, the string value is tested against these compiled regular
expressions:

| Name                       | Pattern                                                                                      | Detects                                      |
|----------------------------|----------------------------------------------------------------------------------------------|----------------------------------------------|
| `aws_access_key`           | `AKIA[0-9A-Z]{16}`                                                                          | AWS access key IDs                           |
| `azure_connection_string`  | `DefaultEndpointsProtocol=https?;AccountName=` (case-insensitive)                            | Azure Storage connection strings             |
| `private_key_block`        | `-----BEGIN (RSA\|EC\|DSA\|OPENSSH )?PRIVATE KEY-----`                                      | PEM-encoded private keys (RSA, EC, DSA, OpenSSH) |
| `bearer_token`             | `Bearer\s+[A-Za-z0-9\-._~+/]{20,}={0,2}`                                                   | OAuth/API bearer tokens                      |
| `github_token`             | `(ghp\|gho\|ghs\|ghr\|github_pat)_[A-Za-z0-9_]{20,}`                                       | GitHub personal access tokens, OAuth tokens, app tokens, refresh tokens, and fine-grained PATs |
| `generic_credential_pair`  | `(password\|passwd\|secret\|api_key\|apikey\|access_key\|private_key\|auth_token)\s*[=:]\s*\S+` (case-insensitive) | Inline credential assignments in string values |

### Shannon Entropy

If neither path nor regex matches, and the path is not exempt, the value is checked
for high Shannon entropy -- a statistical indicator that the string contains random
data such as a key or token.

- **Entropy threshold:** `4.5` bits per character (default, configurable via
  `entropy_threshold` parameter)
- **Minimum length:** `16` characters (default, configurable via `min_entropy_length`
  parameter)
- **Calculation:** Shannon entropy `H = -sum(p_i * log2(p_i))` where `p_i` is the
  frequency of each character divided by the string length. Higher values indicate
  more uniformly distributed characters, which is characteristic of random secrets.

**Entropy-exempt paths** -- the following paths are excluded from entropy detection
because they contain commands or values that naturally have high character diversity:

| Pattern                  | Reason                         |
|--------------------------|--------------------------------|
| `*.healthcheck.test`     | Docker healthcheck commands    |
| `*.healthcheck.test.*`   | Arguments to healthcheck tests |
| `*.command`              | Container command strings      |
| `*.command.*`            | Command arguments              |
| `*.entrypoint`           | Container entrypoint strings   |
| `*.entrypoint.*`         | Entrypoint arguments           |

## Ordering Guarantee

The `Pipeline` constructor calls `_topological_sort()`, which implements Kahn's
algorithm on the dependency graph built from `run_after` and `run_before` declarations:

1. `StripSecretsPass` declares `run_after = []` -- no prerequisites.
2. Other passes declare dependencies that chain after `strip-secrets`. For example,
   `strip-defaults` declares `run_after = ["strip-secrets", "strip-comments"]`, and
   `strip-conformant` declares `run_after = ["strip-defaults"]`, creating the chain:
   `strip-secrets` -> `strip-defaults` -> `strip-conformant`.
3. Because `strip-secrets` has zero in-degree (no edges pointing to it), it is
   selected first by Kahn's algorithm.
4. If a cycle is detected (which would prevent ordering), `_topological_sort()` raises
   a `ValueError`.

This means no pass can execute before `strip-secrets` unless it also has an empty
`run_after` list and no other pass declares `run_before` pointing to it. By convention
and code review, `strip-secrets` is the only pass with this property -- all other
passes either depend on it directly or transitively.

## What is NOT Detected

The following categories of secrets may survive the strip-secrets pass:

- **Base64-encoded secrets** -- unless the encoded form happens to exceed the entropy
  threshold, a base64-wrapped secret will not trigger path or regex rules.
- **Secrets split across multiple fields** -- a username in one field and a password
  in a differently-named field will not be correlated.
- **Secrets embedded in structured values** -- a URL like
  `postgresql://user:password@host/db` will not be caught unless the field name matches
  a path pattern or the URL string matches a regex pattern.
- **Custom secret formats** -- proprietary token formats unknown to the built-in regex
  library will not be detected unless they have high entropy.
- **Secrets in field names** -- only string values are inspected. A key named
  `AKIA1234567890ABCDEF` would not be redacted (though its value would be checked).
- **Non-string values** -- integers, booleans, and other non-string scalars are not
  inspected (e.g., a numeric PIN stored as an integer).

## Audit Trail

Every redaction is recorded as an `AuditEntry` dataclass with two fields:

- **`path`** -- the dotted path to the redacted value (e.g., `services.web.environment.DB_PASSWORD`)
- **`detection_method`** -- one of:
  - `"path_pattern"` -- matched a secret path pattern
  - `"regex:<pattern_name>"` -- matched a named regex (e.g., `"regex:aws_access_key"`,
    `"regex:github_token"`)
  - `"entropy"` -- exceeded the Shannon entropy threshold

The audit trail **never** records the actual secret value. This is enforced by design:
the `AuditEntry` dataclass has no field for it, and the `_walk_and_redact` function
replaces the value in the document before creating the entry.

The audit trail is surfaced to users through:

- **`PassResult.details`** -- each entry is formatted as `"path (detection_method)"`.
- **`--show-removed` CLI flag** -- prints all pass results (including strip-secrets
  redactions) to stderr, showing the path and method for each redacted value.

## False Positives

The entropy-based detector will flag some non-secret strings:

- **UUIDs** -- `550e8400-e29b-41d4-a716-446655440000` has high entropy but is not a
  secret.
- **Content hashes** -- SHA-256 digests, Docker image digests, and similar hashes.
- **Encoded data** -- base64-encoded non-secret content with high character diversity.
- **Long configuration values** -- complex regex patterns, format strings, or URIs
  with many distinct characters.

Mitigations in place:

- The `min_entropy_length` threshold (default: 16) filters out short high-entropy
  strings.
- Entropy-exempt paths exclude healthcheck commands, container commands, and
  entrypoints.
- Both `entropy_threshold` and `min_entropy_length` are configurable per pass
  invocation.

**Policy: prefer over-redaction over missed secrets.** A false positive means a
non-secret value is replaced with `[REDACTED]` in the compressed output, which may
reduce usefulness but does not create a security risk. A false negative means a real
secret survives into the output, which is a security incident.

## LLM Data Flow

The `learn` commands (`decoct schema learn` and `decoct assertion learn`) send file
contents to the Anthropic API for analysis:

- **`learn_schema()`** reads user-specified files via `_read_file()` and sends their
  full text content as part of the prompt to the Anthropic `messages.create` API.
- **`learn_assertions()`** does the same for standards documents, example files, or
  corpus files. For corpus mode, file contents may be truncated proportionally if total
  size exceeds 300,000 characters.
- **strip-secrets does NOT run before learn commands.** The learn commands operate on
  raw user-provided files, not on the compression pipeline's output. The user is
  responsible for not passing files containing live secrets to learn commands.
- The compressed output produced by the pipeline (after strip-secrets has run) **is**
  safe for LLM consumption or sharing.
- **`ANTHROPIC_API_KEY`** is the only credential used by decoct itself. It is read
  from the environment by the `anthropic` SDK and is never logged or included in
  prompts.

## Recommendations for Sensitive Environments

1. **Always review `--show-removed` output** to verify that all expected secrets were
   redacted. The audit trail shows every redaction with its path and detection method.

2. **Do not pipe files with live credentials through learn commands.** Use sanitised
   copies or documentation-only inputs for `decoct schema learn` and
   `decoct assertion learn`.

3. **Use custom `secret_paths` in profiles** for non-standard secret field names
   specific to your infrastructure (e.g., `*.vault_token`, `*.signing_key`).

4. **Review false positives and adjust thresholds** if the default `entropy_threshold`
   of 4.5 is too aggressive or too permissive for your data. Lower values catch more
   secrets but produce more false positives; higher values are more permissive.

5. **Consider running strip-secrets as a standalone pre-processing step** by
   constructing a pipeline with only `StripSecretsPass` before feeding data into other
   tools or workflows.

6. **Audit the regex patterns** against your environment's credential formats. If your
   organisation uses custom token prefixes or secret formats, extend the detection
   patterns via a custom pass or by contributing patterns upstream.
