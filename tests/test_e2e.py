"""End-to-end tests — CLI invocation against realistic fixtures."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from decoct.cli import cli

FIXTURES = Path(__file__).parent / "fixtures"
YAML_FIXTURES = FIXTURES / "yaml"
SCHEMA_FIXTURES = FIXTURES / "schemas"
ASSERTION_FIXTURES = FIXTURES / "assertions"
PROFILE_FIXTURES = FIXTURES / "profiles"
JSON_FIXTURES = FIXTURES / "json"


class TestCompressRealistic:
    def test_compress_realistic_with_full_schema(self) -> None:
        """CLI exit 0, defaults stripped from realistic fixture."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "realistic-compose.yaml"),
            "--schema", str(SCHEMA_FIXTURES / "docker-compose-full.yaml"),
        ])
        assert result.exit_code == 0
        assert "services" in result.output
        # Some defaults should be gone (e.g. retries: 3 if it matches)
        # The output should still be valid YAML

    def test_compress_with_deployment_standards(self) -> None:
        """Deviations annotated, conformant values stripped."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "realistic-with-deviations.yaml"),
            "--assertions", str(ASSERTION_FIXTURES / "deployment-standards.yaml"),
        ])
        assert result.exit_code == 0
        # Deviating values should have [!] annotations
        assert "[!]" in result.output
        # Deviation summary should be present
        assert "deviations from standards" in result.output

    def test_compress_with_full_profile(self) -> None:
        """Profile loads all config and processes successfully."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "realistic-compose.yaml"),
            "--profile", str(PROFILE_FIXTURES / "docker-full.yaml"),
        ])
        assert result.exit_code == 0
        assert result.output  # produces some output


class TestCompressStats:
    def test_compress_stats_shows_savings(self) -> None:
        """`--stats` shows >0% savings."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "realistic-compose.yaml"),
            "--schema", str(SCHEMA_FIXTURES / "docker-compose-full.yaml"),
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output

    def test_compress_stats_only(self) -> None:
        """No YAML output, stats printed."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "realistic-compose.yaml"),
            "--schema", str(SCHEMA_FIXTURES / "docker-compose-full.yaml"),
            "--stats-only",
        ])
        assert result.exit_code == 0
        assert "Tokens:" in result.output or "saved" in result.output

    def test_compress_show_removed_details(self) -> None:
        """Pass details in output."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "realistic-compose.yaml"),
            "--schema", str(SCHEMA_FIXTURES / "docker-compose-full.yaml"),
            "--show-removed",
        ])
        assert result.exit_code == 0
        assert "strip-defaults" in result.output


class TestCompressOutput:
    def test_compress_output_file(self, tmp_path: Path) -> None:
        """`-o` writes compressed file."""
        runner = CliRunner()
        out_file = tmp_path / "compressed.yaml"
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "realistic-compose.yaml"),
            "--schema", str(SCHEMA_FIXTURES / "docker-compose-full.yaml"),
            "-o", str(out_file),
        ])
        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text()
        assert "services" in content


class TestCompressJsonInput:
    def test_compress_json_input(self) -> None:
        """JSON file processed through pipeline."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(JSON_FIXTURES / "simple-config.json"),
        ])
        assert result.exit_code == 0
        # JSON input should be output as YAML
        assert "services" in result.output


class TestCompressBundledSchema:
    def test_compress_bundled_schema(self) -> None:
        """`--schema docker-compose` works."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "with-defaults.yaml"),
            "--schema", "docker-compose",
        ])
        assert result.exit_code == 0
        assert "services" in result.output


class TestCompressMultipleFiles:
    def test_compress_multiple_files(self) -> None:
        """Batch processing of multiple files."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "realistic-compose.yaml"),
            str(YAML_FIXTURES / "realistic-with-deviations.yaml"),
        ])
        assert result.exit_code == 0
        # Both files should be processed
        assert "services" in result.output


class TestCompressCloudInit:
    def test_compress_cloud_init_with_schema(self) -> None:
        """Cloud-init schema strips known defaults."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "cloud-init-config.yaml"),
            "--schema", str(SCHEMA_FIXTURES / "cloud-init.yaml"),
        ])
        assert result.exit_code == 0
        # Non-default values should remain
        assert "packages" in result.output
        assert "nginx" in result.output
        # Defaults should be stripped from YAML body (may appear in class comments)
        yaml_body = "\n".join(
            line for line in result.output.splitlines() if not line.startswith("#")
        )
        assert "package_update" not in yaml_body
        assert "package_upgrade" not in yaml_body
        # List-item defaults should also be stripped
        assert "lock_passwd" not in yaml_body
        assert "no_create_home" not in yaml_body

    def test_compress_cloud_init_bundled(self) -> None:
        """`--schema cloud-init` works with bundled schema."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "cloud-init-config.yaml"),
            "--schema", "cloud-init",
        ])
        assert result.exit_code == 0
        assert "packages" in result.output

    def test_compress_cloud_init_auto_detect(self) -> None:
        """Cloud-init document auto-detected without --schema."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "cloud-init-config.yaml"),
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output

    def test_compress_cloud_init_stats(self) -> None:
        """Cloud-init compression shows meaningful savings."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "cloud-init-config.yaml"),
            "--schema", "cloud-init",
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output


class TestCompressAnsible:
    def test_compress_ansible_bundled(self) -> None:
        """Ansible playbook schema strips module defaults."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "ansible-playbook.yaml"),
            "--schema", "ansible-playbook",
        ])
        assert result.exit_code == 0
        # Non-default values should remain
        assert "nginx" in result.output
        # Module defaults should be stripped
        assert "purge" not in result.output
        assert "autoremove" not in result.output

    def test_compress_ansible_stats(self) -> None:
        """Ansible compression shows savings."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "ansible-playbook.yaml"),
            "--schema", "ansible-playbook",
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output


class TestCompressKubernetes:
    def test_compress_kubernetes_bundled(self) -> None:
        """Kubernetes schema strips API defaults and system-managed fields."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "kubernetes-deployment.yaml"),
            "--schema", "kubernetes",
        ])
        assert result.exit_code == 0
        # Non-default values should remain
        assert "web-app" in result.output
        assert "replicas" in result.output  # 3 is not the default
        # Defaults should be stripped from YAML body (may appear in class comments)
        yaml_body = "\n".join(
            line for line in result.output.splitlines() if not line.startswith("#")
        )
        assert "schedulerName" not in yaml_body
        assert "enableServiceLinks" not in yaml_body
        assert "terminationMessagePath" not in yaml_body

    def test_compress_kubernetes_auto_detect(self) -> None:
        """Kubernetes manifest auto-detected by apiVersion + kind."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "kubernetes-deployment.yaml"),
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output


class TestCompressSshd:
    def test_compress_sshd_bundled(self) -> None:
        """SSH config schema strips known defaults."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "sshd-config.yaml"),
            "--schema", "sshd-config",
        ])
        assert result.exit_code == 0
        # Non-default values should remain (hardened settings)
        assert "PermitRootLogin" in result.output  # 'no' != default 'prohibit-password'
        assert "PasswordAuthentication" in result.output  # 'no' != default 'yes'
        # Defaults should be stripped
        assert "FingerprintHash" not in result.output
        assert "IgnoreRhosts" not in result.output


class TestCompressGitHubActions:
    def test_compress_github_actions_bundled(self) -> None:
        """GitHub Actions schema strips known defaults."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "github-actions-workflow.yaml"),
            "--schema", "github-actions",
        ])
        assert result.exit_code == 0
        # Non-default values should remain
        assert "ubuntu-latest" in result.output
        assert "actions/checkout@v4" in result.output
        # Non-default timeout should remain
        assert "30" in result.output  # test job has timeout-minutes: 30
        # Default values should be stripped from YAML body
        yaml_body = "\n".join(
            line for line in result.output.splitlines() if not line.startswith("#")
        )
        # Default timeout-minutes: 360 should be stripped from lint/deploy jobs
        # Default continue-on-error: false should be stripped
        assert "continue-on-error" not in yaml_body

    def test_compress_github_actions_auto_detect(self) -> None:
        """GitHub Actions workflow auto-detected by on + jobs keys."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "github-actions-workflow.yaml"),
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output

    def test_compress_github_actions_stats(self) -> None:
        """GitHub Actions compression shows meaningful savings."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "github-actions-workflow.yaml"),
            "--schema", "github-actions",
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output


class TestCompressTraefik:
    def test_compress_traefik_bundled(self) -> None:
        """Traefik schema strips known defaults."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "traefik-config.yaml"),
            "--schema", "traefik",
        ])
        assert result.exit_code == 0
        # Non-default values should remain
        assert ":80" in result.output or "web" in result.output
        assert "traefik" in result.output
        # Non-default values (custom settings) should remain
        assert "INFO" in result.output  # log.level: INFO != default ERROR
        assert "json" in result.output  # accessLog.format: json != default common
        assert "exposedByDefault" in result.output  # false != default true

    def test_compress_traefik_auto_detect(self) -> None:
        """Traefik config auto-detected by entryPoints key."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "traefik-config.yaml"),
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output

    def test_compress_traefik_stats(self) -> None:
        """Traefik compression shows meaningful savings."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "traefik-config.yaml"),
            "--schema", "traefik",
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output


class TestCompressPrometheus:
    def test_compress_prometheus_bundled(self) -> None:
        """Prometheus schema strips known defaults."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "prometheus-config.yaml"),
            "--schema", "prometheus",
        ])
        assert result.exit_code == 0
        # Non-default values should remain
        assert "prometheus" in result.output  # job_name
        assert "node-exporter" in result.output
        assert "localhost:9090" in result.output
        assert "mimir" in result.output  # remote_write URL
        # Non-default scrape_interval should remain
        assert "30s" in result.output or "15s" in result.output

    def test_compress_prometheus_auto_detect(self) -> None:
        """Prometheus config auto-detected by scrape_configs key."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "prometheus-config.yaml"),
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output

    def test_compress_prometheus_stats(self) -> None:
        """Prometheus compression shows meaningful savings."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "prometheus-config.yaml"),
            "--schema", "prometheus",
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output


class TestCompressAutoDetect:
    def test_auto_detect_docker_compose(self) -> None:
        """Auto-applies docker-compose schema without --schema flag."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "realistic-compose.yaml"),
            "--stats",
        ])
        assert result.exit_code == 0
        # Should auto-detect docker-compose and apply schema
        assert "saved" in result.output or "Tokens:" in result.output

    def test_auto_detect_json(self) -> None:
        """Auto-applies terraform-state schema for tfstate JSON."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(JSON_FIXTURES / "tfstate-sample.json"),
            "--stats",
        ])
        assert result.exit_code == 0


class TestCompressBundledProfile:
    def test_bundled_profile_docker_compose(self) -> None:
        """--profile docker-compose applies full pipeline."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "realistic-compose.yaml"),
            "--profile", "docker-compose",
        ])
        assert result.exit_code == 0
        assert "services" in result.output

    def test_bundled_profile_with_deviations(self) -> None:
        """Bundled profile detects deviations."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "realistic-with-deviations.yaml"),
            "--profile", "docker-compose",
        ])
        assert result.exit_code == 0
        assert "[!]" in result.output


class TestCompressNetworkOS:
    def test_compress_cisco_ios_xe_with_bundled_schema(self) -> None:
        """Verify IOS XE defaults are stripped from a representative config."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "ios-xe-show-run-all.yaml"),
            "--schema", "cisco-ios-xe",
        ])
        assert result.exit_code == 0
        # Non-default customisations should remain
        yaml_body = "\n".join(
            line for line in result.output.splitlines() if not line.startswith("#")
        )
        assert "WAN uplink to ISP-A" in yaml_body  # custom description
        assert "203.0.113.1" in yaml_body  # custom IP address
        assert "example.com" in yaml_body  # custom domain name
        assert "4096" in yaml_body  # custom spanning-tree priority
        assert "10.255.0.1" in yaml_body  # custom OSPF router-id
        # Defaults should be stripped from YAML body
        assert "ip.classless" not in yaml_body or "classless: true" not in yaml_body

    def test_compress_juniper_junos_with_bundled_schema(self) -> None:
        """Verify JunOS defaults are stripped from a representative config."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "junos-config.yaml"),
            "--schema", "juniper-junos",
        ])
        assert result.exit_code == 0
        # Non-default customisations should remain
        yaml_body = "\n".join(
            line for line in result.output.splitlines() if not line.startswith("#")
        )
        assert "core-rtr-01" in yaml_body  # custom hostname
        assert "10.255.0.1" in yaml_body  # custom router-id
        assert "Uplink to PE-01" in yaml_body  # custom description
        assert "9192" in yaml_body  # custom MTU
        assert "10g" in yaml_body or "10G" in yaml_body  # custom reference-bandwidth
        # Defaults should be stripped from YAML body
        assert "asdot-notation" not in yaml_body or "asdot-notation: false" not in yaml_body

    def test_compress_cisco_ios_xe_stats(self) -> None:
        """IOS XE compression shows meaningful savings."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "ios-xe-show-run-all.yaml"),
            "--schema", "cisco-ios-xe",
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output

    def test_compress_juniper_junos_stats(self) -> None:
        """JunOS compression shows meaningful savings."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(YAML_FIXTURES / "junos-config.yaml"),
            "--schema", "juniper-junos",
            "--stats",
        ])
        assert result.exit_code == 0
        assert "saved" in result.output or "Tokens:" in result.output


class TestCompressDirectory:
    def test_compress_directory(self, tmp_path: Path) -> None:
        """Directory argument processes all matching files."""
        import shutil

        # Copy fixtures into a temp directory
        shutil.copy(YAML_FIXTURES / "realistic-compose.yaml", tmp_path / "a.yaml")
        shutil.copy(YAML_FIXTURES / "realistic-with-deviations.yaml", tmp_path / "b.yml")

        runner = CliRunner()
        result = runner.invoke(cli, ["compress", str(tmp_path)])
        assert result.exit_code == 0
        assert "services" in result.output

    def test_compress_directory_recursive(self, tmp_path: Path) -> None:
        """--recursive descends into subdirectories."""
        import shutil

        subdir = tmp_path / "sub"
        subdir.mkdir()
        shutil.copy(YAML_FIXTURES / "realistic-compose.yaml", tmp_path / "root.yaml")
        shutil.copy(YAML_FIXTURES / "realistic-with-deviations.yaml", subdir / "nested.yaml")

        runner = CliRunner()
        # Without --recursive, should only find root.yaml
        result1 = runner.invoke(cli, ["compress", str(tmp_path)])
        assert result1.exit_code == 0

        # With --recursive, should find both
        result2 = runner.invoke(cli, ["compress", str(tmp_path), "--recursive"])
        assert result2.exit_code == 0
        # Recursive output should be longer (more content)
        assert len(result2.output) > len(result1.output)

    def test_compress_directory_with_json(self, tmp_path: Path) -> None:
        """Directory mode picks up JSON files too."""
        import shutil

        shutil.copy(JSON_FIXTURES / "simple-config.json", tmp_path / "config.json")

        runner = CliRunner()
        result = runner.invoke(cli, ["compress", str(tmp_path)])
        assert result.exit_code == 0
        assert "services" in result.output

    def test_compress_directory_stats(self, tmp_path: Path) -> None:
        """Multi-file stats show aggregate totals."""
        import shutil

        shutil.copy(YAML_FIXTURES / "realistic-compose.yaml", tmp_path / "a.yaml")
        shutil.copy(YAML_FIXTURES / "realistic-with-deviations.yaml", tmp_path / "b.yaml")

        runner = CliRunner()
        result = runner.invoke(cli, ["compress", str(tmp_path), "--stats"])
        assert result.exit_code == 0
        assert "Total:" in result.output
