"""Offline behavioral tests: python3 -m unittest discover -s scripts -p 'test_*.py'."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
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


if __name__ == '__main__':
    unittest.main()
