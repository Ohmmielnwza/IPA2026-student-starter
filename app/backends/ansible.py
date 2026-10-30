import json
import os
import subprocess
import sys
from ipaddress import IPv4Interface
from pathlib import Path

ANSIBLE_DIR = Path(__file__).resolve().parents[2] / "ansible"


def _error(code):
    return {"status": "error", "result": code}


def _real_run_playbook(variables):
    """Run ansible/apply_interface.yml; raise on failure."""
    extra = dict(variables)
    extra["ansible_host"] = variables["router"]
    try:
        proc = subprocess.run(
            [
                "ansible-playbook",
                "-i",
                str(ANSIBLE_DIR / "inventory.ini"),
                str(ANSIBLE_DIR / "apply_interface.yml"),
                "-e",
                json.dumps(extra),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        raise ConnectionError("ansible timed out") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("ansible-playbook not installed") from exc
    if proc.returncode == 0:
        return
    text = (proc.stdout + proc.stderr).lower()
    if (
        "authentication failed" in text
        or "permission denied" in text
        or "invalid credentials" in text
    ):
        raise PermissionError(text[-500:])
    if proc.returncode == 4 or "unreachable" in text:
        raise ConnectionError(text[-500:])
    raise RuntimeError(text[-500:])


def _map_exception(exc):
    if isinstance(exc, PermissionError):
        return _error("authentication_failed")
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return _error("connection_failed")
    return _error("backend_failed")


def apply_interface(
    router,
    desired_interface,
    run_playbook=None,
):
    """Apply complete desired interface state using Ansible."""
    run_playbook = run_playbook or _real_run_playbook
    try:
        ipv4 = IPv4Interface(desired_interface["ipv4"])
        variables = {
            "router": router,
            "interface_name": desired_interface["name"],
            "description": desired_interface["description"],
            "ipv4_address": str(ipv4.ip),
            "netmask": str(ipv4.network.netmask),
            "shutdown": desired_interface["admin_state"] == "down",
        }
    except (KeyError, ValueError, TypeError):
        return _error("backend_failed")
    try:
        run_playbook(variables)
    except Exception as exc:
        return _map_exception(exc)
    return {"status": "ok", "result": "applied"}
