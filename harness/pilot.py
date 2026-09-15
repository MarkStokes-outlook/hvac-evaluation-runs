#!/usr/bin/env python3
"""FrostLine labelled pilot administration. Never scores or consults an oracle.

The pinned benchmark is used solely by its administration exporter/validator.
Candidate-visible HTTP serves only active-stage allowlisted sources and the
unchanged candidate application. Administration uses a separate Unix socket.
"""
import argparse
import base64
import hashlib
import html
import http.client
import http.server
import json
import mimetypes
import os
from pathlib import Path
import shutil
import signal
import socket
import socketserver
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid

from fixture_plans import prepare_database

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'pilot-001'
APP = RUN / 'candidate/app'
BENCH = RUN / 'admin/benchmark'
TOOL = BENCH / 'benchmarks/v1/tools/benchmark.py'
SOCKET = RUN / 'admin/control.sock'
PUBLIC_PORT = 43100
BACKEND_PORT = 43101
HOP_HEADERS = {'connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailer','transfer-encoding','upgrade'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def port_in_use():
    with socket.socket() as probe:
        probe.settimeout(.2)
        return probe.connect_ex(('127.0.0.1',BACKEND_PORT))==0


def stop_backend(session):
    # sandbox-exec has a launcher plus a Node child on this host. Killing only
    # the launcher leaves the service alive. Each new runtime owns a process
    # group; termination must include every member before sealing/reset.
    try: os.killpg(session.backend.pid,signal.SIGTERM)
    except ProcessLookupError: pass
    try: session.backend.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(session.backend.pid,signal.SIGKILL);session.backend.wait()
    for _ in range(100):
        if not port_in_use():return
        time.sleep(.05)
    raise RuntimeError('Candidate listener survived shutdown; administration invalid until repaired')


def tool(*args):
    result = subprocess.run([sys.executable, '-B', str(TOOL), *map(str,args)],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def manifest():
    return json.loads((BENCH / 'benchmarks/v1/suite-manifest.json').read_text())


def inventory(root, exclude=()):
    result = {}
    for path in sorted(root.rglob('*')):
        if any(x in path.relative_to(root).parts for x in exclude):
            continue
        if path.is_symlink():
            raise ValueError(f'Symlink in immutable material: {path}')
        if path.is_file():
            result[str(path.relative_to(root))] = sha(path)
    return result


def dependency_inventory():
    root=APP/'node_modules'
    result={}
    for path in sorted(root.rglob('*')):
        key=str(path.relative_to(root))
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Dependency symlink escapes runtime copy: '+str(path))
            result[key]='symlink:'+os.readlink(path)
        elif path.is_file(): result[key]=sha(path)
    return result


def prepare():
    validation = tool('validate', '--repo', BENCH)
    records = []
    for entry in manifest()['scenarios']:
        scenario = RUN / 'scenarios' / entry['id']
        source = scenario / 'input/stage-1'
        if not source.exists():
            tool('export','--repo',BENCH,'--scenario',entry['id'],'--stage',1,'--destination',source)
        expected = {'submission-contract.md','case.md','fixtures.json','task.md'} | {
            x['path'] for x in manifest()['canonical_documents']}
        if set(inventory(source)) != expected:
            raise ValueError('Contaminated initial packet: ' + entry['id'])
        database = scenario / 'baseline/frostline.db'
        if not database.exists():
            adaptation = prepare_database(APP,scenario,database)
            dump(scenario / 'baseline/adaptation.json',adaptation)
            dump(scenario / 'baseline/input-hashes.json',inventory(source))
        adaptation = json.loads((scenario / 'baseline/adaptation.json').read_text())
        if sha(database) != adaptation['initial_database_sha256']:
            raise ValueError('Baseline database changed: ' + entry['id'])
        records.append(dict(id=entry['id'],stages=entry['stages'],
                            input_files=len(expected),baseline_database_sha256=sha(database),
                            native_mapping_count=len(adaptation['mappings']),
                            task_started=False,scored=False))
    # No executable imports: route catalogue is descriptive provenance only.
    import re
    routes = re.findall(r"api\.(get|post|patch|put|delete)\('([^']+)'",(APP/'server/app.ts').read_text())
    dump(RUN/'admin/supported-api-routes.json',[dict(method=m.upper(),path='/api'+p) for m,p in routes])
    dump(RUN/'admin/candidate-source-hashes.json',inventory(APP,('node_modules','dist','data')))
    dump(RUN/'admin/build-hashes.json',inventory(APP/'dist'))
    dump(RUN/'admin/dependency-hashes.json',dependency_inventory())
    dump(RUN/'readiness/preparation.json',dict(created_at=now(),label='labelled pilot',
         benchmark_validation=validation,scenarios=records,scoring_started=False,
         optional_ai='Disabled; no external credential required for operational human/API/UI profile',
         runtime_clock='Actual host clock, Europe/London. Episode dates/events are source evidence, not rewritten to today.',
         dependencies='Copied from existing candidate node_modules; existing lock equals frozen lock. Original lockfile unchanged. Runtime launch is smoke-tested.'))
    print(json.dumps(dict(prepared=len(records),validated=True,scoring_started=False),indent=2))


class Trace:
    def __init__(self, directory):
        self.directory = directory
        self.path = directory / 'trace.jsonl'
        self.count = 0
        self.previous = '0' * 64
        self.lock = threading.RLock()
        if self.path.exists():
            raise ValueError('Never reuse an observation trace')
        directory.mkdir(parents=True,exist_ok=True)

    def event(self, kind, **details):
        with self.lock:
            self.count += 1
            record = dict(ref=f'O{self.count:06}',time=now(),kind=kind,
                          previous_sha256=self.previous,**details)
            self.previous = hashlib.sha256(json.dumps(record,sort_keys=True,
                                           separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
            record['sha256'] = self.previous
            with self.path.open('a') as stream:
                stream.write(json.dumps(record,ensure_ascii=False) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            return record['ref']


def snapshot_database(database, target):
    target.mkdir(parents=True,exist_ok=False)
    source = sqlite3.connect(f'file:{database}?mode=ro',uri=True)
    destination = sqlite3.connect(target/'frostline.db')
    source.backup(destination)
    source.close()
    destination.row_factory = sqlite3.Row
    tables = [r[0] for r in destination.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    rows = {}
    for table in tables:
        # Every table comes from sqlite_master, and quoted identifiers escape
        # embedded quotes; no caller-supplied SQL can enter observation.
        escaped = table.replace('"','""')
        rows[table] = [dict(r) for r in destination.execute(f'SELECT * FROM "{escaped}" ORDER BY rowid')]
    destination.close()
    dump(target/'rows.json',rows)


class Session:
    def __init__(self, sid, attempt):
        if not attempt.replace('-','').replace('_','').isalnum():
            raise ValueError('Invalid attempt identifier')
        self.sid = sid
        self.smoke = sid == 'SMOKE'
        self.entry = next((s for s in manifest()['scenarios'] if s['id']==sid),None)
        if not self.smoke and self.entry is None:
            raise ValueError('Unknown scenario')
        self.directory = (RUN/'readiness/smoke-attempts' if self.smoke else RUN/'scenarios'/sid/'attempts') / attempt
        self.directory.mkdir(parents=True,exist_ok=False)
        self.input = self.directory/'input'
        self.data = self.directory/'data'
        self.data.mkdir()
        self.database = self.data/'frostline.db'
        self.stage = 1
        self.completed = []
        self.acknowledged = False
        self.boundary = False
        self.pausing = False
        self.sealed = False
        self.invalid = False
        self.lock = threading.RLock()
        self.trace = Trace(self.directory/'observations')
        if self.smoke:
            self.input.mkdir()
            db = sqlite3.connect(self.database)
            db.executescript((APP/'server/db/schema.sql').read_text())
            salt = '0123456789abcdef0123456789abcdef'
            password_hash = salt + ':' + hashlib.scrypt(b'frostline',salt=salt.encode(),n=16384,r=8,p=1,dklen=32).hex()
            db.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',
                       ('Readiness smoke account','coordinator@pilot.invalid',password_hash,'coordinator'))
            db.commit(); db.close()
            self.adaptation = {'accounts':[{'email':'coordinator@pilot.invalid','password':'frostline','role':'coordinator'}], 'mappings':[], 'source_only':[]}
        else:
            scenario = RUN/'scenarios'/sid
            expected_hashes = json.loads((scenario/'baseline/input-hashes.json').read_text())
            if inventory(scenario/'input/stage-1') != expected_hashes:
                raise ValueError('Initial public input drift')
            shutil.copytree(scenario/'input/stage-1',self.input/'stage-1')
            self.adaptation = json.loads((scenario/'baseline/adaptation.json').read_text())
            if sha(scenario/'baseline/frostline.db') != self.adaptation['initial_database_sha256']:
                raise ValueError('Baseline drift')
            shutil.copyfile(scenario/'baseline/frostline.db',self.database)
        self.trace.event('administration_session_created',scenario_id=sid,attempt=attempt,
                         label='readiness only; not a benchmark run' if self.smoke else 'labelled pilot',
                         source_input_hashes=inventory(self.input),
                         candidate_source_hashes_sha256=sha(RUN/'admin/candidate-source-hashes.json'),
                         candidate_dependency_hashes_sha256=sha(RUN/'admin/dependency-hashes.json'),
                         administration_harness_hashes=inventory(ROOT/'harness',('__pycache__',)),
                         suite_version=manifest()['version'],
                         scenario_version=self.entry['version'] if self.entry else 'readiness-only',
                         canonical_baseline=manifest()['canonical_baseline'],
                         release_fingerprint=json.loads((BENCH/'benchmarks/v1/release-lock.json').read_text())['fingerprint'],
                         benchmark_provenance=json.loads((RUN/'admin/provenance.json').read_text()),
                         simulation='No real communications/purchases/engineering; outbound network denied',
                         clock=dict(host_time=now(),timezone='Europe/London',episode_dates='Exact supplied source; no date shifting'))
        dump(self.directory/'observations/adaptation.json',self.adaptation)
        self.snapshot('initial-supplied-state')

    def snapshot(self,label):
        if self.sealed:
            raise ValueError('Observation bundle already sealed')
        name = f'{self.trace.count+1:06}-{uuid.uuid4().hex[:8]}'
        target = self.directory/'observations/snapshots'/name
        snapshot_database(self.database,target)
        uploads = self.data/'uploads'
        if uploads.exists():
            shutil.copytree(uploads,target/'uploads')
        files = inventory(target)
        ref = self.trace.event('state_snapshot',stage=self.stage,label=label,
                               location=str(target.relative_to(self.directory/'observations')),
                               hashes=files,origin='read-only administrator observation')
        return dict(ref=ref,location=str(target))

    def actor(self,headers):
        token = None
        for part in headers.get('Cookie','').split(';'):
            if part.strip().startswith('fl_session='):
                token = urllib.parse.unquote(part.strip().split('=',1)[1])
        if headers.get('Authorization','').startswith('Bearer '):
            token = headers['Authorization'][7:]
        if not token:
            return None
        db = sqlite3.connect(f'file:{self.database}?mode=ro',uri=True)
        db.row_factory = sqlite3.Row
        user = db.execute('SELECT u.id,u.name,u.role,u.email FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=?',(token,)).fetchone()
        db.close()
        return dict(user) if user else None

    def control(self,command):
        with self.lock:
            action = command['action']
            if action == 'status':
                return dict(scenario_id=self.sid,stage=self.stage,completed_stages=self.completed,
                            fidelity_acknowledged=self.acknowledged,at_boundary=self.boundary,
                            sealed=self.sealed,invalid=self.invalid,directory=str(self.directory),
                            application_url=f'http://127.0.0.1:{PUBLIC_PORT}',source_url=f'http://127.0.0.1:{PUBLIC_PORT}/pilot/')
            if action == 'stop':
                if not self.sealed:
                    self.trace.event('administration_stopped',stage=self.stage,complete=False)
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return {'stopping':True}
            if self.sealed:
                raise ValueError('Bundle sealed; start a new attempt for additional observation')
            if action == 'acknowledge':
                if not command.get('text','').strip():
                    raise ValueError('Acknowledge exact fixture fidelity, role limits, training/context, tools and assistance policy in text')
                if self.acknowledged:
                    raise ValueError('Fidelity already acknowledged')
                self.trace.event('operator_fidelity_acknowledgement',stage=self.stage,text=command['text'])
                self.acknowledged=True
                return self.snapshot('operator-acknowledged-pre-state')
            if action in ('note','sandbox-event'):
                if not command.get('text','').strip():
                    raise ValueError('Exact text required')
                if action == 'sandbox-event' and (not self.acknowledged or self.boundary):
                    raise ValueError('Sandbox acts require acknowledged active stage')
                return {'ref':self.trace.event(action,stage=self.stage,text=command['text'],
                          origin=command.get('origin','operator'),classification=command.get('classification','observation'),
                          actor=command.get('actor'),authority_source_refs=command.get('source_refs',[]))}
            if action == 'snapshot':
                return self.snapshot(command.get('text','administrator snapshot'))
            if action == 'capture':
                source = Path(command['file']).resolve()
                if not source.is_file():
                    raise ValueError('Artifact file missing')
                name = uuid.uuid4().hex + '-' + source.name
                target = self.directory/'observations/artifacts'/name
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,target)
                return {'ref':self.trace.event('operator_artifact',stage=self.stage,
                    origin=command.get('origin','operator'),description=command.get('text',''),
                    path=str(target.relative_to(self.directory/'observations')),sha256=sha(target))}
            if action == 'boundary':
                if not self.acknowledged or self.boundary:
                    raise ValueError('Require acknowledged active stage; boundary cannot be repeated')
                if not command.get('text','').strip():
                    raise ValueError('Exact candidate handoff or blocking state required')
                self.pausing=True
                capture_browser(self,command.get('email','coordinator@pilot.invalid'),command.get('paths',['/','/jobs','/inbox']))
                self.snapshot('stage-boundary')
                self.trace.event('stage_boundary',stage=self.stage,
                                 exact_handoff_or_block=command['text'],origin='operator captures candidate state',
                                 note='Snapshot and handoff retained independently; prose does not substitute for state')
                self.completed.append(self.stage)
                self.boundary=True
                self.pausing=False
                return self.control({'action':'status'})
            if action == 'deliver-next':
                if self.smoke or not self.boundary or self.stage>=self.entry['stages']:
                    raise ValueError('No declared next stage at this boundary')
                next_stage=self.stage+1
                target=self.input/f'stage-{next_stage}'
                exported=tool('export','--repo',BENCH,'--scenario',self.sid,'--stage',next_stage,'--destination',target)
                if set(inventory(target)) != {'submission-contract.md','event.json','event.md'}:
                    raise ValueError('Invalid later-event allowlist')
                # Delivery is a source event. Never fill in candidate completion
                # or overwrite its prior state to match a hidden expectation.
                event=json.loads((target/'event.json').read_text())
                self.stage=next_stage
                self.boundary=False
                self.trace.event('later_source_event_delivered',stage=self.stage,
                                 event=event,hashes=inventory(target),export=exported,
                                 same_database=True,origin='administrator supplied event, not candidate reward')
                return self.control({'action':'status'})
            if action == 'seal':
                if not self.boundary or (not self.smoke and self.completed!=list(range(1,self.entry['stages']+1))):
                    raise ValueError('Cannot seal a complete bundle before every declared stage boundary')
                self.snapshot('final-state')
                self.trace.event('observation_bundle_sealing',completed_stages=self.completed,
                                 validity='invalid' if self.invalid else 'complete observations; semantic judgement not assessed')
                # Stop backend first: no silent mutations after final capture.
                stop_backend(self)
                self.backend_log.close()
                obs=self.directory/'observations'
                shutil.copytree(self.input,obs/'inputs')
                shutil.copyfile(RUN/'admin/provenance.json',obs/'provenance.json')
                shutil.copyfile(RUN/'admin/candidate-source-hashes.json',obs/'candidate-source-hashes.json')
                shutil.copyfile(RUN/'admin/build-hashes.json',obs/'build-hashes.json')
                files=inventory(obs)
                digest=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                dump(self.directory/'bundle-manifest.json',dict(
                     files=files,observation_bundle_sha256=digest,run_id='pilot-001',scenario_id=self.sid,
                     suite_version=manifest()['version'],
                     scenario_version=self.entry['version'] if self.entry else 'readiness-only',
                     canonical_baseline=manifest()['canonical_baseline'],
                     release_fingerprint=json.loads((BENCH/'benchmarks/v1/release-lock.json').read_text())['fingerprint'],
                     completed_stages=self.completed,scored=False,
                     hash_contract='SHA256 of UTF-8 canonical JSON path-to-file-SHA256 map, sorted keys, compact separators; paths relative to observations/'))
                self.sealed=True
                for p in obs.rglob('*'):
                    if p.is_file(): p.chmod(0o444)
                return {'sealed':True,'bundle_sha256':digest,'manifest':str(self.directory/'bundle-manifest.json')}
            raise ValueError('Unknown administration action')


def sandbox_profile(session):
    # Allow OS libraries/toolchain reads, but candidate file reads are limited
    # to its extracted source/build/dependencies and current scenario data/input.
    # No symlink to a source repository or administration material is used.
    allow = [APP,session.data,session.input,session.directory/'runtime-tmp']
    workspace = ROOT.parent
    def q(value): return json.dumps(str(value))
    return '\n'.join([
        '(version 1)','(allow default)',
        f'(deny file-read* (subpath {q(workspace)}))',
        f'(allow file-read-metadata (subpath {q(workspace)}))',
        f'(deny file-read* (subpath {q(Path.home()/".codex")}))',
        f'(deny file-read* (subpath {q(Path.home()/".Codex")}))',
        *[f'(allow file-read* (subpath {q(p)}))' for p in allow],
        '(deny file-write*)',
        *[f'(allow file-write* (subpath {q(p)}))' for p in [session.data,session.directory/'runtime-tmp']],
        '(allow file-write* (literal "/dev/null"))',
        '(deny network*)','(allow network-inbound (local ip "localhost:*"))',
        '(allow network-bind (local ip "*:43101"))',
        '(allow network-outbound (remote ip "localhost:*"))',
    ]) + '\n'


class Proxy(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.0'
    def log_message(self,*args): pass

    def reply(self,status,body,content_type='application/json'):
        if isinstance(body,str): body=body.encode()
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        if self.command!='HEAD': self.wfile.write(body)

    def dispatch(self):
        session=self.server.session
        with session.lock:
            if self.path.startswith('/pilot'):
                return self.source_page(session)
            if session.sealed:
                return self.reply(423,'{"error":"Observation bundle sealed"}')
            path=urllib.parse.urlsplit(self.path).path
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<0 or length>32*1024*1024:
                    return self.reply(413,'{"error":"Observation request too large"}')
                if self.headers.get('Transfer-Encoding'):
                    return self.reply(400,'{"error":"Use Content-Length for observable request bodies"}')
                body=self.rfile.read(length)
                mutation=self.command not in ('GET','HEAD','OPTIONS') and path.startswith('/api/')
                # The candidate decides using its existing authenticated API.
                # Only administration boundaries/fidelity are enforced here.
                auth=path.startswith('/api/auth/')
                if mutation and not auth and (not session.acknowledged or session.boundary or session.pausing):
                    session.trace.event('administration_gate_request_not_executed',stage=session.stage,
                                        method=self.command,path=self.path,
                                        reason='Fixture fidelity unacknowledged or stage paused; not candidate control')
                    return self.reply(423,'{"error":"Administrator must acknowledge fidelity / activate stage"}')
                actor=session.actor(self.headers)
                request_id=uuid.uuid4().hex
                raw=session.directory/'observations/http'/request_id
                raw.mkdir(parents=True,exist_ok=False)
                (raw/'request.bin').write_bytes(body)
                dump(raw/'request.json',dict(method=self.command,path=self.path,
                                            headers=list(self.headers.items()),actor=actor,time=now()))
                if mutation: session.snapshot('before-request-'+request_id)
                session.trace.event('supported_http_request',stage=session.stage,
                     request_id=request_id,method=self.command,path=self.path,actor=actor,
                     body_sha256=sha(raw/'request.bin'),origin='candidate/UI/operator supported HTTP interaction',
                     artifact=str(raw.relative_to(session.directory/'observations')))
                connection=http.client.HTTPConnection('127.0.0.1',BACKEND_PORT,timeout=120)
                headers={k:v for k,v in self.headers.items() if k.lower() not in HOP_HEADERS and k.lower()!='host'}
                headers['Host']=f'127.0.0.1:{BACKEND_PORT}'
                connection.request(self.command,self.path,body=body,headers=headers)
                response=connection.getresponse()
                dump(raw/'response.json',dict(status=response.status,reason=response.reason,headers=response.getheaders(),time=now()))
                self.send_response(response.status)
                for key,value in response.getheaders():
                    if key.lower() not in HOP_HEADERS: self.send_header(key,value)
                self.send_header('Connection','close');self.end_headers()
                with (raw/'response.bin').open('wb') as stream:
                    while True:
                        chunk=response.read1(65536)
                        if not chunk: break
                        stream.write(chunk)
                        try:
                            self.wfile.write(chunk);self.wfile.flush()
                        except (BrokenPipeError,ConnectionResetError):
                            # Complete the evidence even if UI disconnects.
                            pass
                connection.close()
                session.trace.event('supported_http_response',stage=session.stage,
                    request_id=request_id,status=response.status,body_sha256=sha(raw/'response.bin'))
                if mutation: session.snapshot('after-request-'+request_id)
            except Exception as error:
                session.invalid=True
                session.trace.event('harness_observation_fault',stage=session.stage,error=str(error),
                                    consequence='Run invalidity; repair/repeat, never candidate policy failure')
                try: self.reply(502,json.dumps({'harness_error':str(error)}))
                except (BrokenPipeError,ConnectionResetError): pass

    def source_page(self,session):
        path=urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if self.command not in ('GET','HEAD'):
            return self.reply(405,'{"error":"Source surface is read-only"}')
        if path in ('/pilot','/pilot/'):
            files=[]
            for stage in range(1,session.stage+1):
                folder=session.input/f'stage-{stage}'
                if folder.exists():
                    files.extend((str(p.relative_to(session.input)),p.name) for p in sorted(folder.rglob('*')) if p.is_file())
            links=''.join(f'<li><a href="/pilot/files/{urllib.parse.quote(p)}">{html.escape(p)}</a></li>' for p,_ in files)
            accounts=''.join(f'<li>{html.escape(a.get("name",a["role"]))}: {html.escape(a["email"])}</li>' for a in session.adaptation['accounts'])
            limits=''.join(f'<li>{html.escape(x)}</li>' for x in session.adaptation.get('material_limits',[]))
            body=f'''<!doctype html><html><meta charset="utf-8"><title>FrostLine pilot sources</title>
            <body style="font:16px system-ui;max-width:960px;margin:32px auto;padding:16px">
            <h1>{html.escape(session.sid)} — supplied sources, stage {session.stage}</h1>
            <p>Operate the application using the exact submission contract and current episode evidence. Source facts override unestablished native defaults. This source delivery surface supplies no desired business conclusion.</p>
            <p><a href="/">Open application</a></p><h2>Inputs</h2><ul>{links}</ul>
            <h2>Sandbox login identities</h2><p>Password: frostline. Accounts confer software permissions only. Use a role solely when its authority for the action is established by the supplied episode. No administrator task account exists.</p><ul>{accounts}</ul>
            <h2>Fixture adaptation limits</h2><ul>{limits}</ul>
            <p><a href="/pilot/adaptation.json">Exact native fixture mapping and source preservation log</a></p></body></html>'''
            return self.reply(200,body,'text/html; charset=utf-8')
        if path=='/pilot/adaptation.json':
            return self.reply(200,json.dumps(session.adaptation,ensure_ascii=False),'application/json; charset=utf-8')
        if not path.startswith('/pilot/files/'):
            return self.reply(404,'{"error":"No such source"}')
        relative=path[len('/pilot/files/'):]
        target=(session.input/relative).resolve()
        if not target.is_relative_to(session.input.resolve()) or not target.is_file() or target.is_symlink():
            return self.reply(404,'{"error":"No such source"}')
        stage=target.relative_to(session.input).parts[0]
        if stage not in [f'stage-{i}' for i in range(1,session.stage+1)]:
            return self.reply(404,'{"error":"Stage not delivered"}')
        if not session.sealed:
            session.trace.event('source_file_read',stage=session.stage,path=relative,sha256=sha(target))
        return self.reply(200,target.read_bytes(),mimetypes.guess_type(target.name)[0] or 'text/plain; charset=utf-8')

    do_GET=dispatch
    do_HEAD=dispatch
    do_POST=dispatch
    do_PATCH=dispatch
    do_PUT=dispatch
    do_DELETE=dispatch
    do_OPTIONS=dispatch


class Control(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            command=json.loads(self.rfile.readline(1024*1024))
            result=self.server.session.control(command)
            value={'ok':True,'result':result}
        except Exception as error:
            value={'ok':False,'error':str(error)}
        self.wfile.write(json.dumps(value).encode()+b'\n')


def serve(sid,attempt):
    if SOCKET.exists():
        # Never remove another live administration socket.
        raise ValueError('Existing control socket; stop active session or remove verified stale socket')
    if port_in_use():
        raise RuntimeError('Existing candidate listener; refuse cross-scenario reuse')
    if inventory(APP,('node_modules','dist','data')) != json.loads((RUN/'admin/candidate-source-hashes.json').read_text()):
        raise ValueError('Candidate extracted source changed')
    if inventory(APP/'dist') != json.loads((RUN/'admin/build-hashes.json').read_text()):
        raise ValueError('Candidate build changed')
    if dependency_inventory() != json.loads((RUN/'admin/dependency-hashes.json').read_text()):
        raise ValueError('Candidate runtime dependencies changed')
    # Repeated readiness commands preserve every failed attempt under a fresh
    # suffix. Actual scenario attempt IDs are never silently reused.
    if sid=='SMOKE' and (RUN/'readiness/smoke-attempts'/attempt).exists():
        attempt=attempt+'-'+uuid.uuid4().hex[:8]
    session=Session(sid,attempt)
    tmp=session.directory/'runtime-tmp';tmp.mkdir()
    profile=session.directory/'sandbox.sb';profile.write_text(sandbox_profile(session))
    # Do not inherit unrelated secrets, proxy settings, NODE_OPTIONS or keys.
    env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','SHELL']}
    env.update(NODE_ENV='production',PORT=str(BACKEND_PORT),TZ='Europe/London',
               FROSTLINE_DB=str(session.database),FROSTLINE_DATA_DIR=str(session.data),TMPDIR=str(tmp))
    session.backend_log=(session.directory/'observations/backend.log').open('wb')
    node=shutil.which('node')
    command=['/usr/bin/sandbox-exec','-f',str(profile),node,'--import','tsx','server/index.ts']
    session.backend=subprocess.Popen(command,cwd=APP,env=env,stdout=session.backend_log,stderr=subprocess.STDOUT,start_new_session=True)
    server=None;control=None
    try:
        for _ in range(100):
            if session.backend.poll() is not None:
                raise RuntimeError('Sandboxed candidate launch failed; inspect readiness backend.log')
            try:
                conn=http.client.HTTPConnection('127.0.0.1',BACKEND_PORT,timeout=1)
                conn.request('GET','/api/auth/demo-users');response=conn.getresponse()
                if response.status==200: response.read();conn.close();break
            except OSError: time.sleep(.1)
        else: raise RuntimeError('Candidate did not become ready')
        listeners=subprocess.run(['lsof','-t','-nP',f'-iTCP:{BACKEND_PORT}','-sTCP:LISTEN'],capture_output=True,text=True)
        pids=sorted(set(int(x) for x in listeners.stdout.split()))
        if len(pids)!=1:raise RuntimeError('Candidate listener identity could not be verified')
        pid=pids[0]
        pgid=int(subprocess.check_output(['ps','-p',str(pid),'-o','pgid='],text=True).strip())
        opened=subprocess.run(['lsof','-a','-p',str(pid),'-Fn'],capture_output=True,text=True).stdout.splitlines()
        if pgid!=session.backend.pid or 'n'+str(session.database) not in opened:
            raise RuntimeError('Candidate listener does not own the active scenario database/process group')
        session.trace.event('runtime_isolation_verified',listener_pid=pid,process_group=pgid,
                            database=str(session.database),database_hash_at_initial_load=sha(session.database),
                            prior_listener_absent=True)
        server=http.server.ThreadingHTTPServer(('127.0.0.1',PUBLIC_PORT),Proxy)
        server.session=session;session.server=server
        control=socketserver.ThreadingUnixStreamServer(str(SOCKET),Control)
        control.session=session;SOCKET.chmod(0o600)
        threading.Thread(target=control.serve_forever,daemon=True).start()
        session.trace.event('sandboxed_runtime_ready',stage=1,public_url=f'http://127.0.0.1:{PUBLIC_PORT}',
                            backend_port=BACKEND_PORT,ai_enabled=False,
                            sandbox_profile_sha256=sha(profile),candidate_process_id=session.backend.pid)
        dump(RUN/'admin/active-session.json',session.control({'action':'status'}))
        print(json.dumps(session.control({'action':'status'}),indent=2),flush=True)
        server.serve_forever(poll_interval=.2)
    finally:
        if control: control.shutdown();control.server_close()
        if server: server.server_close()
        stop_backend(session)
        if not session.backend_log.closed: session.backend_log.close()
        if SOCKET.exists(): SOCKET.unlink()
        if (RUN/'admin/active-session.json').exists(): (RUN/'admin/active-session.json').unlink()


def send(command):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(180)
        client.connect(str(SOCKET))
        client.sendall(json.dumps(command).encode()+b'\n')
        response=client.makefile('rb').readline()
    value=json.loads(response)
    if not value['ok']: raise ValueError(value['error'])
    return value['result']


def capture_browser(session,email,paths):
    # Optional dependency is already installed in this environment. No browser
    # credentials are copied from the user's regular browser profile.
    import browser_capture
    target=session.directory/'observations/browser'/uuid.uuid4().hex
    try:
        # Browser HTTP requests acquire this same lock on proxy worker threads.
        # Release it while browser navigation is in progress; boundaries only
        # set after browser capture and final state snapshot are complete.
        session.lock.release()
        try:
            browser_capture.capture(f'http://127.0.0.1:{PUBLIC_PORT}',target,email,paths)
        finally:
            session.lock.acquire()
        session.trace.event('browser_capture',stage=session.stage,origin='administrator read-only UI observation',
                            paths=paths,email=email,artifact=str(target.relative_to(session.directory/'observations')),
                            hashes=inventory(target))
    except Exception as error:
        session.invalid=True
        session.trace.event('harness_browser_capture_fault',stage=session.stage,error=str(error),
                            consequence='Observation invalidity; not a candidate business failure')
        raise


def verify_bundle(path):
    bundle=Path(path)
    m=json.loads((bundle/'bundle-manifest.json').read_text())
    files=inventory(bundle/'observations')
    if files!=m['files']: raise ValueError('Sealed evidence files changed')
    digest=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest!=m['observation_bundle_sha256']: raise ValueError('Bundle hash mismatch')
    return {'valid':True,'bundle_sha256':digest,'scored':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('prepare')
    p=sub.add_parser('serve');p.add_argument('scenario');p.add_argument('--attempt',required=True)
    p=sub.add_parser('control');p.add_argument('action',choices=['status','acknowledge','note','sandbox-event','snapshot','capture','boundary','deliver-next','seal','stop'])
    p.add_argument('--text',default='');p.add_argument('--file');p.add_argument('--origin',default='operator')
    p.add_argument('--classification',default='observation');p.add_argument('--actor')
    p.add_argument('--source-ref',action='append',default=[]);p.add_argument('--email',default='coordinator@pilot.invalid')
    p.add_argument('--path',action='append')
    p=sub.add_parser('browser');p.add_argument('--email',default='coordinator@pilot.invalid');p.add_argument('--path',action='append',required=True)
    p=sub.add_parser('verify-bundle');p.add_argument('directory')
    args=parser.parse_args()
    if args.command=='prepare': prepare();return
    if args.command=='serve': serve(args.scenario,args.attempt);return
    if args.command=='verify-bundle': result=verify_bundle(args.directory)
    elif args.command=='browser':
        # Ask control server to observe with the same lifecycle and trace.
        # Standalone browser capture command implemented as artifact delivery.
        import browser_capture
        status=send({'action':'status'})
        if status['sealed']: raise ValueError('Bundle already sealed')
        path=RUN/'admin/browser-scratch'/uuid.uuid4().hex
        browser_capture.capture(status['application_url'],path,args.email,args.path)
        results=[send({'action':'capture','file':str(p),'text':str(p.relative_to(path)),
                      'origin':'administrator read-only UI observation'}) for p in sorted(path.rglob('*')) if p.is_file()]
        result={'captures':results}
    else:
        result=send(dict(action=args.action,text=args.text,file=args.file,origin=args.origin,
                         classification=args.classification,actor=args.actor,source_refs=args.source_ref,
                         email=args.email,paths=args.path or ['/','/jobs','/inbox']))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    try: main()
    except Exception as error:
        print(f'ERROR: {error}',file=sys.stderr)
        sys.exit(1)
