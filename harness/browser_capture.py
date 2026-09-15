"""Fresh-profile Chrome CDP screenshots, DOM and network evidence.

Only native read-only page navigation and a normal sandbox login are automated.
No app source injection, desired business answer, or database mutation occurs.
Remote resources and file URLs are blocked and disclosed as admin boundaries.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request
import uuid

CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


class CDP:
    def __init__(self,url,allowed_origin):
        import websocket
        self.ws=websocket.create_connection(url,timeout=20,suppress_origin=True)
        self.sequence=0
        self.events=[]
        self.origin=allowed_origin

    def call(self,method,params=None):
        self.sequence+=1
        seq=self.sequence
        self.ws.send(json.dumps({'id':seq,'method':method,'params':params or {}}))
        while True:
            result=json.loads(self.ws.recv())
            if result.get('method')=='Fetch.requestPaused':
                request=result['params']
                url=request['request']['url']
                self.sequence+=1
                allowed=url.startswith(self.origin+'/') or url.startswith('data:')
                self.events.append(dict(method='administration_network_boundary',url=url,allowed=allowed))
                self.ws.send(json.dumps({'id':self.sequence,'method':'Fetch.continueRequest' if allowed else 'Fetch.failRequest',
                    'params':{'requestId':request['requestId'],**({} if allowed else {'errorReason':'BlockedByClient'})}}))
            elif result.get('method'):
                self.events.append(result)
            if result.get('id')==seq:
                if 'error' in result: raise RuntimeError(result['error'])
                return result.get('result',{})

    def evaluate(self,expression,await_promise=False):
        value=self.call('Runtime.evaluate',dict(expression=expression,returnByValue=True,awaitPromise=await_promise))
        if value.get('exceptionDetails'): raise RuntimeError(value['exceptionDetails'])
        return value.get('result',{}).get('value')


def capture(origin,target,email,paths):
    target=Path(target)
    target.mkdir(parents=True,exist_ok=False)
    # Profile is administration-private scratch, not shared browser state and
    # not source material delivered to the candidate or observation bundle.
    root=Path(__file__).resolve().parents[1]
    profile=root/'pilot-001/admin/browser-profiles'/uuid.uuid4().hex
    profile.mkdir(parents=True)
    command=[CHROME,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
             '--disable-background-networking','--disable-component-update','--disable-sync',
             '--remote-debugging-port=0','--remote-debugging-address=127.0.0.1',
             '--user-data-dir='+str(profile),'about:blank']
    # Never inherit a key or use the user's browser profile.
    env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','TMPDIR']}
    with (target/'chrome.log').open('wb') as log:
        process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        client=None
        try:
            for _ in range(100):
                active=profile/'DevToolsActivePort'
                if active.exists(): break
                if process.poll() is not None: raise RuntimeError('Headless Chrome failed to start')
                time.sleep(.1)
            else: raise RuntimeError('Chrome debugging endpoint unavailable')
            port=int(active.read_text().splitlines()[0])
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list') as response:
                tabs=json.load(response)
            tab=next(t for t in tabs if t.get('type')=='page')
            client=CDP(tab['webSocketDebuggerUrl'],origin)
            client.call('Page.enable');client.call('Runtime.enable');client.call('Network.enable')
            client.call('Fetch.enable',{'patterns':[{'urlPattern':'*'}]})
            client.call('Emulation.setDeviceMetricsOverride',dict(width=1440,height=1000,deviceScaleFactor=1,mobile=False))
            client.call('Page.navigate',{'url':origin+'/login'})
            for _ in range(40):
                if client.evaluate('document.readyState')=='complete': break
                time.sleep(.1)
            # Normal supported API login, as used by the candidate's UI.
            login=client.evaluate('fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify('+json.dumps({'email':email,'password':'frostline'})+')}).then(async r=>({status:r.status,body:await r.json()}))',True)
            (target/'login.json').write_text(json.dumps(login,indent=2)+'\n')
            if login['status']!=200: raise RuntimeError('Sandbox UI login failed: '+str(login))
            for index,path in enumerate(paths):
                if not path.startswith('/') or path.startswith('//') or urllib.parse.urlsplit(path).scheme:
                    raise ValueError('Only relative native app paths may be captured')
                if path.startswith('/pilot'):
                    raise ValueError('Capture native app UI separately from source delivery')
                client.call('Page.navigate',{'url':origin+path})
                for _ in range(40):
                    ready=client.evaluate('document.readyState')
                    if ready=='complete': break
                    time.sleep(.1)
                # Let React's normal supported queries settle. No artificial
                # target content or backend response is injected.
                deadline=time.monotonic()+1.5
                while time.monotonic()<deadline:
                    client.call('Runtime.evaluate',{'expression':'document.readyState'})
                    time.sleep(.1)
                folder=target/f'{index:02}'
                folder.mkdir()
                for label,viewport in [('desktop',(1440,1000,False)),('mobile',(390,844,True))]:
                    if label=='mobile' and not path.startswith('/m'): continue
                    w,h,mobile=viewport
                    client.call('Emulation.setDeviceMetricsOverride',dict(width=w,height=h,deviceScaleFactor=1,mobile=mobile))
                    screenshot=client.call('Page.captureScreenshot',dict(format='png',captureBeyondViewport=True))
                    (folder/(label+'.png')).write_bytes(base64.b64decode(screenshot['data']))
                (folder/'dom.html').write_text(client.evaluate('document.documentElement.outerHTML'))
                (folder/'text.txt').write_text(client.evaluate('document.body.innerText'))
                (folder/'page.json').write_text(json.dumps(dict(requested_path=path,url=client.evaluate('location.href'),title=client.evaluate('document.title')),indent=2)+'\n')
                client.call('Emulation.setDeviceMetricsOverride',dict(width=1440,height=1000,deviceScaleFactor=1,mobile=False))
            (target/'events.json').write_text(json.dumps(client.events,indent=2)+'\n')
            (target/'capture-policy.json').write_text(json.dumps(dict(email=email,paths=paths,fresh_profile=True,
                observed_only=True,allowed_origin=origin,external_resources='Blocked by administrator; not evidence of candidate refusal/control'),indent=2)+'\n')
        finally:
            if client: client.ws.close()
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill();process.wait()
