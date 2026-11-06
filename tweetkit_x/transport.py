"""Fail-closed HTTPS transport. No proxies, redirects, retries or raw upstream errors."""
import json
from urllib.parse import urlsplit
import requests

API_HOSTS = frozenset({'x.com', 'api.x.com', 'upload.x.com'})
PUBLIC_HOSTS = API_HOSTS | {'abs.twimg.com'}
MAX_RESPONSE = 8 * 1024 * 1024

class TransportError(RuntimeError):
    pass

class SafeSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.trust_env = False

    def request(self, method, url, **kwargs):
        parsed = urlsplit(url)
        headers = kwargs.get('headers') or {}
        authenticated = any(k.lower() in {'cookie', 'authorization', 'x-csrf-token'} for k in headers)
        allowed = API_HOSTS if authenticated else PUBLIC_HOSTS
        if (parsed.scheme != 'https' or parsed.hostname not in allowed
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise TransportError('Destination denied')
        kwargs.update(allow_redirects=False, stream=True)
        kwargs.setdefault('timeout', 30)
        kwargs.pop('proxies', None)
        try:
            response = super().request(method, url, **kwargs)
            try:
                if not 200 <= response.status_code < 300:
                    raise TransportError(f'X HTTP {response.status_code}; no automatic retry')
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_RESPONSE:
                        raise TransportError('X response exceeded size limit')
                    chunks.append(chunk)
                response._content = b''.join(chunks)
                response._content_consumed = True
            finally:
                response.close()
            if authenticated:
                try:
                    body = response.json()
                except ValueError:
                    if response.content:
                        raise TransportError('X returned a non-JSON response') from None
                else:
                    if isinstance(body, dict) and body.get('errors'):
                        codes = [e.get('code') for e in body['errors'] if isinstance(e, dict)]
                        codes = [c for c in codes if isinstance(c, int)]
                        raise TransportError(f'X rejected request; codes={codes}')
            return response
        except requests.RequestException:
            raise TransportError('X network failure; outcome may be unknown; do not automatically retry') from None
