"""Tests for the hybrid-infra adapter: per-format parsing and flattening."""

from pathlib import Path

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from decoct.adapters.hybrid_infra import (
    HybridInfraAdapter,
    flatten_doc,
)
from decoct.core.composite_value import CompositeValue
from decoct.core.entity_graph import EntityGraph

FIXTURES = Path("tests/fixtures/hybrid-infra/configs")


class TestParseHelper:
    """Shared parsing helper."""

    def _parse_one(self, filename: str) -> tuple[EntityGraph, str]:
        adapter = HybridInfraAdapter()
        graph = EntityGraph()
        parsed = adapter.parse(str(FIXTURES / filename))
        adapter.extract_entities(parsed, graph)
        entity_id = graph.entity_ids[0]
        return graph, entity_id


class TestYamlCompose(TestParseHelper):
    """Docker Compose YAML parsing."""

    def test_parse_yaml_compose(self) -> None:
        graph, eid = self._parse_one("compose-dev.yaml")
        e = graph.get_entity(eid)
        assert eid == "compose-dev"
        assert e.schema_type_hint == "docker-compose"
        # Services are nested dicts, should appear as dotted paths
        assert any(p.startswith("services.") for p in e.attributes)

    def test_compose_service_attributes(self) -> None:
        graph, eid = self._parse_one("compose-dev.yaml")
        e = graph.get_entity(eid)
        assert e.attributes["services.core-api.image"].value == "ridgeline/core-api:dev"
        assert e.attributes["services.core-api.restart"].value == "unless-stopped"


class TestYamlAnsible(TestParseHelper):
    """Ansible playbook YAML parsing (root list unwrapping)."""

    def test_parse_yaml_ansible(self) -> None:
        graph, eid = self._parse_one("ansible-base-server.yaml")
        e = graph.get_entity(eid)
        assert eid == "ansible-base-server"
        assert e.schema_type_hint == "ansible-playbook"
        # Root list should be unwrapped — play-level fields should appear
        assert e.attributes["name"].value == "Base Server Provisioning"
        assert e.attributes["hosts"].value == "all"

    def test_ansible_tasks_as_composite(self) -> None:
        graph, eid = self._parse_one("ansible-base-server.yaml")
        e = graph.get_entity(eid)
        assert "tasks" in e.attributes
        cv = e.attributes["tasks"].value
        assert isinstance(cv, CompositeValue)
        assert cv.kind == "list"


class TestYamlCloudInit(TestParseHelper):
    """Cloud-init YAML parsing."""

    def test_parse_yaml_cloud_init(self) -> None:
        graph, eid = self._parse_one("cloud-init-app-server.yaml")
        e = graph.get_entity(eid)
        assert eid == "cloud-init-app-server"
        assert e.schema_type_hint == "cloud-init"
        assert "package_update" in e.attributes

    def test_cloud_init_users_composite(self) -> None:
        graph, eid = self._parse_one("cloud-init-app-server.yaml")
        e = graph.get_entity(eid)
        # users contains a mix of scalars ("default") and dicts — handled
        # as scalars-joined or composite depending on content
        assert any(p.startswith("users") or p == "users" for p in e.attributes)


class TestYamlTraefik(TestParseHelper):
    """Traefik YAML parsing."""

    def test_parse_yaml_traefik(self) -> None:
        graph, eid = self._parse_one("traefik-prod-static.yaml")
        e = graph.get_entity(eid)
        assert eid == "traefik-prod-static"
        assert e.schema_type_hint == "traefik"
        # Nested entryPoints should be flattened
        assert "api.dashboard" in e.attributes


class TestYamlPrometheus(TestParseHelper):
    """Prometheus YAML parsing."""

    def test_parse_yaml_prometheus(self) -> None:
        graph, eid = self._parse_one("prometheus-prod.yaml")
        e = graph.get_entity(eid)
        assert eid == "prometheus-prod"
        assert e.schema_type_hint == "prometheus"

    def test_prometheus_scrape_configs_composite(self) -> None:
        graph, eid = self._parse_one("prometheus-prod.yaml")
        e = graph.get_entity(eid)
        assert "scrape_configs" in e.attributes
        cv = e.attributes["scrape_configs"].value
        assert isinstance(cv, CompositeValue)
        assert cv.kind == "list"


class TestJsonTfvars(TestParseHelper):
    """JSON tfvars parsing."""

    def test_parse_json_tfvars(self) -> None:
        graph, eid = self._parse_one("tfvars-prod.json")
        e = graph.get_entity(eid)
        assert eid == "tfvars-prod"
        assert e.schema_type_hint is None  # tfvars not detected
        # Nested keys should be flattened
        assert e.attributes["compute.app_instance_type"].value == "t3.xlarge"
        assert e.attributes["compute.app_instance_count"].value == "3"


class TestJsonAppConfig(TestParseHelper):
    """JSON app config parsing."""

    def test_parse_json_app_config(self) -> None:
        graph, eid = self._parse_one("app-config-auth-jwt.json")
        e = graph.get_entity(eid)
        assert eid == "app-config-auth-jwt"
        assert e.schema_type_hint is None
        # Nested + flat attributes
        assert e.attributes["name"].value == "Auth Service JWT Config"
        assert e.attributes["auth.jwt_expiry_seconds"].value == "3600"

    def test_json_scalar_array_joined(self) -> None:
        graph, eid = self._parse_one("app-config-auth-jwt.json")
        e = graph.get_entity(eid)
        # cors.origins is an array of strings
        assert "cors.origins" in e.attributes
        assert "https://app.ridgeline.io" in e.attributes["cors.origins"].value


class TestIniPostgresql(TestParseHelper):
    """PostgreSQL flat INI parsing."""

    def test_parse_ini_postgresql(self) -> None:
        graph, eid = self._parse_one("pg-prod-primary.conf")
        e = graph.get_entity(eid)
        assert eid == "pg-prod-primary"
        assert e.schema_type_hint is None  # INI not detected by detect_platform
        assert e.attributes["max_connections"].value == "200"
        assert e.attributes["shared_buffers"].value == "2GB"


class TestIniMariadb(TestParseHelper):
    """MariaDB sectioned INI parsing."""

    def test_parse_ini_mariadb(self) -> None:
        graph, eid = self._parse_one("maria-dev.cnf")
        e = graph.get_entity(eid)
        assert eid == "maria-dev"
        assert e.schema_type_hint is None
        # Sectioned INI → section.key dotted paths
        assert e.attributes["mysqld.port"].value == "3306"
        assert e.attributes["mysqld.max_connections"].value == "50"


class TestIniSystemd(TestParseHelper):
    """systemd sectioned INI parsing."""

    def test_parse_ini_systemd(self) -> None:
        graph, eid = self._parse_one("systemd-core-api.conf")
        e = graph.get_entity(eid)
        assert eid == "systemd-core-api"
        assert e.schema_type_hint is None
        assert e.attributes["Unit.description"].value == "Ridgeline Core API Service"
        assert e.attributes["Service.type"].value == "simple"


class TestSshdSpaceSeparated(TestParseHelper):
    """sshd space-separated config parsing (fallback parser)."""

    def test_parse_sshd_space_separated(self) -> None:
        graph, eid = self._parse_one("sshd-prod.conf")
        e = graph.get_entity(eid)
        assert eid == "sshd-prod"
        assert e.schema_type_hint is None
        # Space-separated Key Value → attributes
        assert e.attributes["Port"].value == "22"
        assert e.attributes["PermitRootLogin"].value == "false"
        assert e.attributes["PasswordAuthentication"].value == "false"


class TestSysctl(TestParseHelper):
    """sysctl flat key=value parsing."""

    def test_parse_sysctl(self) -> None:
        graph, eid = self._parse_one("sysctl-hardened.conf")
        e = graph.get_entity(eid)
        assert eid == "sysctl-hardened"
        assert e.schema_type_hint is None
        # Flat key=value with dotted kernel paths
        assert e.attributes["vm.swappiness"].value == "10"
        assert e.attributes["net.core.somaxconn"].value == "65535"


class TestFlattenDocEdgeCases:
    """Edge cases for flatten_doc."""

    def test_none_and_empty_filtered(self) -> None:
        doc = CommentedMap()
        doc["a"] = "value"
        doc["b"] = None
        doc["c"] = []
        doc["d"] = CommentedMap()
        flat, composites = flatten_doc(doc)
        assert "a" in flat
        assert "b" not in flat
        assert "c" not in flat
        assert "d" not in flat

    def test_scalar_array_joined(self) -> None:
        doc = CommentedMap()
        seq = CommentedSeq()
        seq.extend(["a", "b", "c"])
        doc["items"] = seq
        flat, composites = flatten_doc(doc)
        assert flat["items"] == "a,b,c"
        assert "items" not in composites

    def test_object_array_composite(self) -> None:
        doc = CommentedMap()
        seq = CommentedSeq()
        item1 = CommentedMap()
        item1["name"] = "foo"
        item1["value"] = "bar"
        item2 = CommentedMap()
        item2["name"] = "baz"
        item2["value"] = "qux"
        seq.append(item1)
        seq.append(item2)
        doc["entries"] = seq
        flat, composites = flatten_doc(doc)
        assert "entries" in composites
        cv = composites["entries"]
        assert isinstance(cv, CompositeValue)
        assert cv.kind == "list"
        assert len(cv.data) == 2
        assert cv.data[0]["name"] == "foo"

    def test_boolean_to_string(self) -> None:
        doc = CommentedMap()
        doc["enabled"] = True
        doc["disabled"] = False
        flat, _ = flatten_doc(doc)
        assert flat["enabled"] == "true"
        assert flat["disabled"] == "false"

    def test_number_to_string(self) -> None:
        doc = CommentedMap()
        doc["count"] = 42
        doc["ratio"] = 3.14
        flat, _ = flatten_doc(doc)
        assert flat["count"] == "42"
        assert flat["ratio"] == "3.14"
