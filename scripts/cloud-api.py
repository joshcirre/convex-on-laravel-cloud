#!/usr/bin/env python3
"""Small, deliberately limited bridge for Cloud CLI v0.6.1's missing options."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

BASE = 'https://cloud.laravel.com/api/'
SAFE_ATTRIBUTES = {
    'name', 'region', 'status', 'node_version', 'build_command', 'deploy_command',
    'uses_push_to_deploy', 'hibernation_timeout', 'uses_hibernation', 'size',
    'scaling_type', 'min_replicas', 'max_replicas', 'visibility', 'filesystem_keys',
}
PATCH_FIELDS = {
    'environments': {'node_version', 'uses_push_to_deploy', 'filesystem_keys'},
    'instances': {'hibernation_timeout'},
}


def load_token():
    token = os.environ.get('LARAVEL_CLOUD_TOKEN')
    if not token:
        config = Path.home() / '.config/cloud/config.json'
        tokens = json.loads(config.read_text()).get('api_tokens', [])
        if not isinstance(tokens, list) or len(tokens) != 1:
            raise ValueError('Select an organization token through LARAVEL_CLOUD_TOKEN; expected exactly one saved token.')
        token = tokens[0]
    if not isinstance(token, str) or not token or any(c in token for c in '\r\n"\\'):
        raise ValueError('Invalid Cloud token format.')
    return token


def request(token, method, route, payload=None):
    # curl works with Cloud's edge where Python's default HTTP user agent may not.
    # Supply the auth header on stdin, and JSON through a mode-0600 file, not argv.
    with tempfile.NamedTemporaryFile(mode='w+', encoding='utf-8') as body:
        args = ['curl', '--silent', '--show-error', '--connect-timeout', '15',
                '--max-time', '90', '--config', '-', '--request', method,
                '--header', 'Accept: application/vnd.api+json',
                '--header', 'Content-Type: application/json',
                '--write-out', '\n%{http_code}', BASE + route]
        if payload is not None:
            json.dump(payload, body)
            body.flush()
            args += ['--data-binary', '@' + body.name]
        result = subprocess.run(args, input=f'header = "Authorization: Bearer {token}"\n',
                                text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'Cloud request failed (curl exit {result.returncode}); inspect connectivity before retrying.')
    response, status = result.stdout.rsplit('\n', 1)
    if not status.startswith('2'):
        # Raw errors can include submitted data or credentials. Do not print them.
        raise RuntimeError(f'Cloud API returned HTTP {status}; check permissions, IDs, and the documented payload. Response body withheld.')
    return json.loads(response) if response else {}


def safe_resource(resource):
    if not isinstance(resource, dict):
        return {}
    attrs = resource.get('attributes', {})
    return {
        'id': resource.get('id'), 'type': resource.get('type'),
        'attributes': {k: v for k, v in attrs.items() if k in SAFE_ATTRIBUTES},
        'relationships': {
            key: value.get('data') for key, value in resource.get('relationships', {}).items()
            if isinstance(value, dict)
        },
    }


def validate(method, route, payload):
    if not re.fullmatch(r'(environments|instances)/[a-zA-Z0-9-]+(?:\?include=[a-z,]+)?', route):
        raise ValueError('Only environment/instance resource routes are supported.')
    if method == 'PATCH':
        if '?' in route or not isinstance(payload, dict) or not payload:
            raise ValueError('PATCH requires a resource route and a nonempty JSON object.')
        allowed = PATCH_FIELDS[route.split('/')[0]]
        if set(payload) - allowed:
            raise ValueError('Unsupported PATCH fields; use the Cloud CLI for other settings.')
    elif payload is not None:
        raise ValueError('GET does not accept a payload.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('method', choices=['GET', 'PATCH'])
    parser.add_argument('route', help='e.g. environments/env-ID?include=instances,buckets')
    parser.add_argument('--organization', required=True, help='Expected org-ID (checked before any resource request)')
    parser.add_argument('--data-file', help='JSON file for PATCH; never put secrets in this file')
    args = parser.parse_args()
    payload = json.loads(Path(args.data_file).read_text()) if args.data_file else None
    validate(args.method, args.route, payload)
    token = load_token()
    org = request(token, 'GET', 'meta/organization').get('data', {})
    if org.get('id') != args.organization:
        raise ValueError('Cloud token organization does not match --organization. No resource request sent.')
    result = request(token, args.method, args.route, payload)
    data = result.get('data', {})
    print(json.dumps({'data': safe_resource(data),
                      'included': [safe_resource(r) for r in result.get('included', [])]}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, RuntimeError):
        # Avoid tracebacks containing credentials or complete API response objects.
        error = sys.exc_info()[1]
        if isinstance(error, (ValueError, RuntimeError)) and not isinstance(error, json.JSONDecodeError):
            print(str(error), file=sys.stderr)
        else:
            print('Could not read configuration or parse the response. Check local files and Cloud access.', file=sys.stderr)
        sys.exit(1)
