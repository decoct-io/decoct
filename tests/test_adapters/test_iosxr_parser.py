"""Tests for IOS-XR parser: line classification, indentation, route-policy, annotations."""

from decoct.adapters.iosxr import parse_iosxr_config


class TestIosxrParser:
    def test_extracts_hostname_from_header(self) -> None:
        config = "!! IOS XR Configuration - P-CORE-01\nhostname P-CORE-01\n!\nend\n"
        tree = parse_iosxr_config(config)
        assert tree.hostname == "P-CORE-01"

    def test_extracts_hostname_from_command(self) -> None:
        config = "hostname MY-ROUTER\n!\nend\n"
        tree = parse_iosxr_config(config)
        assert tree.hostname == "MY-ROUTER"

    def test_parses_nested_sections(self) -> None:
        config = "router isis CORE\n is-type level-2-only\n!\nend\n"
        tree = parse_iosxr_config(config)
        assert len(tree.children) >= 1
        assert tree.children[0].keyword == "router"
        assert tree.children[0].args == ["isis", "CORE"]

    def test_handles_route_policy(self) -> None:
        config = "route-policy RPL-TEST\n set med 100\n pass\nend-policy\n!\nend\n"
        tree = parse_iosxr_config(config)
        rp = tree.children[0]
        assert rp.keyword == "route-policy"
        assert rp.args == ["RPL-TEST"]
        assert len(rp.children) == 2

    def test_handles_negation(self) -> None:
        config = "interface Loopback0\n no shutdown\n!\nend\n"
        tree = parse_iosxr_config(config)
        intf = tree.children[0]
        shutdown_node = intf.children[0]
        assert shutdown_node.keyword == "shutdown"
        assert shutdown_node.negated is True

    def test_handles_annotation_comments(self) -> None:
        config = "! CUSTOM: Test annotation\nhostname R1\n!\nend\n"
        tree = parse_iosxr_config(config)
        assert tree.children[0].annotation == "Test annotation"

    def test_handles_empty_sections(self) -> None:
        config = "address-family vpnv4-unicast\n!\nend\n"
        tree = parse_iosxr_config(config)
        assert len(tree.children) >= 1

    def test_metadata_extraction(self) -> None:
        config = "!! IOS XR Configuration - R1\n!! Platform: Cisco IOS-XR 7.9.2\nhostname R1\nend\n"
        tree = parse_iosxr_config(config)
        assert tree.metadata.hostname == "R1"
        assert tree.metadata.platform == "Cisco IOS-XR 7.9.2"
