import importlib.util
import unittest
from unittest.mock import patch
from pathlib import Path

spec = importlib.util.spec_from_file_location('cloud_api', Path(__file__).parents[1] / 'scripts/cloud-api.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class CloudApiTests(unittest.TestCase):
    def test_secrets_are_not_in_summary(self):
        result = api.safe_resource({'id': 'env-1', 'attributes': {
            'node_version': '22', 'environment_variables': [{'value': 'SECRET'}],
            'connection': {'password': 'SECRET'}, 'secret': 'SECRET'}})
        self.assertEqual(result['attributes'], {'node_version': '22'})

    def test_only_documented_bridge_routes_and_fields(self):
        api.validate('PATCH', 'environments/env-1', {'node_version': '22'})
        for route, payload in [('https://evil.example', {'node_version': '22'}),
                               ('environments/env-1', {'environment_variables': []}),
                               ('instances/inst-1', {'node_version': '22'})]:
            with self.assertRaises(ValueError):
                api.validate('PATCH', route, payload)

    def test_auth_is_not_in_process_arguments(self):
        with patch.object(api.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '{"data":{}}\n200'
            api.request('test-token', 'GET', 'instances/inst-1')
            self.assertNotIn('test-token', str(run.call_args.args))
            self.assertIn('test-token', run.call_args.kwargs['input'])

    def test_api_error_body_is_not_disclosed(self):
        with patch.object(api.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '{"secret":"SECRET"}\n403'
            with self.assertRaisesRegex(RuntimeError, 'HTTP 403') as caught:
                api.request('test-token', 'GET', 'instances/inst-1')
            self.assertNotIn('SECRET', str(caught.exception))

    def test_wrong_organization_stops_before_mutation(self):
        with patch.object(api.sys, 'argv', ['cloud-api.py', 'GET', 'instances/inst-1', '--organization', 'org-expected']), \
             patch.object(api, 'load_token', return_value='test-token'), \
             patch.object(api, 'request', return_value={'data': {'id': 'org-other'}}) as request:
            with self.assertRaisesRegex(ValueError, 'organization'):
                api.main()
            self.assertEqual(request.call_count, 1)
