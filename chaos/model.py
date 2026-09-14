"""Explicit OpenAI-compatible HTTP backend; no SDK, redirects or retries. NGPL."""
import http.client
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from .director import eligible
from .protocol import parse_request, strict_json


class ModelBackend:
    def __init__(self, endpoint, model, api_key_env, *, timeout=10., max_calls=4,
                 max_context=8192, max_response=16384, allow_local_http=False,
                 ordinary_food=False):
        self.url = urlsplit(endpoint)
        u = self.url
        local = allow_local_http and u.scheme == 'http' and u.hostname in ('127.0.0.1','::1','localhost')
        if (u.scheme != 'https' and not local) or not u.hostname or u.username or u.password or u.fragment:
            raise ValueError('explicit HTTPS endpoint required (local HTTP fixture opt-in only)')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',api_key_env):
            raise ValueError('API key environment variable NAME required')
        key = os.environ.get(api_key_env)
        if not key or any(ord(c)<32 or ord(c)>126 for c in key):
            raise ValueError('missing or invalid API key environment value')
        if not model or len(model)>200 or any(ord(c)<32 for c in model):
            raise ValueError('invalid model name')
        if not 0 < timeout <= 120 or not 1 <= max_calls <= 100 or not 2048 <= max_context <= 32768 or not 512 <= max_response <= 65536:
            raise ValueError('model limit outside allowed bounds')
        self.key, self.model = key, model
        self.timeout, self.max_calls = timeout, max_calls
        self.max_context, self.max_response = max_context, max_response
        self.calls = 0
        self.ordinary_food = ordinary_food
        self.deadline = float('inf')
        self.prompt = (Path(__file__).parent/'prompts/director.txt').read_text()

    def choose(self, state, ident, at):
        options = eligible(state,self.ordinary_food)
        if not options or self.calls >= self.max_calls: return None
        data = {'assigned_id':ident, 'assigned_at':at, 'eligible':options,
                'summary':json.loads(state.summary())}
        messages = [{'role':'system','content':self.prompt},
                    {'role':'user','content':json.dumps(data,separators=(',',':'))}]
        if len(json.dumps(messages).encode()) > self.max_context:
            raise ValueError('model context byte cap exceeded')
        body = json.dumps({'model':self.model,'messages':messages,'temperature':0,
                           'max_tokens':256,'stream':False,
                           'response_format':{'type':'json_object'}}).encode()
        end = min(time.monotonic()+self.timeout,self.deadline)
        remaining = end-time.monotonic()
        if remaining <= 0: return None
        cls = http.client.HTTPSConnection if self.url.scheme=='https' else http.client.HTTPConnection
        conn = cls(self.url.hostname,self.url.port,timeout=remaining)
        path = self.url.path or '/'
        if self.url.query: path += '?'+self.url.query
        self.calls += 1  # failed calls also spend the finite call allowance
        try:
            conn.request('POST',path,body=body,headers={'Authorization':'Bearer '+self.key,
                'Content-Type':'application/json','Accept':'application/json'})
            response = conn.getresponse()
            if response.status != 200:
                raise ValueError('model HTTP response rejected; no redirects or retries')
            chunks = []
            size = 0
            while True:
                remaining = end-time.monotonic()
                if remaining <= 0: raise ValueError('model request deadline exceeded')
                # read1 returns available bytes, preventing slow trickle from resetting the deadline.
                if response.fp is not None:
                    response.fp.raw._sock.settimeout(remaining)
                chunk = response.read1(min(4096,self.max_response+1-size))
                if not chunk: break
                chunks.append(chunk); size += len(chunk)
                if size > self.max_response: raise ValueError('model response byte cap exceeded')
            outer = strict_json(b''.join(chunks),self.max_response)
            choices = outer.get('choices')
            if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
                raise ValueError('model response choices invalid')
            message = choices[0].get('message')
            if type(message) is not dict or type(message.get('content')) is not str:
                raise ValueError('model response content invalid')
            request = parse_request(message['content'])
            if request['id'] != ident or request['at'] != at or request['mutation'] not in options:
                raise ValueError('model proposal is ineligible or changes assigned schedule')
            return request
        except (http.client.HTTPException, UnicodeError) as exc:
            raise ValueError('model transport failed') from exc
        finally:
            conn.close()
