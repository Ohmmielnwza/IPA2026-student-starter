import os
from ipaddress import IPv4Interface, IPv4Network

from app.backends import planning

STATUS_URL = (
    "https://{router}/restconf/data/"
    "ietf-interfaces:interfaces/interface={name}"
)
NATIVE_URL = (
    "https://{router}/restconf/data/"
    "Cisco-IOS-XE-native:native/interface/Loopback={number}"
)
HEADERS = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-data+json",
}


def _error(code):
    return {"status": "error", "result": code}


def _credentials():
    return (
        os.environ.get("ROUTER_USER", ""),
        os.environ.get("ROUTER_PASS", ""),
    )


def _real_get(url):
    import requests

    return requests.get(
        url,
        auth=_credentials(),
        headers=HEADERS,
        verify=False,
        timeout=10,
    )


def _real_put(url, json):
    import requests

    return requests.put(
        url,
        json=json,
        auth=_credentials(),
        headers=HEADERS,
        verify=False,
        timeout=10,
    )


def _map_exception(exc):
    if isinstance(exc, PermissionError):
        return _error("authentication_failed")
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return _error("connection_failed")
    try:
        import requests

        if isinstance(
            exc,
            (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ),
        ):
            return _error("connection_failed")
    except ImportError:
        pass
    return _error("backend_failed")


def _status_error(code):
    if code in (401, 403):
        return _error("authentication_failed")
    return _error("backend_failed")


def _normalize(data):
    item = data["ietf-interfaces:interface"]
    ipv4 = None
    addresses = (item.get("ietf-ip:ipv4") or {}).get("address") or []
    if addresses:
        first = addresses[0]
        prefix = IPv4Network(
            f"0.0.0.0/{first['netmask']}"
        ).prefixlen
        ipv4 = f"{first['ip']}/{prefix}"
    return {
        "name": item["name"],
        "ipv4": ipv4,
        "description": item.get("description"),
        "admin_state": "up" if item.get("enabled") else "down",
    }


def get_interface_state(
    router,
    interface_name,
    http_get=None,
):
    """Return normalized interface status using RESTCONF."""
    http_get = http_get or _real_get
    url = STATUS_URL.format(router=router, name=interface_name)
    try:
        response = http_get(url)
        code = response.status_code
        if code == 404:
            return {
                "status": "ok",
                "result": "not_found",
                "interface": None,
            }
        if code != 200:
            return _status_error(code)
        interface = _normalize(response.json())
    except (KeyError, ValueError, TypeError, AttributeError):
        return _error("backend_failed")
    except Exception as exc:
        return _map_exception(exc)
    return {
        "status": "ok",
        "result": "found",
        "interface": interface,
    }


def plan_interface(
    router,
    desired_interface,
    http_get=None,
):
    """Return create/update/no_change plan using RESTCONF status."""
    return planning.plan_interface(
        router,
        desired_interface,
        lambda r, name: get_interface_state(r, name, http_get),
    )


def apply_interface(
    router,
    desired_interface,
    http_put=None,
):
    """Apply complete desired interface state using RESTCONF."""
    http_put = http_put or _real_put
    try:
        number = int(desired_interface["name"][len("Loopback"):])
        ipv4 = IPv4Interface(desired_interface["ipv4"])
        payload = {
            "name": number,
            "description": desired_interface["description"],
            "ip": {
                "address": {
                    "primary": {
                        "address": str(ipv4.ip),
                        "mask": str(ipv4.network.netmask),
                    }
                }
            },
        }
        if desired_interface["admin_state"] == "down":
            payload["shutdown"] = [None]
        url = NATIVE_URL.format(router=router, number=number)
    except (KeyError, ValueError, TypeError):
        return _error("backend_failed")
    try:
        response = http_put(
            url, json={"Cisco-IOS-XE-native:Loopback": payload}
        )
        code = response.status_code
    except Exception as exc:
        return _map_exception(exc)
    if code in (200, 201, 204):
        return {"status": "ok", "result": "applied"}
    return _status_error(code)
