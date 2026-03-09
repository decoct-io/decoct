# Troubleshooting

## "No schema found" / No defaults stripped
- If `--schema` not provided, decoct tries auto-detection from document content
- Auto-detection only works for 8 platforms (Docker Compose, Kubernetes, Ansible, cloud-init, Terraform, GitHub Actions, Traefik, Prometheus)
- Fix: explicitly pass `--schema <name>` or `--schema /path/to/schema.yaml`
- List available schemas: docker-compose, kubernetes, ansible-playbook, cloud-init, sshd-config, terraform-state, github-actions, traefik, prometheus, mongodb, postgresql, redis, mariadb-mysql, kafka, opentelemetry-collector, argocd, fluent-bit, gitlab-ci, grafana, keycloak, entra-id, intune, azure-arm, aws-cloudformation, gcp-resources

## False positive secret detection
- Healthcheck commands, long URLs, UUIDs, and hashes can trigger entropy-based detection
- Healthcheck test paths are exempted by default
- Adjust entropy threshold in a profile: `strip-secrets: { entropy_threshold: 5.0 }`
- Adjust minimum length: `strip-secrets: { min_entropy_length: 20 }`
- Use `--show-removed` to see what was detected and why

## Values not being stripped by strip-defaults
- Check that the schema default matches exactly (type-coerced comparison)
- Check path pattern: `services.*.restart` matches `services.web.restart` but not `restart`
- Low-confidence schemas may be skipped: check `skip_low_confidence` setting
- Use `--show-removed` to see what strip-defaults actually removed

## Assertions not matching
- Check path pattern syntax (dot-separated, * for single segment, ** for any depth)
- Only `must` severity assertions are stripped by strip-conformant
- `should` and `may` assertions are annotated but not stripped
- Assertions without `match` are LLM-context only — not machine-evaluated
- Check match condition: `value` is case-insensitive for strings, `pattern` uses re.search (not re.match)

## Empty or nearly empty output
- If most values are stripped, the document was highly conformant/default-heavy
- Use `--show-removed` to understand what was stripped
- Consider removing some passes from the profile if too aggressive
- The prune-empty pass removes empty containers — this is expected

## JSON/INI parsing failures
- JSON: must be valid JSON (check with `python -m json.tool < file.json`)
- INI: sections need `[section]` headers, or flat key=value (no sections)
- File extension determines parser: .json → JSON, .ini/.conf/.cfg/.cnf/.properties → INI, everything else → YAML
- stdin is always treated as YAML — pipe JSON through a file instead

## LLM learn commands failing
- Requires `pip install decoct[llm]`
- Set ANTHROPIC_API_KEY environment variable
- Rate limits: reduce file count or file size
- Model errors: try `--model claude-sonnet-4-20250514` (default)
- `--corpus` and `--example` are mutually exclusive
- At least one input file required (--standard, --example, or --corpus)

## Token count discrepancies
- Default encoding is cl100k_base (GPT-4, Claude)
- Use `--encoding o200k_base` for GPT-4o token counts
- Token counts are of the YAML text representation, not the parsed structure
- Whitespace and formatting affect token counts

## Performance on large files
- YAML parsing is the main bottleneck
- Large files (>10K lines): expect a few seconds
- Batch processing: use `--recursive` for directory mode
- The pipeline is deterministic — cache results for unchanged files

## Getting Help
- Issue tracker: https://github.com/decoct-io/decoct/issues
- Check `--show-removed` output for debugging
- Include the decoct version (`decoct --version`) in bug reports
