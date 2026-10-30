import yaml

ROUTERS = {
    "10.0.29.101",
    "10.0.29.102",
    "10.0.29.103",
    "10.0.29.104",
    "10.0.29.105",
}

METHOD_ACTIONS = {
    "restconf": {"status", "plan", "apply"},
    "netconf": {"status", "plan", "apply"},
    "ansible": {"apply"},
    "netmiko-textfsm": {"status", "delete"},
}


def _error(code):
    return {"status": "error", "result": code}


def _missing(mapping, key):
    return key not in mapping or mapping[key] is None or mapping[key] == ""


def validate_request(data):
    """
    Validate one IPA2026 desired-state request.

    Return a response dictionary according to
    specs/response-spec-v1.md.
    """
    if not isinstance(data, dict):
        return _error("invalid_yaml")

    version = data.get("version")
    if type(version) is not int or version != 1:
        return _error("invalid_version")

    if _missing(data, "router"):
        return _error("missing_router")
    router = data["router"]
    if not isinstance(router, str) or router not in ROUTERS:
        return _error("invalid_router")

    if _missing(data, "method"):
        return _error("missing_method")
    method = data["method"]
    if not isinstance(method, str) or method not in METHOD_ACTIONS:
        return _error("invalid_method")

    if _missing(data, "action"):
        return _error("missing_action")
    action = data["action"]
    if not isinstance(action, str) or action not in METHOD_ACTIONS[method]:
        return _error("invalid_action")

    if _missing(data, "desired"):
        return _error("missing_desired")
    desired = data["desired"]
    if not isinstance(desired, dict):
        return _error("missing_desired")

    if _missing(desired, "interface"):
        return _error("missing_interface")
    interface = desired["interface"]
    if not isinstance(interface, dict):
        return _error("missing_interface")

    if _missing(interface, "name"):
        return _error("missing_interface_name")

    if action in ("plan", "apply"):
        if _missing(interface, "ipv4"):
            return _error("missing_ipv4")
        if _missing(interface, "description"):
            return _error("missing_description")
        if _missing(interface, "admin_state"):
            return _error("missing_admin_state")
        state = interface["admin_state"]
        if not isinstance(state, str) or state not in ("up", "down"):
            return _error("invalid_admin_state")

    return {"status": "ok", "result": "accepted"}


def process_request_file(path):
    """
    Read a YAML request file, validate it,
    and return a response dictionary.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, UnicodeDecodeError, OSError, ValueError):
        return _error("invalid_yaml")
    return validate_request(data)
