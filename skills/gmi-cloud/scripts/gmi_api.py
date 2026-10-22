#!/usr/bin/env python3
"""Direct GMI HTTP workflows. Python 3.10+, standard library only."""
import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import random
import re
import socket
import ssl
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, HTTPSHandler, build_opener
from uuid import uuid4

INFERENCE = 'https://api.gmi-serving.com/v1'
MEDIA = 'https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey'
PENDING = {'queued', 'pending', 'dispatched', 'processing', 'running', 'in_progress'}
SUCCESS = {'success', 'completed', 'succeeded'}
FAILURE = {'failed', 'error', 'cancelled', 'canceled', 'expired', 'rejected'}
TRANSIENT = {408, 429, 500, 502, 503, 504}
SENSITIVE = re.compile(r'token|api[_-]?key|authorization|secret|password', re.I)


def default_state_dir(platform=None, env=None, home=None):
    """Native user storage, with backward compatibility for existing registries."""
    platform = sys.platform if platform is None else platform
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    if env.get('GMI_SKILL_STATE_DIR'):
        return str(Path(env['GMI_SKILL_STATE_DIR']).expanduser())
    if platform == 'win32':
        base = Path(env.get('LOCALAPPDATA') or home / 'AppData' / 'Local')
        native = base / 'gmi-skill' / 'jobs'
    elif platform == 'darwin':
        native = home / 'Library' / 'Application Support' / 'gmi-skill' / 'jobs'
    else:
        xdg = Path(env.get('XDG_STATE_HOME', ''))
        base = xdg if xdg.is_absolute() else home / '.local' / 'state'
        native = base / 'gmi-skill' / 'jobs'
    legacy = home / '.local' / 'state' / 'gmi-skill' / 'jobs'
    if native != legacy and legacy.exists() and not native.exists():
        return str(legacy)
    return str(native)


def scrub(value):
    if isinstance(value, dict):
        return {k: '[redacted]' if SENSITIVE.search(k) else scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        for name in ('GMI_API_KEY', 'GMI_COMPUTE_API_KEY', 'GMI_SANDBOX_API_KEY'):
            secret = os.environ.get(name)
            if secret:
                value = value.replace(secret, '[redacted]')
    return value


def emit(value):
    # ASCII JSON works with legacy Windows consoles; parsers recover Unicode.
    print(json.dumps(scrub(value), ensure_ascii=True, allow_nan=False))


class Error(Exception):
    def __init__(self, message, *, transient=False, retry_after=0, hint=None, code=None):
        super().__init__(message)
        self.transient, self.retry_after, self.hint = transient, retry_after, hint
        self.code = code


def tls_context():
    """Verify certificates/hostnames using configured or Python default trust."""
    bundle = os.environ.get('GMI_CA_BUNDLE', '').strip()
    try:
        return ssl.create_default_context(cafile=str(Path(bundle).expanduser()) if bundle else None)
    except (OSError, ssl.SSLError):
        raise Error('Cannot load trusted CA certificates. Check GMI_CA_BUNDLE, '
                    'SSL_CERT_FILE and SSL_CERT_DIR; see references/portability.md#tls-certificates.',
                    code='TLS_CA_CONFIG') from None


def tls_error():
    return Error('TLS certificate verification failed. Repair the Python/OS CA setup '
                 'or set GMI_CA_BUNDLE to a trusted PEM CA bundle. On python.org macOS '
                 'installs, run the matching Install Certificates.command. '
                 'See references/portability.md#tls-certificates. Verification remains enabled.',
                 code='TLS_CERTIFICATE_VERIFY_FAILED')


def tls_diagnostics():
    context = tls_context()
    paths = ssl.get_default_verify_paths()
    return {'certificate_verification': context.verify_mode == ssl.CERT_REQUIRED,
            'hostname_verification': context.check_hostname,
            'ca_source': 'GMI_CA_BUNDLE' if os.environ.get('GMI_CA_BUNDLE', '').strip() else 'Python default trust',
            'loaded_ca_count': context.cert_store_stats()['x509_ca'],
            'default_cafile': paths.cafile, 'default_capath': paths.capath,
            'ssl_cert_file_configured': bool(os.environ.get('SSL_CERT_FILE')),
            'ssl_cert_dir_configured': bool(os.environ.get('SSL_CERT_DIR'))}


def secure_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise Error('Expected an HTTPS URL without embedded credentials.')
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Error('API redirect refused; check the official endpoint.')


class ArtifactRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        secure_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def retry_seconds(headers):
    value = headers.get('Retry-After', '')
    try:
        return max(0, float(value))
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0


class API:
    def __init__(self):
        self.key = os.environ.get('GMI_API_KEY', '').strip()
        if not self.key:
            raise Error('Set GMI_API_KEY in the execution environment; do not paste it into chat.')
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=tls_context()))

    def call(self, method, base, path, body=None, timeout=30):
        headers = {'Authorization': 'Bearer ' + self.key, 'User-Agent': 'gmi-skill/1.0',
                   'Accept': 'application/json'}
        if os.environ.get('GMI_ORG_ID'):
            headers['X-Organization-ID'] = os.environ['GMI_ORG_ID']
        data = None
        if body is not None:
            data = json.dumps(body, allow_nan=False).encode()
            headers['Content-Type'] = 'application/json'
        req = Request(base + '/' + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=max(0.001, timeout)) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise Error('API response exceeded 8 MiB.')
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise Error('Expected a JSON object from GMI.')
                return value
        except HTTPError as exc:
            try:
                envelope = json.loads(exc.read(65536))
            except (ValueError, OSError):
                envelope = {}
            finally:
                exc.close()
            if not isinstance(envelope, dict):
                envelope = {}
            limit = envelope.get('rate_limit') or {}
            daily = isinstance(limit, dict) and str(limit.get('limit_type', '')).upper() in {'RPD', 'DAILY'}
            hint = envelope.get('request_id')
            # Avoid raw upstream messages, which may echo keys or request content.
            raise Error(f'GMI HTTP {exc.code}' + ('; daily quota reached.' if daily else '.'),
                        transient=exc.code in TRANSIENT and not daily,
                        retry_after=retry_seconds(exc.headers), hint=hint) from None
        except (ssl.SSLCertVerificationError, URLError) as exc:
            reason = exc.reason if isinstance(exc, URLError) else exc
            if isinstance(reason, ssl.SSLCertVerificationError):
                raise tls_error() from None
            raise Error('GMI connection failed or timed out.', transient=True) from None
        except (TimeoutError, socket.timeout, ConnectionError, OSError, HTTPException):
            raise Error('GMI connection failed or timed out.', transient=True) from None
        except (ValueError, UnicodeError):
            raise Error('GMI returned invalid JSON.') from None

    def read(self, base, path):
        for attempt in range(3):
            try:
                return self.call('GET', base, path)
            except Error as exc:
                if not exc.transient or attempt == 2 or exc.retry_after > 30:
                    raise
                time.sleep(max(exc.retry_after, 2 ** attempt))


def unwrap(value):
    return value['data'] if isinstance(value.get('data'), dict) else value


def model_matches(record, search):
    """Compare names without punctuation/spacing; retain exact IDs for requests."""
    normalize = lambda s: re.sub(r'[^a-z0-9]', '', str(s).casefold())
    query = normalize(search)
    return not query or any(query in normalize(record.get(key, ''))
                            for key in ('id', 'model', 'name', 'display_name'))


def catalog(api, kind='all', search='', details=False):
    """Fresh discovery across both catalogs. Never filter out unavailable entries."""
    records, errors, counts = [], [], {}
    if kind in ('all', 'text'):
        try:
            data = api.read(INFERENCE, 'models').get('data')
            if not isinstance(data, list):
                raise Error('Unexpected text model catalog shape.')
            counts['text'] = len(data)
            for value in data:
                if not isinstance(value, dict) or not isinstance(value.get('id'), str):
                    raise Error('Text catalog contains an invalid model record.')
                record = {**value, 'source': 'text', 'listed': True}
                if model_matches(record, search):
                    records.append(record)
        except Error as exc:
            errors.append({'source': 'text', 'error': str(exc), 'code': exc.code})
    if kind in ('all', 'media'):
        try:
            ids = api.read(MEDIA, 'models').get('model_ids')
            if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids):
                raise Error('Unexpected media model catalog shape.')
            counts['media'] = len(ids)
            for model_id in dict.fromkeys(ids):
                record = {'id': model_id, 'source': 'media', 'listed': True,
                          'readiness': 'unknown'}
                if model_matches(record, search):
                    records.append(record)
        except Error as exc:
            errors.append({'source': 'media', 'error': str(exc), 'code': exc.code})
    if details:
        for record in records:
            if record['source'] != 'media':
                continue
            try:
                data = unwrap(api.read(MEDIA, 'models/' + quote(record['id'], safe='')))
                for key in ('display_name', 'model_type', 'status', 'qworkers',
                            'modalities', 'model_metadata', 'price_info'):
                    if key in data:
                        record[key] = data[key]
                status, workers = data.get('status'), data.get('qworkers')
                if status is not None and status != 'active':
                    record['readiness'] = 'unavailable'
                elif workers is not None:
                    if int(workers) <= 0:
                        record['readiness'] = 'no_workers'
                    elif status == 'active':
                        record['readiness'] = 'ready'
            except (Error, ValueError, TypeError) as exc:
                message = str(exc) if isinstance(exc, Error) else 'Invalid readiness metadata.'
                errors.append({'source': 'media', 'id': record['id'], 'error': message,
                               'code': getattr(exc, 'code', None)})
    records.sort(key=lambda r: (r['source'], r['id'].casefold()))
    return {'retrieved_at': now(), 'source_counts': counts, 'search': search,
            'models': records, 'matched': len(records), 'complete': not errors,
            'errors': errors}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', value):
        raise Error('IDs must be 1-128 letters, numbers, dots, underscores or hyphens.')
    if value.endswith('.') or value.split('.')[0].upper() in {
            'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
            *(f'LPT{i}' for i in range(1, 10))}:
        raise Error('ID is a reserved filename on Windows; choose a portable ID.')
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser()

    def path(self, job):
        return self.root / (identifier(job) + '.json')

    def load(self, job):
        try:
            value = json.loads(self.path(job).read_text(encoding='utf-8'))
            if not isinstance(value, dict) or value.get('job_id') != job:
                raise ValueError()
            return value
        except (OSError, ValueError):
            raise Error('Cannot read local job; check the ID and state directory.') from None

    def create(self, job):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(self.path(job['job_id']), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise Error('Local job ID exists; use status/wait or reconcile it. No submission sent.') from None
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(scrub(job), handle)

    def save(self, job):
        job['updated_at'] = now()
        fd, temp = tempfile.mkstemp(dir=self.root, prefix='.job-')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(scrub(job), handle)
            os.replace(temp, self.path(job['job_id']))
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def listing(self):
        if not self.root.exists():
            return []
        return [self.load(path.stem) for path in sorted(self.root.glob('*.json'))]


def apply_record(job, record, store):
    record = unwrap(record)
    request_id = record.get('request_id') or record.get('id') or job.get('request_id')
    if not request_id:
        raise Error('Submission response has no request ID; reconcile recent requests before resubmitting.')
    identifier(request_id)
    if job.get('request_id') and job['request_id'] != request_id:
        raise Error('Response request ID differs from the saved job.')
    if record.get('model') and record['model'] != job.get('model'):
        raise Error('Response model differs from the saved job; verify account and request ID.')
    job.update(request_id=request_id, status=str(record.get('status', 'unknown')).lower())
    job['outcome'] = record.get('outcome')
    store.save(job)
    return job


def job_exit(job):
    if job['status'] in SUCCESS:
        return 0
    if job['status'] in PENDING:
        return 3
    return 1


def validate_payload(payload, model):
    if not isinstance(payload, dict):
        raise Error('Payload must be a JSON object.')
    specs = model.get('parameters')
    if not isinstance(specs, list) or not specs:
        raise Error('Model has no parameter schema; inspect current GMI documentation before submitting.')
    known = {p['name']: p for p in specs if isinstance(p, dict) and p.get('name')}
    result = dict(payload)
    unknown = set(result) - set(known)
    if unknown:
        raise Error('Unknown payload fields: ' + ', '.join(sorted(unknown)))
    for name, spec in known.items():
        if name not in result and spec.get('required'):
            if spec.get('default_value') is None:
                raise Error('Missing required payload field: ' + name)
            result[name] = spec['default_value']
        if name not in result:
            continue
        value, typ = result[name], spec.get('type', 'string')
        types = {'integer': lambda x: type(x) is int, 'int': lambda x: type(x) is int,
                 'float': lambda x: type(x) in (int, float), 'number': lambda x: type(x) in (int, float),
                 'boolean': lambda x: type(x) is bool, 'bool': lambda x: type(x) is bool,
                 'string': lambda x: isinstance(x, str), 'array': lambda x: isinstance(x, list),
                 'object': lambda x: isinstance(x, dict)}
        if value is None and not spec.get('required'):
            continue
        if typ in types and not types[typ](value):
            raise Error(f'Payload field {name} must be {typ}; use correctly typed JSON.')
        options = spec.get('options') or spec.get('enum') or []
        choices = [v.get('value') if isinstance(v, dict) else v for v in options]
        if choices and value not in choices:
            raise Error('Unsupported value for payload field: ' + name)
    return result


def submit(api, store, model_id, payload, job_id=None):
    model = unwrap(api.read(MEDIA, 'models/' + quote(model_id, safe='')))
    if model.get('status') is not None and model['status'] != 'active':
        raise Error('Selected model is not active.')
    if model.get('qworkers') is not None and int(model['qworkers']) <= 0:
        raise Error('Selected model has no workers; choose another model.')
    payload = validate_payload(payload, model)
    # Detect invalid/nonfinite JSON before making an intent record or paid request.
    json.dumps(payload, allow_nan=False)
    job = {'job_id': identifier(job_id or str(uuid4())), 'model': model_id,
           'status': 'submitting', 'created_at': now(), 'request_id': None}
    store.create(job)
    try:
        record = api.call('POST', MEDIA, 'requests', {'model': model_id, 'payload': payload}, timeout=120)
        return apply_record(job, record, store)
    except (Error, KeyboardInterrupt, OSError):
        # HTTP errors can be ambiguous too. Never replay this POST automatically.
        exc = sys.exc_info()[1]
        job['status'] = 'submission_unknown'
        if isinstance(exc, Error) and exc.hint and isinstance(exc.hint, str):
            job['request_id_hint'] = exc.hint
        store.save(job)
        emit(job)
        raise


def refresh(api, store, job, timeout=30):
    if not job.get('request_id'):
        raise Error('No confirmed request ID. Use requests and attach to reconcile; do not resubmit.')
    record = api.call('GET', MEDIA, 'requests/' + quote(job['request_id'], safe=''), timeout=timeout)
    return apply_record(job, record, store)


def wait_job(api, store, job, timeout, sleep=time.sleep, clock=time.monotonic):
    deadline, delay, errors = clock() + timeout, 1.0, 0
    if job['status'] in SUCCESS | FAILURE:
        return job
    while clock() < deadline:
        remaining = deadline - clock()
        try:
            refresh(api, store, job, timeout=min(30, remaining))
            errors = 0
            if job['status'] not in PENDING:
                return job
            print(json.dumps({'job_id': job['job_id'], 'status': job['status']}), file=sys.stderr)
            pause = delay + random.uniform(0, delay * 0.1)
        except Error as exc:
            errors += 1
            if not exc.transient or errors >= 3:
                raise
            pause = max(delay, exc.retry_after)
        remaining = max(0, deadline - clock())
        if pause >= remaining:
            sleep(remaining)
            break
        sleep(pause)
        delay = min(10, delay * 1.6)
    return job


def artifact_urls(outcome):
    if not isinstance(outcome, dict):
        return []
    urls = []
    for key in ('audio_url', 'video_url', 'image_url'):
        if isinstance(outcome.get(key), str):
            urls.append(outcome[key])
    for key in ('media_urls', 'media', 'medias'):
        for item in outcome.get(key) or []:
            url = item.get('url') if isinstance(item, dict) else item
            if isinstance(url, str):
                urls.append(url)
    if not urls and isinstance(outcome.get('thumbnail_image_url'), str):
        urls.append(outcome['thumbnail_image_url'])
    return list(dict.fromkeys(urls))


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def download(store, job, output, max_bytes, opener=None):
    if job['status'] not in SUCCESS:
        raise Error('Downloads require a successful job; use status or wait first.')
    urls = artifact_urls(job.get('outcome'))
    if not urls:
        raise Error('Successful job has no recognized artifact URLs; inspect its outcome.')
    directory = Path(output).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    opener = opener or build_opener(ArtifactRedirect(), HTTPSHandler(context=tls_context()))
    saved = job.setdefault('downloads', {})
    failures = []
    for index, url in enumerate(urls, 1):
        temp = None
        try:
            secure_url(url)
            suffix = Path(urlsplit(url).path).suffix.lower()
            if not re.fullmatch(r'\.[a-z0-9]{1,8}', suffix):
                suffix = '.bin'
            path = directory / f"{job['job_id']}-{index}-{hashlib.sha256(url.encode()).hexdigest()[:10]}{suffix}"
            old = saved.get(str(path), {})
            if path.is_file() and old.get('sha256') == digest(path):
                continue
            # Separate opener and fresh Request: never inherit API auth or org headers.
            with opener.open(Request(url, headers={'User-Agent': 'gmi-skill/1.0'}), timeout=30) as response:
                if int(response.headers.get('Content-Length') or 0) > max_bytes:
                    raise Error('Artifact exceeds the per-file byte limit.')
                fd, temp = tempfile.mkstemp(dir=directory, prefix='.download-')
                count, sha = 0, hashlib.sha256()
                with os.fdopen(fd, 'wb') as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > max_bytes:
                            raise Error('Artifact exceeds the per-file byte limit.')
                        handle.write(chunk)
                        sha.update(chunk)
                length = response.headers.get('Content-Length')
                if length and count != int(length):
                    raise Error('Artifact body was truncated.')
            os.replace(temp, path)
            saved[str(path)] = {'bytes': count, 'sha256': sha.hexdigest()}
            store.save(job)
        except (Error, OSError, ValueError, URLError, HTTPException) as exc:
            reason = exc.reason if isinstance(exc, URLError) else exc
            if isinstance(reason, ssl.SSLCertVerificationError):
                exc = tls_error()
            # URLError text may contain a signed URL; report only the artifact index.
            failures.append({'artifact': index, 'error': str(exc) if isinstance(exc, Error) else 'Artifact download failed.',
                             'code': getattr(exc, 'code', None)})
        finally:
            if temp and os.path.exists(temp):
                os.unlink(temp)
    return {'job_id': job['job_id'], 'files': saved, 'failures': failures}


def json_file(path):
    with open(path, encoding='utf-8-sig') as handle:
        return json.load(handle, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON.')))


def positive(value):
    value = int(value)
    if value <= 0:
        raise argparse.ArgumentTypeError('Must be positive.')
    return value


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir', default=default_state_dir())
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('models', 'media-models', 'jobs', 'doctor'):
        sub.add_parser(name)
    discovery = sub.add_parser('catalog', help='Search fresh text and media catalogs together.')
    discovery.add_argument('--kind', choices=('all', 'text', 'media'), default='all')
    discovery.add_argument('--search', default='')
    discovery.add_argument('--details', action='store_true', help='Inspect matching media model readiness and pricing.')
    sub.add_parser('model').add_argument('model')
    recent = sub.add_parser('requests')
    recent.add_argument('--limit', type=positive, default=20)
    recent.add_argument('--offset', type=int, default=0)
    chat = sub.add_parser('chat')
    chat.add_argument('--model', required=True)
    inputs = chat.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--prompt')
    inputs.add_argument('--prompt-file')
    inputs.add_argument('--messages-file')
    chat.add_argument('--max-tokens', type=positive, default=512)
    create = sub.add_parser('submit')
    create.add_argument('--model', required=True)
    create.add_argument('--payload-file', required=True)
    create.add_argument('--job-id')
    for name in ('status', 'wait', 'download', 'attach'):
        cmd = sub.add_parser(name)
        cmd.add_argument('job_id')
        if name == 'wait':
            cmd.add_argument('--timeout', type=positive, default=45)
        elif name == 'download':
            cmd.add_argument('--out', required=True)
            cmd.add_argument('--max-bytes', type=positive, default=1024 ** 3)
        elif name == 'attach':
            cmd.add_argument('--request-id', required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    store = Store(args.state_dir)
    job = None
    try:
        if args.command == 'doctor':
            emit({'python': sys.version.split()[0], 'platform': sys.platform,
                  'state_dir': str(store.root),
                  'credentials_available': bool(os.environ.get('GMI_API_KEY', '').strip()),
                  'org_id_available': bool(os.environ.get('GMI_ORG_ID', '').strip()),
                  'tls': tls_diagnostics(),
                  'state_permissions': 'Windows inherited ACLs' if os.name == 'nt' else 'POSIX private modes'})
            return 0
        if args.command == 'jobs':
            emit({'jobs': store.listing()})
            return 0
        if args.command == 'download':
            job = store.load(args.job_id)
            result = download(store, job, args.out, args.max_bytes)
            emit(result)
            return 1 if result['failures'] else 0
        api = API()
        if args.command == 'catalog':
            result = catalog(api, args.kind, args.search, args.details)
            emit(result)
            return 0 if result['complete'] else 1
        if args.command in ('models', 'media-models', 'model', 'requests'):
            base, path = MEDIA, 'models'
            if args.command == 'models':
                base = INFERENCE
            elif args.command == 'model':
                path += '/' + quote(args.model, safe='')
            elif args.command == 'requests':
                path = 'requests?' + urlencode({'limit': args.limit, 'offset': args.offset})
            emit(api.read(base, path))
            return 0
        if args.command == 'chat':
            if args.messages_file:
                messages = json_file(args.messages_file)
            else:
                prompt = Path(args.prompt_file).read_text(encoding='utf-8-sig') if args.prompt_file else args.prompt
                messages = [{'role': 'user', 'content': prompt}]
            if not isinstance(messages, list) or not messages or any(not isinstance(m, dict) or 'role' not in m or 'content' not in m for m in messages):
                raise Error('Messages must be a nonempty array of role/content objects.')
            emit(api.call('POST', INFERENCE, 'chat/completions', {'model': args.model,
                          'messages': messages, 'max_tokens': args.max_tokens, 'stream': False}, timeout=120))
            return 0
        if args.command == 'submit':
            job = submit(api, store, args.model, json_file(args.payload_file), args.job_id)
        else:
            job = store.load(args.job_id)
            if args.command == 'attach':
                request_id = identifier(args.request_id)
                if job.get('request_id') and job['request_id'] != request_id:
                    raise Error('Refusing to replace a different saved request ID.')
                record = unwrap(api.read(MEDIA, 'requests/' + quote(request_id, safe='')))
                if record.get('model') != job['model']:
                    raise Error('Request model does not match the local intent.')
                returned_id = record.get('request_id') or record.get('id')
                if returned_id and returned_id != request_id:
                    raise Error('Fetched request ID differs from the selected request.')
                record.setdefault('request_id', request_id)
                apply_record(job, record, store)
            elif args.command == 'wait':
                wait_job(api, store, job, args.timeout)
            else:
                refresh(api, store, job)
        emit(job)
        return job_exit(job)
    except KeyboardInterrupt:
        emit({'error': 'Local waiting interrupted; remote work may continue.',
              'job_id': job.get('job_id') if job else getattr(args, 'job_id', None),
              'request_id': job.get('request_id') if job else None})
        return 130
    except (Error, OSError, ValueError, TypeError, KeyError) as exc:
        message = str(exc) if isinstance(exc, Error) else 'Invalid local input/state or file access failed.'
        emit({'error': message, 'job_id': job.get('job_id') if job else getattr(args, 'job_id', None),
              'request_id': job.get('request_id') if job else None, 'code': getattr(exc, 'code', None)})
        return 1


if __name__ == '__main__':
    sys.exit(main())
