"""Part 4 student implementation."""

import yaml

from app.core import validate_request

from app.dispatcher import dispatch_request

from app.request_handler import validate_webex_envelope


def process_request(mentioned_people, attachment_path, bot_person_id):
    error = validate_webex_envelope(
        mentioned_people, attachment_path, bot_person_id
    )
    if error is not None:
        return error

    try:
        with open(attachment_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, UnicodeDecodeError, OSError, ValueError):
        return {'status': 'error', 'result': 'invalid_yaml'}

    validation = validate_request(data)
    if validation.get('status') != 'ok':
        return validation

    try:
        return dispatch_request(data)
    except Exception:
        return {'status': 'error', 'result': 'backend_failed'}
