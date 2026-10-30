"""Part 4 student implementation."""

import json

import logging

import os

from concurrent.futures import ThreadPoolExecutor

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path

from tempfile import TemporaryDirectory

from app.integration import process_request

from app.webex_client import WEBEX_API_BASE, WebexClient

import requests

logger = logging.getLogger(__name__)

MAX_BODY = 1_000_000


class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor or process_request

    def handle_event(self, event):
        if not isinstance(event, dict):
            return None
        if event.get('resource') != 'messages' or event.get('event') != 'created':
            return None
        data = event.get('data')
        if not isinstance(data, dict):
            return None
        message_id = data.get('id')
        if not message_id:
            return None
        if data.get('personId') == self.bot_person_id:
            return None

        message = self.client.get_message(message_id)
        if message.get('personId') == self.bot_person_id:
            return None
        room_id = message.get('roomId')
        files = message.get('files') or []

        if len(files) > 1:
            result = {'status': 'error', 'result': 'multiple_attachments'}
        elif not files:
            result = self.processor(
                message.get('mentionedPeople') or [], None, self.bot_person_id
            )
        else:
            content = self.client.download_file(files[0])
            with TemporaryDirectory() as tmp:
                path = Path(tmp) / 'request.yaml'
                path.write_bytes(content)
                result = self.processor(
                    message.get('mentionedPeople') or [], path, self.bot_person_id
                )

        self.client.send_message(room_id, json.dumps(result))
        return result


def make_http_handler(submit_event):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, body):
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path == '/health':
                self._send(200, {'status': 'ok', 'result': 'healthy'})
            else:
                self._send(404, {'status': 'error', 'result': 'not_found'})

        def do_POST(self):
            if self.path != '/webhook':
                self._send(404, {'status': 'error', 'result': 'not_found'})
                return
            invalid = {'status': 'error', 'result': 'invalid_event'}
            try:
                length = int(self.headers.get('Content-Length', ''))
            except ValueError:
                self._send(400, invalid)
                return
            if not 1 <= length <= MAX_BODY:
                self._send(400, invalid)
                return
            try:
                event = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                self._send(400, invalid)
                return
            if not isinstance(event, dict):
                self._send(400, invalid)
                return
            submit_event(event)
            self._send(200, {'status': 'ok', 'result': 'accepted'})

        def log_message(self, format, *args):
            logger.info(format, *args)

    return Handler


def main():
    logging.basicConfig(level=logging.INFO)
    client = WebexClient()
    me = requests.get(
        f'{WEBEX_API_BASE}/people/me', headers=client.headers, timeout=10
    )
    me.raise_for_status()
    handler = WebexEventHandler(client, me.json()['id'])
    executor = ThreadPoolExecutor(max_workers=1)

    def run(event):
        try:
            result = handler.handle_event(event)
            logger.info('handled event, reply=%s', json.dumps(result))
        except Exception:
            logger.exception('event processing failed')

    def submit(event):
        executor.submit(run, event)

    host = os.environ.get('WEBHOOK_HOST', '0.0.0.0')
    port = int(os.environ.get('WEBHOOK_PORT', '8000'))
    server = ThreadingHTTPServer((host, port), make_http_handler(submit))
    server.serve_forever()


if __name__ == "__main__":
    main()
