"""Tests for IOS-XR path encoding for all section types."""

from decoct.adapters.iosxr import flatten_config_tree, parse_iosxr_config


class TestPathEncoding:
    def test_hostname_path(self) -> None:
        tree = parse_iosxr_config("hostname APE-R1-01\nend\n")
        attrs = flatten_config_tree(tree.children)
        assert attrs["hostname"] == "APE-R1-01"

    def test_router_isis_path(self) -> None:
        config = "router isis CORE\n is-type level-2-only\n!\nend\n"
        tree = parse_iosxr_config(config)
        attrs = flatten_config_tree(tree.children)
        assert attrs["router.isis.CORE.is-type"] == "level-2-only"

    def test_interface_path(self) -> None:
        config = "interface Loopback0\n description Test\n!\nend\n"
        tree = parse_iosxr_config(config)
        attrs = flatten_config_tree(tree.children)
        assert attrs["interface.Loopback0.description"] == "Test"

    def test_address_family_joins_args(self) -> None:
        config = "router isis CORE\n address-family ipv4 unicast\n  metric-style wide\n !\n!\nend\n"
        tree = parse_iosxr_config(config)
        attrs = flatten_config_tree(tree.children)
        assert attrs["router.isis.CORE.address-family.ipv4-unicast.metric-style"] == "wide"

    def test_bgp_neighbor_path(self) -> None:
        config = "router bgp 65002\n neighbor 10.0.0.11\n  remote-as 65002\n !\n!\nend\n"
        tree = parse_iosxr_config(config)
        attrs = flatten_config_tree(tree.children)
        assert attrs["router.bgp.65002.neighbor.10.0.0.11.remote-as"] == "65002"

    def test_vrf_path(self) -> None:
        config = "vrf VRF-A\n address-family ipv4 unicast\n !\n!\nend\n"
        tree = parse_iosxr_config(config)
        attrs = flatten_config_tree(tree.children)
        # vrf.VRF-A should have address-family child
        matching = [k for k in attrs if k.startswith("vrf.VRF-A")]
        assert len(matching) > 0

    def test_no_shutdown_becomes_false(self) -> None:
        config = "interface Loopback0\n no shutdown\n!\nend\n"
        tree = parse_iosxr_config(config)
        attrs = flatten_config_tree(tree.children)
        assert attrs["interface.Loopback0.shutdown"] == "false"

    def test_bare_keyword_becomes_true(self) -> None:
        config = "interface Loopback0\n cdp\n!\nend\n"
        tree = parse_iosxr_config(config)
        attrs = flatten_config_tree(tree.children)
        assert attrs["interface.Loopback0.cdp"] == "true"
