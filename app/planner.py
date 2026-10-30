MANAGED_FIELDS = ("ipv4", "description", "admin_state")


def _result(operation, changes):
    return {
        "status": "ok",
        "result": "planned",
        "operation": operation,
        "changes": changes,
    }


def build_plan(desired_interface, current_interface):
    """
    Compare desired interface state with normalized current state
    and return a plan according to specs/plan-spec-v1.md.
    """
    if current_interface is None:
        changes = {
            field: {"to": desired_interface[field]}
            for field in MANAGED_FIELDS
        }
        return _result("create", changes)

    changes = {}
    for field in MANAGED_FIELDS:
        desired = desired_interface[field]
        current = current_interface.get(field)
        if desired != current:
            changes[field] = {"from": current, "to": desired}

    return _result("update" if changes else "no_change", changes)
