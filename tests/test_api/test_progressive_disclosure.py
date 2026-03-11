"""Tests for the Progressive Disclosure API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from decoct.api.app import create_app

# Use hybrid-infra output as test fixture (checked into repo)
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "hybrid-infra"

pytestmark = pytest.mark.skipif(
    not (OUTPUT_DIR / "tier_a.yaml").exists(),
    reason="hybrid-infra output not present",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = create_app(OUTPUT_DIR)
    with TestClient(app) as c:
        yield c


class TestFleetEndpoints:
    """Tests for GET / and GET /types."""

    def test_get_fleet_overview(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "types" in data
        assert isinstance(data["types"], dict)
        assert len(data["types"]) > 0

    def test_get_types(self, client: TestClient) -> None:
        resp = client.get("/types")
        assert resp.status_code == 200
        data = resp.json()
        assert "types" in data
        assert len(data["types"]) > 0
        first = data["types"][0]
        assert "type_id" in first
        assert "count" in first
        assert "classes" in first

    def test_fleet_overview_has_docker_compose(self, client: TestClient) -> None:
        resp = client.get("/")
        data = resp.json()
        assert "docker-compose" in data["types"]


class TestTypeEndpoints:
    """Tests for type-level detail endpoints."""

    def test_get_type_detail(self, client: TestClient) -> None:
        resp = client.get("/types/docker-compose")
        assert resp.status_code == 200
        data = resp.json()
        assert "base_class" in data
        assert "classes" in data

    def test_get_type_not_found(self, client: TestClient) -> None:
        resp = client.get("/types/nonexistent-type")
        assert resp.status_code == 404

    def test_get_classes(self, client: TestClient) -> None:
        resp = client.get("/types/docker-compose/classes")
        assert resp.status_code == 200
        data = resp.json()
        assert "base_class" in data
        assert "classes" in data
        assert "subclasses" in data

    def test_get_templates(self, client: TestClient) -> None:
        resp = client.get("/types/docker-compose/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "composite_templates" in data

    def test_list_instances(self, client: TestClient) -> None:
        resp = client.get("/types/docker-compose/instances")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type_id"] == "docker-compose"
        assert data["entity_count"] > 0
        assert len(data["entities"]) > 0
        entity = data["entities"][0]
        assert "entity_id" in entity
        assert "class_name" in entity


class TestEntityEndpoints:
    """Tests for entity-level reconstruction, delta, and layers."""

    def _get_first_entity(self, client: TestClient) -> str:
        resp = client.get("/types/docker-compose/instances")
        return resp.json()["entities"][0]["entity_id"]

    def test_reconstruct_entity(self, client: TestClient) -> None:
        entity_id = self._get_first_entity(client)
        resp = client.get(f"/types/docker-compose/instances/{entity_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == entity_id
        assert data["entity_type"] == "docker-compose"
        assert isinstance(data["attributes"], dict)
        assert len(data["attributes"]) > 0

    def test_entity_not_found(self, client: TestClient) -> None:
        resp = client.get("/types/docker-compose/instances/nonexistent-entity")
        assert resp.status_code == 404

    def test_entity_delta(self, client: TestClient) -> None:
        entity_id = self._get_first_entity(client)
        resp = client.get(f"/types/docker-compose/instances/{entity_id}/delta")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == entity_id
        assert data["type_id"] == "docker-compose"
        assert data["class_name"] is not None

    def test_entity_layers(self, client: TestClient) -> None:
        entity_id = self._get_first_entity(client)
        resp = client.get(f"/types/docker-compose/instances/{entity_id}/layers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == entity_id
        assert isinstance(data["layers"], dict)
        assert len(data["layers"]) > 0
        # Each layer entry should have value and source
        for path, layer in data["layers"].items():
            assert "value" in layer
            assert "source" in layer
            assert layer["source"] in (
                "base_class", "class", "subclass", "override",
                "composite_template", "instance_attr", "phone_book",
            )


class TestDeltaEndpoints:
    """Tests for raw Tier C delta endpoints."""

    def test_get_type_deltas(self, client: TestClient) -> None:
        resp = client.get("/types/docker-compose/deltas")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type_id"] == "docker-compose"
        assert "class_assignments" in data
        assert isinstance(data["class_assignments"], dict)


class TestProjectionEndpoints:
    """Tests for projection endpoints."""

    def test_list_projections(self, client: TestClient) -> None:
        resp = client.get("/types/docker-compose/projections")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type_id"] == "docker-compose"
        assert isinstance(data["subjects"], list)

    def test_get_projection(self, client: TestClient) -> None:
        resp = client.get("/types/docker-compose/projections")
        data = resp.json()
        if not data["subjects"]:
            pytest.skip("No projections available")
        subject = data["subjects"][0]
        resp = client.get(f"/types/docker-compose/projections/{subject}")
        assert resp.status_code == 200

    def test_projection_not_found(self, client: TestClient) -> None:
        resp = client.get("/types/docker-compose/projections/nonexistent-subject")
        assert resp.status_code == 404

    def test_projection_type_not_found(self, client: TestClient) -> None:
        resp = client.get("/types/nonexistent/projections")
        assert resp.status_code == 404


class TestStatsEndpoint:
    """Tests for GET /stats."""

    def test_get_stats(self, client: TestClient) -> None:
        resp = client.get("/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "tier_a" in data
        assert "tier_b" in data
        assert "tier_c" in data
        assert data["output_total_bytes"] > 0
        assert data["output_total_files"] > 0
        assert isinstance(data["type_stats"], list)
        assert len(data["type_stats"]) > 0


class TestProgressiveDisclosure:
    """Integration test: verify the progressive disclosure flow."""

    def test_progressive_flow(self, client: TestClient) -> None:
        """Walk the full disclosure path: fleet → type → entity → layers."""
        # 1. Fleet overview
        resp = client.get("/")
        assert resp.status_code == 200
        types = resp.json()["types"]
        type_id = next(iter(types))

        # 2. Type list
        resp = client.get("/types")
        assert resp.status_code == 200

        # 3. Type detail (Tier B)
        resp = client.get(f"/types/{type_id}")
        assert resp.status_code == 200

        # 4. Instances
        resp = client.get(f"/types/{type_id}/instances")
        assert resp.status_code == 200
        entities = resp.json()["entities"]
        if not entities:
            return
        entity_id = entities[0]["entity_id"]

        # 5. Entity delta
        resp = client.get(f"/types/{type_id}/instances/{entity_id}/delta")
        assert resp.status_code == 200

        # 6. Entity layers
        resp = client.get(f"/types/{type_id}/instances/{entity_id}/layers")
        assert resp.status_code == 200

        # 7. Reconstructed entity
        resp = client.get(f"/types/{type_id}/instances/{entity_id}")
        assert resp.status_code == 200

        # 8. Type deltas
        resp = client.get(f"/types/{type_id}/deltas")
        assert resp.status_code == 200
