import os
import re

ABBREVIATIONS = {
    "lo": "Loopback",
    "gi": "GigabitEthernet",
    "te": "TenGigabitEthernet",
    "fa": "FastEthernet",
    "eth": "Ethernet",
}


def _error(code):
    return {"status": "error", "result": code}


def _expand(name):
    match = re.match(r"^([A-Za-z]+)(\d.*)$", str(name).strip())
    if not match:
        return str(name).strip()
    prefix, rest = match.groups()
    full = ABBREVIATIONS.get(prefix.lower(), prefix)
    return f"{full}{rest}"


def _same(a, b):
    return _expand(a).lower() == _expand(b).lower()


def _device(router):
    return {
        "device_type": "cisco_ios",
        "host": router,
        "username": os.environ.get("ROUTER_USER", ""),
        "password": os.environ.get("ROUTER_PASS", ""),
        "timeout": 20,
    }


def _as_records(output):
    # Netmiko returns the raw string when TextFSM cannot parse the output
    # (for example "% Invalid input" for a missing interface).
    return output if isinstance(output, list) else []


def _real_get(router, interface_name):
    from netmiko import ConnectHandler

    with ConnectHandler(**_device(router)) as conn:
        ip_info = conn.send_command(
            f"show ip interface {interface_name}", use_textfsm=True
        )
        descriptions = conn.send_command(
            "show interfaces description", use_textfsm=True
        )
        if isinstance(descriptions, str) and descriptions.strip():
            if "Invalid input" in descriptions:
                raise RuntimeError("show interfaces description failed")
    return _as_records(ip_info), _as_records(descriptions)


def _real_delete(router, interface_name):
    from netmiko import ConnectHandler

    ip_info, _ = _real_get(router, interface_name)
    if not any(_same(r.get("interface", ""), interface_name) for r in ip_info):
        return "not_found"
    with ConnectHandler(**_device(router)) as conn:
        conn.send_config_set([f"no interface {interface_name}"])
    ip_info, _ = _real_get(router, interface_name)
    if any(_same(r.get("interface", ""), interface_name) for r in ip_info):
        raise RuntimeError("interface still present after delete")
    return "deleted"


def _map_exception(exc):
    if isinstance(exc, PermissionError):
        return _error("authentication_failed")
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return _error("connection_failed")
    try:
        from netmiko.exceptions import (
            NetmikoAuthenticationException,
            NetmikoTimeoutException,
        )

        if isinstance(exc, NetmikoAuthenticationException):
            return _error("authentication_failed")
        if isinstance(exc, NetmikoTimeoutException):
            return _error("connection_failed")
    except ImportError:
        pass
    return _error("backend_failed")


def _normalize(interface_name, ip_info, descriptions):
    record = next(
        (
            r
            for r in ip_info
            if _same(r.get("interface", ""), interface_name)
        ),
        None,
    )
    if record is None:
        return None
    addresses = record.get("ip_address") or []
    prefixes = record.get("prefix_length") or []
    if isinstance(addresses, str):
        addresses = [addresses]
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    ipv4 = f"{addresses[0]}/{prefixes[0]}" if addresses and prefixes else None
    description = next(
        (
            d.get("description") or None
            for d in descriptions
            if _same(d.get("port", ""), interface_name)
        ),
        None,
    )
    state = str(record.get("link_status", "")).lower()
    return {
        "name": interface_name,
        "ipv4": ipv4,
        "description": description,
        "admin_state": (
            "down" if "administratively down" in state else "up"
        ),
    }


def get_interface_state(
    router,
    interface_name,
    netmiko_get=None,
):
    """Return normalized interface status using Netmiko + TextFSM."""
    netmiko_get = netmiko_get or _real_get
    try:
        ip_info, descriptions = netmiko_get(router, interface_name)
    except Exception as exc:
        return _map_exception(exc)
    try:
        interface = _normalize(interface_name, ip_info, descriptions)
    except (AttributeError, KeyError, IndexError, TypeError):
        return _error("backend_failed")
    if interface is None:
        return {"status": "ok", "result": "not_found", "interface": None}
    return {"status": "ok", "result": "found", "interface": interface}


def delete_interface(
    router,
    interface_name,
    netmiko_delete=None,
):
    """Delete an interface using Netmiko."""
    netmiko_delete = netmiko_delete or _real_delete
    try:
        outcome = netmiko_delete(router, interface_name)
    except Exception as exc:
        return _map_exception(exc)
    if outcome == "deleted":
        return {"status": "ok", "result": "deleted"}
    if outcome == "not_found":
        return {"status": "ok", "result": "not_found", "interface": None}
    return _error("backend_failed")
