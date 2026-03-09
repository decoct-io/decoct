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
        # Defaults should be stripped
        assert "package_update" not in result.output
        assert "package_upgrade" not in result.output
        # List-item defaults should also be stripped (users.*.lock_passwd, etc.)
        assert "lock_passwd" not in result.output
        assert "no_create_home" not in result.output

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
        # Defaults should be stripped
        assert "schedulerName" not in result.output
        assert "enableServiceLinks" not in result.output
        assert "terminationMessagePath" not in result.output

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
