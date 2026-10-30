import os
import xml.etree.ElementTree as ET
from ipaddress import IPv4Interface, IPv4Network
from xml.sax.saxutils import escape

from app.backends import planning

FILTER = (
    '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">'
    "<interface><name>{name}</name></interface></interfaces>"
)


def _error(code):
    return {"status": "error", "result": code}


def _manager(router):
    from ncclient import manager

    return manager.connect(
        host=router,
        port=830,
        username=os.environ.get("ROUTER_USER", ""),
        password=os.environ.get("ROUTER_PASS", ""),
        hostkey_verify=False,
        allow_agent=False,
        look_for_keys=False,
        timeout=10,
    )


def _real_get_config(router, filter_xml):
    with _manager(router) as m:
        return m.get_config(
            source="running", filter=("subtree", filter_xml)
        ).data_xml


def _real_edit_config(router, config_xml):
    with _manager(router) as m:
        m.edit_config(target="running", config=config_xml)


def _map_exception(exc):
    if isinstance(exc, PermissionError):
        return _error("authentication_failed")
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return _error("connection_failed")
    try:
        from ncclient.operations import RPCError
        from ncclient.transport.errors import (
            AuthenticationError,
            SSHError,
            TransportError,
        )

        if isinstance(exc, AuthenticationError):
            return _error("authentication_failed")
        if isinstance(exc, (SSHError, TransportError)):
            return _error("connection_failed")
        if isinstance(exc, RPCError):
            return _error("backend_failed")
    except ImportError:
        pass
    try:
        import paramiko

        if isinstance(exc, paramiko.AuthenticationException):
            return _error("authentication_failed")
        if isinstance(exc, paramiko.SSHException):
            return _error("connection_failed")
    except ImportError:
        pass
    return _error("backend_failed")


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _child(element, name):
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _parse(xml_text, interface_name):
    root = ET.fromstring(xml_text)
    for element in root.iter():
        if _local(element.tag) != "interface":
            continue
        name = _child(element, "name")
        if name is None or (name.text or "").strip() != interface_name:
            continue
        description = _child(element, "description")
        enabled = _child(element, "enabled")
        ipv4 = None
        ipv4_el = _child(element, "ipv4")
        address = (
            _child(ipv4_el, "address") if ipv4_el is not None else None
        )
        if address is not None:
            ip = _child(address, "ip")
            mask = _child(address, "netmask")
            prefix = IPv4Network(
                f"0.0.0.0/{mask.text.strip()}"
            ).prefixlen
            ipv4 = f"{ip.text.strip()}/{prefix}"
        return {
            "name": interface_name,
            "ipv4": ipv4,
            "description": (
                description.text if description is not None else None
            ),
            "admin_state": (
                "down"
                if enabled is not None
                and (enabled.text or "").strip().lower() == "false"
                else "up"
            ),
        }
    return None


def get_interface_state(
    router,
    interface_name,
    netconf_get_config=None,
):
    """Return normalized interface status using NETCONF."""
    netconf_get_config = netconf_get_config or _real_get_config
    try:
        xml_text = netconf_get_config(
            router, FILTER.format(name=escape(interface_name))
        )
    except Exception as exc:
        return _map_exception(exc)
    try:
        interface = _parse(xml_text, interface_name)
    except (ET.ParseError, AttributeError, ValueError, TypeError):
        return _error("backend_failed")
    if interface is None:
        return {"status": "ok", "result": "not_found", "interface": None}
    return {"status": "ok", "result": "found", "interface": interface}


def plan_interface(
    router,
    desired_interface,
    netconf_get_config=None,
):
    """Return create/update/no_change plan using NETCONF status."""
    return planning.plan_interface(
        router,
        desired_interface,
        lambda r, name: get_interface_state(r, name, netconf_get_config),
    )


def _build_config(desired):
    number = desired["name"][len("Loopback"):]
    int(number)
    ipv4 = IPv4Interface(desired["ipv4"])
    shutdown = "<shutdown/>" if desired["admin_state"] == "down" else ""
    return (
        '<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" '
        'xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">'
        '<native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">'
        "<interface>"
        '<Loopback nc:operation="replace">'
        f"<name>{number}</name>"
        f"<description>{escape(desired['description'])}</description>"
        "<ip><address><primary>"
        f"<address>{ipv4.ip}</address>"
        f"<mask>{ipv4.network.netmask}</mask>"
        "</primary></address></ip>"
        f"{shutdown}"
        "</Loopback></interface></native></config>"
    )


def apply_interface(
    router,
    desired_interface,
    netconf_edit_config=None,
):
    """Apply complete desired interface state using NETCONF."""
    netconf_edit_config = netconf_edit_config or _real_edit_config
    try:
        config_xml = _build_config(desired_interface)
    except (KeyError, ValueError, TypeError):
        return _error("backend_failed")
    try:
        netconf_edit_config(router, config_xml)
    except Exception as exc:
        return _map_exception(exc)
    return {"status": "ok", "result": "applied"}
