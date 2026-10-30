"""Part 4 student implementation."""

from app.backends import ansible, netconf, netmiko_textfsm, restconf

BACKENDS = {
    'restconf': restconf,
    'netconf': netconf,
    'ansible': ansible,
    'netmiko-textfsm': netmiko_textfsm,
}


def dispatch_request(data):
    backend = BACKENDS[data['method']]
    action = data['action']
    router = data['router']
    interface = data['desired']['interface']

    if action == 'status':
        return backend.get_interface_state(router, interface['name'])
    if action == 'delete':
        return backend.delete_interface(router, interface['name'])
    if action == 'plan':
        return backend.plan_interface(router, interface)
    if action == 'apply':
        return backend.apply_interface(router, interface)
    return {'status': 'error', 'result': 'invalid_action'}
