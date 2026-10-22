"""Offline behavioral tests: python3 -m unittest discover -s scripts -p 'test_*.py'."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
import ssl
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import build_opener
import gmi_api as g


class Fixture(BaseHTTPRequestHandler):
    states = []
    calls = []
    posts = 0
    response = None
    schema = {'model': 'demo', 'status': 'active', 'qworkers': 1,
              'parameters': [{'name': 'prompt', 'type': 'string', 'required': True},
                             {'name': 'steps', 'type': 'integer', 'required': True, 'default_value': 2}]}

    def log_message(self, *args):
        pass

    def send(self, code, value, extra=None):
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.send_response(code)
        self.send_header('Content-Length', str(len(raw)))
        for key, val in (extra or {}).items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        Fixture.calls.append((self.path, dict(self.headers)))
        if self.path == '/models/demo':
            self.send(200, self.schema)
        elif self.path.startswith('/requests/'):
            item = Fixture.states.pop(0) if len(Fixture.states) > 1 else Fixture.states[0]
            if isinstance(item, tuple):
                self.send(*item)
            else:
                self.send(200, item)
        elif self.path == '/file.mp4':
            self.send(200, b'fixture-video')
        elif self.path == '/bad':
            self.send(404, {})
        else:
            self.send(200, {'data': []})

    def do_POST(self):
        Fixture.posts += 1
        self.rfile.read(int(self.headers['Content-Length']))
        code, value = Fixture.response or (200, {'request_id': 'req-1', 'model': 'demo', 'status': 'queued'})
        self.send(code, value)


class LocalAPI(g.API):
    def call(self, method, base, path, body=None, timeout=30):
        return super().call(method, BASE, path, body, timeout)


class Clock:
    value = 0
    def now(self):
        return self.value
    def sleep(self, n):
        self.value += n


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global BASE
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        BASE = 'http://127.0.0.1:' + str(cls.server.server_port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'GMI_API_KEY': 'FAKE-secret-1234'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.api = LocalAPI()
        self.original_docs_fetch = g.fetch_docs_index
        docs = patch.object(g, 'fetch_docs_index', return_value='- [WAN 3.0 Video](https://docs.gmicloud.ai/model-quickstarts/video/wan3-0-video.md)')
        docs.start()
        self.addCleanup(docs.stop)
        self.store = g.Store(Path(self.tmp.name) / 'state')
        Fixture.calls, Fixture.posts, Fixture.response = [], 0, None
        Fixture.states = [{'request_id': 'req-1', 'model': 'demo', 'status': 'success', 'outcome': {}}]

    def submit(self):
        return g.submit(self.api, self.store, 'demo', {'prompt': 'private prompt'}, 'scene')

    def test_pending_saved_private_without_prompt(self):
        job = self.submit()
        self.assertEqual(g.job_exit(job), 3)
        self.assertEqual(job['request_id'], 'req-1')
        text = self.store.path('scene').read_text()
        self.assertNotIn('private prompt', text)
        self.assertNotIn('FAKE-secret', text)
        if os.name != 'nt':
            self.assertEqual(self.store.path('scene').stat().st_mode & 0o777, 0o600)

    def test_duplicate_local_id_does_not_repost(self):
        self.submit()
        with self.assertRaises(g.Error):
            self.submit()
        self.assertEqual(Fixture.posts, 1)

    def test_immediate_terminal_states(self):
        for index, status in enumerate(sorted(g.SUCCESS | g.FAILURE)):
            Fixture.response = (200, {'request_id': f'req-{index}', 'model': 'demo', 'status': status})
            job = g.submit(self.api, self.store, 'demo', {'prompt': 'x'}, f'job-{index}')
            self.assertEqual(g.job_exit(job), 0 if status in g.SUCCESS else 1)

    def test_resume_new_store_and_api(self):
        self.submit()
        Fixture.states = [{'request_id': 'req-1', 'model': 'demo', 'status': status} for status in ('processing', 'success')]
        store = g.Store(self.store.root)
        job = store.load('scene')
        clock = Clock()
        with redirect_stderr(io.StringIO()):
            g.wait_job(LocalAPI(), store, job, 45, clock.sleep, clock.now)
        self.assertEqual(job['status'], 'success')
        self.assertEqual(Fixture.posts, 1)

    def test_timeout_keeps_id(self):
        job = self.submit()
        Fixture.states = [{'request_id': 'req-1', 'model': 'demo', 'status': 'queued'}]
        clock = Clock()
        with redirect_stderr(io.StringIO()):
            g.wait_job(self.api, self.store, job, 3, clock.sleep, clock.now)
        self.assertEqual(clock.value, 3)
        self.assertEqual(g.job_exit(job), 3)
        self.assertEqual(self.store.load('scene')['request_id'], 'req-1')

    def test_unknown_status_stops(self):
        job = self.submit()
        Fixture.states = [{'request_id': 'req-1', 'model': 'demo', 'status': 'surprise'}]
        clock = Clock()
        g.wait_job(self.api, self.store, job, 45, clock.sleep, clock.now)
        self.assertEqual(g.job_exit(job), 1)
        self.assertEqual(clock.value, 0)

    def test_failed_poll_stops(self):
        job = self.submit()
        Fixture.states = [{'request_id': 'req-1', 'model': 'demo', 'status': 'failed'}]
        clock = Clock()
        g.wait_job(self.api, self.store, job, 45, clock.sleep, clock.now)
        self.assertEqual(g.job_exit(job), 1)

    def test_transient_read_retried_without_post(self):
        job = self.submit()
        Fixture.states = [(503, {}), {'request_id': 'req-1', 'model': 'demo', 'status': 'success'}]
        clock = Clock()
        g.wait_job(self.api, self.store, job, 45, clock.sleep, clock.now)
        self.assertEqual(job['status'], 'success')
        self.assertEqual(Fixture.posts, 1)

    def test_three_transient_errors_stop(self):
        job = self.submit()
        Fixture.states = [(503, {})]
        clock = Clock()
        with self.assertRaises(g.Error):
            g.wait_job(self.api, self.store, job, 45, clock.sleep, clock.now)
        self.assertLess(clock.value, 45)
        self.assertEqual(Fixture.posts, 1)

    def test_retry_after_respects_budget(self):
        job = self.submit()
        Fixture.states = [(429, {}, {'Retry-After': '120'})]
        clock = Clock()
        g.wait_job(self.api, self.store, job, 4, clock.sleep, clock.now)
        self.assertEqual(clock.value, 4)
        self.assertEqual(job['status'], 'queued')

    def test_daily_quota_no_retry(self):
        job = self.submit()
        Fixture.states = [(429, {'rate_limit': {'limit_type': 'RPD'}})]
        clock = Clock()
        with self.assertRaises(g.Error):
            g.wait_job(self.api, self.store, job, 45, clock.sleep, clock.now)
        self.assertEqual(clock.value, 0)

    def test_submit_http_error_is_uncertain_and_not_retried(self):
        Fixture.response = (500, {'error': 'FAKE-secret-1234', 'request_id': 'maybe-1'})
        with redirect_stdout(io.StringIO()), self.assertRaises(g.Error):
            self.submit()
        job = self.store.load('scene')
        self.assertEqual(job['status'], 'submission_unknown')
        self.assertEqual(job['request_id_hint'], 'maybe-1')
        self.assertEqual(Fixture.posts, 1)

    def test_missing_id_persists_uncertain(self):
        Fixture.response = (200, {'status': 'queued'})
        with redirect_stdout(io.StringIO()), self.assertRaises(g.Error):
            self.submit()
        self.assertEqual(self.store.load('scene')['status'], 'submission_unknown')

    def test_interrupt_preserves_confirmed_id(self):
        job = self.submit()
        Fixture.states = [{'request_id': 'req-1', 'model': 'demo', 'status': 'queued'}]
        with redirect_stderr(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            g.wait_job(self.api, self.store, job, 45, sleep=lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
        self.assertEqual(self.store.load('scene')['request_id'], 'req-1')

    def test_validation_before_post(self):
        for payload in ({}, {'prompt': 5}, {'prompt': 'x', 'steps': True}, {'prompt': 'x', 'typo': 4}):
            with self.assertRaises(g.Error):
                g.submit(self.api, self.store, 'demo', payload)
        self.assertEqual(Fixture.posts, 0)

    def test_required_default_and_typed_enum(self):
        result = g.validate_payload({'prompt': 'x'}, Fixture.schema)
        self.assertEqual(result['steps'], 2)
        with self.assertRaises(g.Error):
            g.validate_payload({'n': 3}, {'parameters': [{'name': 'n', 'type': 'integer', 'enum': [1, 2]}]})

    def test_redaction_in_output(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            g.emit({'message': 'echo FAKE-secret-1234', 'access_token': 'other-secret'})
        self.assertNotIn('FAKE-secret', buf.getvalue())
        self.assertNotIn('other-secret', buf.getvalue())

    def test_artifact_url_selection(self):
        self.assertEqual(g.artifact_urls({'audio_url': 'https://x/a', 'media': [{'url': 'https://x/a'}], 'thumbnail_image_url': 'https://x/t'}), ['https://x/a'])
        self.assertEqual(g.artifact_urls({'thumbnail_image_url': 'https://x/t'}), ['https://x/t'])

    def test_download_no_auth_and_repeat_uses_hash(self):
        job = self.submit()
        job.update(status='success', outcome={'video_url': BASE + '/file.mp4'})
        with patch.object(g, 'secure_url', side_effect=lambda x: x):
            result = g.download(self.store, job, Path(self.tmp.name) / 'out', 100)
            count = len(Fixture.calls)
            again = g.download(self.store, job, Path(self.tmp.name) / 'out', 100)
        self.assertFalse(result['failures'])
        self.assertEqual(len(Fixture.calls), count)
        self.assertEqual(result, again)
        headers = Fixture.calls[-1][1]
        self.assertNotIn('Authorization', headers)
        self.assertNotIn('X-Organization-Id', headers)
        path = Path(next(iter(result['files'])))
        self.assertEqual(path.read_bytes(), b'fixture-video')

    def test_partial_download_preserves_success(self):
        job = self.submit()
        job.update(status='success', outcome={'media_urls': [BASE + '/file.mp4', BASE + '/bad']})
        with patch.object(g, 'secure_url', side_effect=lambda x: x):
            result = g.download(self.store, job, Path(self.tmp.name) / 'out', 100)
        self.assertEqual(len(result['files']), 1)
        self.assertEqual(len(result['failures']), 1)
        self.assertFalse(list((Path(self.tmp.name) / 'out').glob('.download-*')))

    def test_size_limit_and_https(self):
        job = self.submit()
        job.update(status='success', outcome={'video_url': BASE + '/file.mp4'})
        result = g.download(self.store, job, Path(self.tmp.name) / 'out', 100)
        self.assertEqual(len(result['failures']), 1)
        with patch.object(g, 'secure_url', side_effect=lambda x: x):
            result = g.download(self.store, job, Path(self.tmp.name) / 'out', 2)
        self.assertEqual(len(result['failures']), 1)
        for url in ('http://host/file', 'https://user:password@host/file', 'file:///etc/passwd'):
            with self.assertRaises(g.Error):
                g.secure_url(url)

    def test_redirect_policy(self):
        with self.assertRaises(g.Error):
            g.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other/secret')
        with self.assertRaises(g.Error):
            g.ArtifactRedirect().redirect_request(None, None, 302, '', {}, 'http://host/file')

    def test_mismatched_record_does_not_replace_job(self):
        job = self.submit()
        with self.assertRaises(g.Error):
            g.apply_record(job, {'request_id': 'other', 'status': 'success'}, self.store)
        self.assertEqual(self.store.load('scene')['request_id'], 'req-1')

    def test_main_pending_exit_and_offline_jobs(self):
        self.submit()
        output = io.StringIO()
        with redirect_stdout(output), patch.object(g, 'API', side_effect=AssertionError('Should be offline')):
            result = g.main(['--state-dir', str(self.store.root), 'jobs'])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())['jobs'][0]['job_id'], 'scene')

    def test_cli_terminal_failure_exit(self):
        payload = Path(self.tmp.name) / 'payload.json'
        payload.write_text('{"prompt":"x"}')
        Fixture.response = (200, {'request_id': 'req-1', 'model': 'demo', 'status': 'failed'})
        with patch.object(g, 'API', LocalAPI), redirect_stdout(io.StringIO()):
            code = g.main(['--state-dir', str(self.store.root), 'submit', '--model', 'demo',
                           '--payload-file', str(payload), '--job-id', 'failed'])
        self.assertEqual(code, 1)

    def test_cli_attach_recovers_uncertain_intent(self):
        self.store.create({'job_id': 'scene', 'model': 'demo', 'status': 'submission_unknown', 'request_id': None})
        with patch.object(g, 'API', LocalAPI), redirect_stdout(io.StringIO()):
            code = g.main(['--state-dir', str(self.store.root), 'attach', 'scene', '--request-id', 'req-1'])
        self.assertEqual(code, 0)
        self.assertEqual(self.store.load('scene')['request_id'], 'req-1')
        self.assertEqual(Fixture.posts, 0)

    def test_cli_attach_refuses_inconsistent_response(self):
        self.store.create({'job_id': 'scene', 'model': 'demo', 'status': 'submission_unknown', 'request_id': None})
        with patch.object(g, 'API', LocalAPI), redirect_stdout(io.StringIO()):
            code = g.main(['--state-dir', str(self.store.root), 'attach', 'scene', '--request-id', 'other'])
        self.assertEqual(code, 1)
        self.assertIsNone(self.store.load('scene')['request_id'])

    def test_submission_timeout_never_reposts(self):
        with patch.object(self.api, 'call', side_effect=g.Error('timeout', transient=True)):
            # Preserve successful schema GET while making the paid call fail.
            with patch.object(self.api, 'read', return_value=Fixture.schema):
                with redirect_stdout(io.StringIO()), self.assertRaises(g.Error):
                    self.submit()
        self.assertEqual(self.store.load('scene')['status'], 'submission_unknown')

    def test_corrupted_download_is_fetched_again(self):
        job = self.submit()
        job.update(status='success', outcome={'video_url': BASE + '/file.mp4'})
        with patch.object(g, 'secure_url', side_effect=lambda x: x):
            result = g.download(self.store, job, Path(self.tmp.name) / 'out', 100)
            path = Path(next(iter(result['files'])))
            path.write_bytes(b'corrupt')
            again = g.download(self.store, job, path.parent, 100)
        self.assertFalse(again['failures'])
        self.assertEqual(path.read_bytes(), b'fixture-video')

    def test_native_state_locations(self):
        home = Path(self.tmp.name) / 'user'
        self.assertEqual(Path(g.default_state_dir('darwin', {}, home)),
                         home / 'Library' / 'Application Support' / 'gmi-skill' / 'jobs')
        local = Path(self.tmp.name) / 'LocalAppData'
        self.assertEqual(Path(g.default_state_dir('win32', {'LOCALAPPDATA': str(local)}, home)),
                         local / 'gmi-skill' / 'jobs')
        self.assertEqual(Path(g.default_state_dir('win32', {}, home)),
                         home / 'AppData' / 'Local' / 'gmi-skill' / 'jobs')
        xdg = Path(self.tmp.name) / 'xdg'
        self.assertEqual(Path(g.default_state_dir('linux', {'XDG_STATE_HOME': str(xdg)}, home)),
                         xdg / 'gmi-skill' / 'jobs')
        for env in ({}, {'XDG_STATE_HOME': 'relative'}):
            self.assertEqual(Path(g.default_state_dir('linux', env, home)),
                             home / '.local' / 'state' / 'gmi-skill' / 'jobs')

    def test_legacy_registry_and_explicit_override(self):
        home = Path(self.tmp.name) / 'user'
        legacy = home / '.local' / 'state' / 'gmi-skill' / 'jobs'
        legacy.mkdir(parents=True)
        self.assertEqual(Path(g.default_state_dir('darwin', {}, home)), legacy)
        explicit = Path(self.tmp.name) / 'chosen'
        self.assertEqual(Path(g.default_state_dir('darwin', {'GMI_SKILL_STATE_DIR': str(explicit)}, home)), explicit)
        native = home / 'Library' / 'Application Support' / 'gmi-skill' / 'jobs'
        native.mkdir(parents=True)
        self.assertEqual(Path(g.default_state_dir('darwin', {}, home)), native)

    def test_portable_ids(self):
        for value in ('CON', 'nul.txt', 'Com1', 'LPT9.data', 'trailing.', '../escape', 'a/b', 'a\\b'):
            with self.assertRaises(g.Error):
                g.identifier(value)
        self.assertEqual(g.identifier('scene-01'), 'scene-01')

    def test_utf8_bom_payload_and_portable_json_output(self):
        path = Path(self.tmp.name) / 'payload.json'
        path.write_text('{"prompt":"日本語 café"}', encoding='utf-8-sig')
        value = g.json_file(path)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            g.emit(value)
        buffer.getvalue().encode('ascii')
        self.assertEqual(json.loads(buffer.getvalue()), value)

    def test_doctor_no_network_or_secret_output(self):
        buffer = io.StringIO()
        with patch.object(g, 'API', side_effect=AssertionError('No network')), redirect_stdout(buffer):
            code = g.main(['--state-dir', str(self.store.root), 'doctor'])
        result = json.loads(buffer.getvalue())
        self.assertEqual(code, 0)
        self.assertIs(result['credentials_available'], True)
        self.assertNotIn('FAKE-secret', buffer.getvalue())
        self.assertFalse(self.store.root.exists())

    def test_tls_context_requires_certificate_and_hostname_verification(self):
        with patch.dict(os.environ, {'GMI_CA_BUNDLE': ''}):
            context = g.tls_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_explicit_bundle_is_used(self):
        with patch.dict(os.environ, {'GMI_CA_BUNDLE': str(Path(self.tmp.name) / 'trusted.pem')}):
            with patch.object(g.ssl, 'create_default_context') as create:
                g.tls_context()
        create.assert_called_once_with(cafile=str(Path(self.tmp.name) / 'trusted.pem'))

    def test_invalid_ca_bundle_is_actionable(self):
        with patch.dict(os.environ, {'GMI_CA_BUNDLE': str(Path(self.tmp.name) / 'missing.pem')}):
            with self.assertRaises(g.Error) as caught:
                g.tls_context()
        self.assertEqual(caught.exception.code, 'TLS_CA_CONFIG')
        self.assertFalse(caught.exception.transient)

    def test_certificate_error_is_not_retried(self):
        problem = ssl.SSLCertVerificationError(1, 'certificate verify failed')
        with patch.object(self.api.opener, 'open', side_effect=g.URLError(problem)) as request:
            with self.assertRaises(g.Error) as caught:
                self.api.read(g.INFERENCE, 'models')
        self.assertEqual(caught.exception.code, 'TLS_CERTIFICATE_VERIFY_FAILED')
        self.assertFalse(caught.exception.transient)
        self.assertEqual(request.call_count, 1)

    def test_doctor_reports_tls_verification(self):
        result = g.tls_diagnostics()
        self.assertIs(result['certificate_verification'], True)
        self.assertIs(result['hostname_verification'], True)
        self.assertIsInstance(result['loaded_ca_count'], int)

    def test_artifact_certificate_error_is_actionable(self):
        job = self.submit()
        job.update(status='success', outcome={'video_url': 'https://artifact.example/video.mp4'})
        opener = unittest.mock.Mock()
        opener.open.side_effect = g.URLError(ssl.SSLCertVerificationError(1, 'certificate verify failed'))
        result = g.download(self.store, job, Path(self.tmp.name) / 'out', 100, opener=opener)
        self.assertEqual(result['failures'][0]['code'], 'TLS_CERTIFICATE_VERIFY_FAILED')
        self.assertEqual(opener.open.call_count, 1)

    def discovery_api(self):
        api = unittest.mock.Mock()
        def read(base, path):
            if base == g.INFERENCE:
                return {'data': [{'id': 'text/model', 'name': 'Text Model'}]}
            if path == 'models':
                return {'model_ids': ['wan3.0-video', 'seedance-2-5-260628', 'seedance-2-0-260128']}
            return {'model': path.split('/')[-1], 'status': 'active',
                    'qworkers': 0 if 'wan' in path else 1, 'model_type': 'video'}
        api.read.side_effect = read
        return api

    def test_catalog_includes_both_sources(self):
        result = g.catalog(self.discovery_api())
        self.assertEqual(result['source_counts'], {'text': 1, 'media': 3, 'documentation': 1})
        self.assertEqual(result['matched'], 4)
        self.assertTrue(result['complete'])

    def test_catalog_search_handles_spacing_case_and_punctuation(self):
        for query, expected in [('WAN 3.0', 'wan3.0-video'),
                                ('Seedance 2.5', 'seedance-2-5-260628'),
                                ('SEEDANCE 2.0', 'seedance-2-0-260128')]:
            result = g.catalog(self.discovery_api(), search=query)
            self.assertEqual([r['id'] for r in result['models']], [expected])

    def test_catalog_keeps_zero_worker_models(self):
        api = self.discovery_api()
        result = g.catalog(api, search='wan 3.0', details=True)
        self.assertEqual(result['models'][0]['readiness'], 'no_workers_reported')
        self.assertTrue(result['models'][0]['listed'])
        self.assertEqual(result['matched'], 1)
        self.assertEqual(api.read.call_count, 3)

    def test_catalog_no_details_does_not_guess_readiness(self):
        api = self.discovery_api()
        result = g.catalog(api, kind='media', search='wan 3.0')
        self.assertEqual(result['models'][0]['readiness'], 'unknown')
        self.assertEqual(api.read.call_count, 1)

    def test_catalog_partial_failure_preserves_other_source(self):
        api = self.discovery_api()
        original = api.read.side_effect
        def read(base, path):
            if base == g.INFERENCE:
                raise g.Error('GMI connection failed.')
            return original(base, path)
        api.read.side_effect = read
        result = g.catalog(api)
        self.assertFalse(result['complete'])
        self.assertEqual(result['matched'], 3)
        self.assertEqual(result['errors'][0]['source'], 'text')

    def test_catalog_live_results_are_not_cached(self):
        api = self.discovery_api()
        self.assertEqual(g.catalog(api, kind='media')['matched'], 3)
        api.read.side_effect = lambda *args: {'model_ids': ['brand-new-model']}
        self.assertIn('brand-new-model', [r['id'] for r in g.catalog(api, kind='media')['models']])

    def test_catalog_detail_failure_preserves_listed_entry(self):
        api = self.discovery_api()
        original = api.read.side_effect
        def read(base, path):
            if path.startswith('models/'):
                raise g.Error('GMI HTTP 403.')
            return original(base, path)
        api.read.side_effect = read
        result = g.catalog(api, kind='media', search='wan 3.0', details=True)
        self.assertEqual(result['models'][0]['id'], 'wan3.0-video')
        self.assertFalse(result['complete'])
        self.assertTrue(result['models'][0]['listed'])

    def test_documentation_only_model_remains_discoverable(self):
        with patch.object(g, 'fetch_docs_index', return_value='- [New Video Model](https://docs.gmicloud.ai/model-quickstarts/video/new-video-model.md)'):
            result = g.catalog(self.discovery_api(), search='New Video')
        self.assertEqual(result['matched'], 1)
        record = result['models'][0]
        self.assertIsNone(record['id'])
        self.assertEqual(record['api_listing'], 'not_returned')
        self.assertTrue(record['documented'])
        self.assertFalse(record['listed'])

    def test_missing_credentials_keeps_public_docs_and_flags_partial(self):
        result = g.catalog(None, search='WAN 3.0')
        self.assertEqual(result['matched'], 1)
        self.assertFalse(result['complete'])
        self.assertEqual(result['models'][0]['api_listing'], 'unknown')
        self.assertEqual(result['successful_sources'], ['documentation'])

    def test_public_name_alias_merges_to_exact_api_id(self):
        with patch.object(g, 'fetch_docs_index', return_value='- [Creative Video](https://docs.gmicloud.ai/model-quickstarts/video/wan3-0-video.md)'):
            result = g.catalog(self.discovery_api(), search='Creative Video')
        self.assertEqual(result['matched'], 1)
        self.assertEqual(result['models'][0]['id'], 'wan3.0-video')
        self.assertTrue(result['models'][0]['documented'])

    def test_documentation_failure_preserves_api_results(self):
        with patch.object(g, 'fetch_docs_index', side_effect=g.Error('Docs unavailable.')):
            result = g.catalog(self.discovery_api())
        self.assertEqual(result['matched'], 4)
        self.assertFalse(result['complete'])
        self.assertEqual(result['errors'][0]['source'], 'documentation')

    def test_parser_ignores_nonmodels_and_untrusted_docs_links(self):
        index = '''- [Overview](https://docs.gmicloud.ai/model-quickstarts/video/about.md)
- [Fake](https://example.com/model-quickstarts/video/fake.md)
- [Studio node](https://docs.gmicloud.ai/gmi-studio/nodes/video/wan.md)
- [A model](https://docs.gmicloud.ai/model-quickstarts/video/model-a.md)
'''
        records = g.documented_models(index)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['doc_slug'], 'model-a')

    def test_unrecognized_docs_index_is_explicit_error(self):
        with self.assertRaises(g.Error):
            g.documented_models('An HTML error page instead of model links.')

    def test_unexpected_pagination_is_not_reported_complete(self):
        api = self.discovery_api()
        original = api.read.side_effect
        def read(base, path):
            value = original(base, path)
            if base == g.MEDIA and path == 'models':
                value['has_more'] = True
            return value
        api.read.side_effect = read
        result = g.catalog(api)
        self.assertFalse(result['complete'])
        self.assertEqual(result['matched'], 4)
        self.assertTrue(any(e['code'] == 'CATALOG_INCOMPLETE' for e in result['errors']))

    def test_default_models_command_uses_all_sources_and_export(self):
        destination = Path(self.tmp.name) / 'catalog.json'
        output = io.StringIO()
        with patch.object(g, 'API', return_value=self.discovery_api()), redirect_stdout(output):
            code = g.main(['models', '--out', str(destination)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(destination.read_text())['matched'], 4)
        self.assertEqual(json.loads(output.getvalue())['saved_catalog'], str(destination.resolve()))

    def test_models_without_key_returns_docs_instead_of_empty_failure(self):
        output = io.StringIO()
        with patch.dict(os.environ, {'GMI_API_KEY': ''}), redirect_stdout(output):
            code = g.main(['models'])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(result['matched'], 1)
        self.assertEqual(result['errors'][0]['code'], 'MISSING_API_KEY')

    def test_public_documentation_request_has_no_credentials(self):
        opener = unittest.mock.MagicMock()
        response = unittest.mock.Mock()
        response.read.return_value = b'public docs'
        opener.open.return_value.__enter__.return_value = response
        # Use the real function despite the default test fixture patch.
        real_fetch = self.original_docs_fetch
        with patch.object(g, 'build_opener', return_value=opener):
            self.assertEqual(real_fetch(), 'public docs')
        request = opener.open.call_args.args[0]
        self.assertFalse(request.has_header('Authorization'))
        self.assertFalse(request.has_header('X-organization-id'))

    def test_zero_workers_do_not_block_authorized_submission(self):
        schema = {**Fixture.schema, 'qworkers': 0}
        with patch.object(self.api, 'read', return_value=schema):
            job = self.submit()
        self.assertEqual(Fixture.posts, 1)
        self.assertIn('zero workers', job['notices'][0])

    def test_documented_created_state_is_pending(self):
        Fixture.response = (200, {'request_id': 'req-1', 'model': 'demo', 'status': 'created'})
        self.assertEqual(g.job_exit(self.submit()), 3)

    def test_live_style_empty_model_id_is_reported_without_crashing(self):
        api = self.discovery_api()
        original = api.read.side_effect
        def read(base, path):
            data = original(base, path)
            if base == g.MEDIA and path == 'models':
                data['model_ids'].append('')
            return data
        api.read.side_effect = read
        result = g.catalog(api)
        self.assertEqual(result['matched'], 4)
        self.assertEqual(result['warnings'][0]['code'], 'EMPTY_MODEL_ID')
        self.assertTrue(result['complete'])

    def test_invalid_middle_record_does_not_hide_later_models(self):
        api = self.discovery_api()
        original = api.read.side_effect
        def read(base, path):
            if base == g.MEDIA and path == 'models':
                return {'model_ids': ['first-model', {}, 'last-model']}
            return original(base, path)
        api.read.side_effect = read
        result = g.catalog(api)
        ids = [r['id'] for r in result['models']]
        self.assertIn('first-model', ids)
        self.assertIn('last-model', ids)
        self.assertFalse(result['complete'])
        self.assertEqual(result['errors'][0]['code'], 'CATALOG_INVALID_RECORD')

    def test_ambiguous_doc_alias_does_not_guess_an_api_id(self):
        api = self.discovery_api()
        api.read.side_effect = lambda base, path: {'model_ids': ['a-b', 'ab']}
        with patch.object(g, 'fetch_docs_index', return_value='- [AB](https://docs.gmicloud.ai/model-quickstarts/video/ab.md)'):
            result = g.catalog(api, kind='media')
        docs = [r for r in result['models'] if r['source'] == 'documentation']
        self.assertEqual(len(docs), 1)
        self.assertIsNone(docs[0]['id'])
        self.assertEqual(len(result['models']), 3)

    def test_text_models_preserves_raw_inference_response(self):
        api = self.discovery_api()
        output = io.StringIO()
        with patch.object(g, 'API', return_value=api), redirect_stdout(output):
            code = g.main(['text-models'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['data'][0]['id'], 'text/model')
        self.assertEqual(api.read.call_count, 1)

    def test_status_snapshot_does_not_block_authorized_submission(self):
        with patch.object(self.api, 'read', return_value={**Fixture.schema, 'status': 'inactive'}):
            job = self.submit()
        self.assertEqual(Fixture.posts, 1)
        self.assertEqual(job['request_id'], 'req-1')


if __name__ == '__main__':
    unittest.main()
