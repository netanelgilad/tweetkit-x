import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import requests
from tweetkit_x.transport import SafeSession, TransportError
from tweetkit_x.cookie import parse_cookie, save_cookie, has_auth, keychain_write, CookieError
from tweetkit_x.importer import from_har, from_cookie_editor_json
from tweetkit_x.runner import validate, run, CATALOG

class Security(unittest.TestCase):
    def response(self,body=b'{}',status=200):
        r=requests.Response();r.status_code=status;r.raw=io.BytesIO(body);return r
    def test_destinations(self):
        for url in ['http://x.com/','https://x.com.evil.test/','https://evil.test/x.com','https://x.com@evil.test/','https://127.0.0.1/','https://x.com:8443/']:
            with self.subTest(url=url),patch.object(requests.Session,'request') as request:
                with self.assertRaises(TransportError):SafeSession().get(url)
                request.assert_not_called()
    def test_authenticated_cdn_denied(self):
        with self.assertRaises(TransportError):SafeSession().get('https://abs.twimg.com/test',headers={'Cookie':'secret'})
    def test_redirect_no_follow_no_leak(self):
        for code in [301,302,307,308,401,403,429,500]:
            with patch.object(requests.Session,'request',return_value=self.response(b'SECRET',code)) as request:
                with self.assertRaises(TransportError) as error:SafeSession().get('https://x.com/',headers={'cookie':'SECRET'})
                self.assertNotIn('SECRET',str(error.exception));self.assertFalse(request.call_args.kwargs['allow_redirects']);self.assertEqual(request.call_count,1)
    def test_proxy_disabled(self):self.assertFalse(SafeSession().trust_env)
    def test_api_errors_are_not_success(self):
        with patch.object(requests.Session,'request',return_value=self.response(b'{"errors":[{"message":"SECRET","code":32}]}')):
            with self.assertRaises(TransportError) as error:SafeSession().get('https://x.com/',headers={'cookie':'SECRET'})
            self.assertNotIn('SECRET',str(error.exception))
    def test_bound_response(self):
        with patch('tweetkit_x.transport.MAX_RESPONSE',3),patch.object(requests.Session,'request',return_value=self.response(b'12345')):
            with self.assertRaises(TransportError):SafeSession().get('https://x.com/')
    def test_cookie_header_injection(self):
        with self.assertRaises(CookieError):parse_cookie('auth_token=x\r\nOther: evil; ct0=y')
        self.assertFalse(has_auth('not_auth_token=x; ct0=y'))
    def test_atomic_cookie_file_does_not_follow_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'target';target.write_text('untouched');dest=Path(d)/'cookie';dest.symlink_to(target)
            save_cookie('auth_token=test; ct0=test',str(dest))
            self.assertEqual(target.read_text(),'untouched');self.assertEqual(stat.S_IMODE(dest.stat().st_mode),0o600)
    def test_keychain_write_never_argv(self):
        with patch('subprocess.run') as run:
            with self.assertRaises(CookieError):keychain_write('test','SECRET')
            run.assert_not_called()
    def test_har_host_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.har';path.write_text(json.dumps({'log':{'entries':[{'request':{'url':'https://evil.test/?x.com','cookies':[{'name':'auth_token','value':'evil'}]}}]}}))
            self.assertEqual(from_har(path),{})
    def test_export_domain_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'cookies.json';p.write_text(json.dumps([{'domain':'x.com.evil.test','name':'auth_token','value':'evil'}]))
            self.assertEqual(from_cookie_editor_json(p),{})
    def test_strict_catalog_inputs(self):
        for op,data in [('__class__',{}),('home',{'cookie':'secret'}),('publish',{'text':'a','image_path':'/etc/passwd'}),('home',{'limit':100000}),('post',{'tweet_id':'../secret'}),('home',{'limit':True}),('thread',{'items':['x']*11})]:
            with self.subTest(op=op,data=data),self.assertRaises(ValueError):validate(op,data)
    def test_validation_precedes_client(self):
        with patch('tweetkit_x.runner.TweetKit') as factory:
            with self.assertRaises(ValueError):run('publish',{'text':'hi','image_path':'/etc/passwd'},'secret',factory)
            factory.assert_not_called()
    def test_valid_input_mapping(self):
        self.assertEqual(validate('home',{}),{'following':True,'limit':20})
        self.assertEqual(validate('publish',{'text':'hello'}),{'text':'hello'})
    def test_catalog_all_methods_exist(self):
        from tweetkit_x.client import TweetKit
        for spec in CATALOG.values():self.assertTrue(callable(getattr(TweetKit,spec['method'])))
    def test_media_no_file_path(self):
        class Client:
            def __init__(self,**kw):pass
            def post(self,**kw):raise AssertionError('must not publish')
        with self.assertRaises(ValueError):run('publishMedia',{'text':'x','media_type':'image/png','media_base64':'c2VjcmV0'},'secret',Client)

if __name__=='__main__':unittest.main()

class RequestSecurity(unittest.TestCase):
    def test_publish_builds_only_expected_request(self):
        from tweetkit_x.client import TweetKit
        client=TweetKit(cookie='auth_token=synthetic-auth; ct0=synthetic-csrf; twid=u%3D123')
        r=requests.Response();r.status_code=200;r._content=b'{"data":{"create_tweet":{"tweet_results":{"result":{"rest_id":"123"}}}}}'
        with patch.object(client,'_tid',return_value='synthetic-tid'),patch.object(client._session,'post',return_value=r) as post:
            result=client.post('hello',reply_to='456')
            self.assertEqual(result['id'],'123');self.assertEqual(post.call_count,1)
            self.assertTrue(post.call_args.args[0].startswith('https://x.com/i/api/graphql/'))
            body=json.loads(post.call_args.kwargs['data']);self.assertEqual(body['variables']['tweet_text'],'hello')
            self.assertEqual(body['variables']['reply']['in_reply_to_tweet_id'],'456')
            self.assertEqual(post.call_args.kwargs['headers']['x-csrf-token'],'synthetic-csrf')
    def test_thread_stops_after_failure(self):
        from tweetkit_x.client import TweetKit
        client=TweetKit(cookie='auth_token=synthetic-auth; ct0=synthetic-csrf')
        with patch.object(client,'post',side_effect=[{'ok':True,'id':'1'},{'ok':False,'error':'failed'}]) as post:
            result=client.post_thread(['a','b','c']);self.assertEqual(len(result),2);self.assertEqual(post.call_count,2)
    def test_network_exception_does_not_leak_or_retry(self):
        with patch.object(requests.Session,'request',side_effect=requests.ConnectionError('SECRET')) as request:
            with self.assertRaises(TransportError) as e:SafeSession().post('https://x.com/',headers={'cookie':'SECRET'})
            self.assertNotIn('SECRET',str(e.exception));self.assertEqual(request.call_count,1)
    def test_mcp_cannot_write(self):
        from tweetkit_x.mcp_server import read
        with patch('tweetkit_x.mcp_server.load_cookie') as loader:
            self.assertFalse(read('publish',{'text':'hello'})['ok']);loader.assert_not_called()
