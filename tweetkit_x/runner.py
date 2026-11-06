"""Bounded one-shot runner: cookies arrive on stdin only, never tool arguments."""
import base64
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from .client import TweetKit
from .cookie import parse_cookie
from .transport import TransportError

CATALOG = json.loads(Path(__file__).with_name('operations.json').read_text())

def validate(operation, data):
    if operation not in CATALOG or not isinstance(data, dict):
        raise ValueError('Unknown operation or invalid input')
    fields = CATALOG[operation]['fields']
    if set(data) - set(fields):
        raise ValueError('Unexpected input field')
    out = {}
    for name, spec in fields.items():
        if name not in data:
            if 'default' in spec:
                out[name] = spec['default']
            elif not spec.get('optional'):
                raise ValueError('Missing field: ' + name)
            continue
        value = data[name]
        def check(v, s):
            typ = s['type']
            expected = {'string':str,'integer':int,'boolean':bool,'array':list}[typ]
            if type(v) is not expected:
                raise ValueError('Invalid field type')
            if typ in ('string','array'):
                if not s.get('minLength',s.get('minItems',0)) <= len(v) <= s.get('maxLength',s.get('maxItems',1000000)):
                    raise ValueError('Field size out of bounds')
            if typ == 'integer' and not s.get('minimum',0) <= v <= s.get('maximum',2**53-1):
                raise ValueError('Integer out of bounds')
            if 'pattern' in s and not re.fullmatch(s['pattern'],v):
                raise ValueError('Invalid identifier')
            if 'enum' in s and v not in s['enum']:
                raise ValueError('Invalid choice')
            if typ == 'array':
                for item in v: check(item,s['items'])
        check(value,spec)
        out[name]=value
    if operation == 'schedule' and out['at_epoch'] <= time.time():
        raise ValueError('Schedule must be in the future')
    return out

def run(operation, data, cookie, factory=TweetKit):
    values=validate(operation,data)
    client=factory(cookie=cookie,timeout=20)
    if operation == 'publishMedia':
        raw=base64.b64decode(values.pop('media_base64'),validate=True)
        mime=values.pop('media_type')
        signatures={'image/png':lambda b:b.startswith(b'\x89PNG\r\n\x1a\n'),'image/jpeg':lambda b:b.startswith(b'\xff\xd8\xff'),'image/gif':lambda b:b.startswith((b'GIF87a',b'GIF89a')),'image/webp':lambda b:b.startswith(b'RIFF') and b[8:12]==b'WEBP'}
        if len(raw)>200000 or not signatures[mime](raw):
            raise ValueError('Invalid media bytes or media too large (200 KB maximum)')
        ext={'image/png':'.png','image/jpeg':'.jpg','image/gif':'.gif','image/webp':'.webp'}[mime]
        with tempfile.NamedTemporaryFile(suffix=ext) as f:
            f.write(raw);f.flush()
            return client.post(**values,image_path=f.name)
    return getattr(client,CATALOG[operation]['method'])(**values)

def main():
    cookie=''
    try:
        raw=sys.stdin.buffer.read(400001)
        if len(raw)>400000: raise ValueError('Request too large')
        request=json.loads(raw)
        cookie=request['cookie']
        result=run(request['operation'],request.get('input',{}),cookie)
        # Defence in depth: never emit a session value even if X reflects it.
        encoded=json.dumps({'ok':True,'result':result},ensure_ascii=False)
        for value in parse_cookie(cookie).values():
            if len(value)>=8:
                encoded=encoded.replace(value,'[redacted]').replace(json.dumps(value)[1:-1],'[redacted]')
        if len(encoded.encode())>2_000_000: raise ValueError('Result too large')
        print(encoded)
    except TransportError as e:
        print(json.dumps({'ok':False,'error':str(e)}))
    except Exception:
        print(json.dumps({'ok':False,'error':'Invalid request or unexpected X response; no retry was attempted'}))

if __name__=='__main__':main()
