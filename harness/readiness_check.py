#!/usr/bin/env python3
"""Deterministic administration readiness checks; no candidate task or score.

--live uses ONLY the separate SMOKE sandbox. Never executes a B### task.
"""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import urllib.request

from pilot import APP, BENCH, RUN, SOCKET, PUBLIC_PORT, inventory, manifest, send, sha, tool, verify_bundle

checks=[]


def check(label,condition):
    if not condition: raise AssertionError(label)
    checks.append(label)
    print('PASS '+label,flush=True)


def static():
    check('pinned benchmark validates',tool('validate','--repo',BENCH)['checkpoints']==270)
    check('candidate source unchanged',inventory(APP,('node_modules','dist','data'))==json.loads((RUN/'admin/candidate-source-hashes.json').read_text()))
    for entry in manifest()['scenarios']:
        sid=entry['id'];scenario=RUN/'scenarios'/sid
        source=scenario/'input/stage-1'
        facts=json.loads((source/'fixtures.json').read_text())
        adaptation=json.loads((scenario/'baseline/adaptation.json').read_text())
        check(sid+' exact initial source hashes',inventory(source)==json.loads((scenario/'baseline/input-hashes.json').read_text()))
        check(sid+' immutable baseline',sha(scenario/'baseline/frostline.db')==adaptation['initial_database_sha256'])
        check(sid+' no premature later stage',not (scenario/'input/stage-2').exists())
        expected={'submission-contract.md','case.md','fixtures.json','task.md'}|{x['path'] for x in manifest()['canonical_documents']}
        check(sid+' candidate allowlist',set(inventory(source))==expected)
        db=sqlite3.connect(f'file:{scenario}/baseline/frostline.db?mode=ro',uri=True)
        check(sid+' fixture integrity',db.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not db.execute('PRAGMA foreign_key_check').fetchall())
        check(sid+' full source visible in native inbox',db.execute('SELECT body FROM enquiries').fetchone()[0]==(source/'case.md').read_text())
        check(sid+' no administrator task account',not db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone())
        check(sid+' every fact preserved',adaptation['source_only']==[
            dict(id=r['id'],statement=r['statement'],reason='Preserved verbatim; no exact complete native translation without unestablished fields or semantic loss') for r in facts['records']])
        check(sid+' no business action during preparation',not (scenario/'attempts').exists())
        db.close()


def request(method,path,value=None,cookie=None):
    connection=http.client.HTTPConnection('127.0.0.1',PUBLIC_PORT,timeout=20)
    body=None if value is None else json.dumps(value).encode()
    headers={'Content-Type':'application/json'}
    if cookie: headers['Cookie']=cookie
    connection.request(method,path,body,headers)
    response=connection.getresponse()
    result=(response.status,response.getheaders(),response.read())
    connection.close()
    return result


def live():
    status=send({'action':'status'})
    check('only readiness sandbox active',status['scenario_id']=='SMOKE')
    directory=Path(status['directory'])
    check('readiness launch has no episode sources',not list((directory/'input').rglob('fixtures.json')))
    # Probe a separate process under the same candidate confinement profile.
    targets=[APP/'package.json',directory/'data/frostline.db',
             BENCH/'benchmarks/v1/hidden/evaluator-instructions.md',
             RUN/'scenarios/B001/input/stage-1/fixtures.json',
             ROOT_PARENT/'hvac-business-reference/benchmarks/v1/scoring-policy.md',
             ROOT_PARENT/'hvac-crm-yolo/app/package.json']
    expression='const fs=require("fs");console.log(JSON.stringify('+json.dumps([str(x) for x in targets])+'.map(p=>{try{fs.readFileSync(p);return true}catch(e){return false}})))'
    probe=subprocess.run(['/usr/bin/sandbox-exec','-f',str(directory/'sandbox.sb'),
                          subprocess.check_output(['which','node'],text=True).strip(),'-e',expression],
                         cwd=APP,capture_output=True,text=True,check=True)
    check('candidate can read runtime, cannot read hidden/source repositories/other scenarios',json.loads(probe.stdout)==[True,True,False,False,False,False])
    expression='const net=require("net");const s=net.connect(443,"1.1.1.1");s.on("error",e=>{console.log(e.code);process.exit(0)});setTimeout(()=>process.exit(2),1000)'
    probe=subprocess.run(['/usr/bin/sandbox-exec','-f',str(directory/'sandbox.sb'),
                          subprocess.check_output(['which','node'],text=True).strip(),'-e',expression],
                         cwd=APP,capture_output=True,text=True)
    check('candidate outbound network denied',probe.returncode==0 and ('EPERM' in probe.stdout or 'EACCES' in probe.stdout))
    status_code,headers,body=request('POST','/api/auth/login',{'email':'coordinator@pilot.invalid','password':'frostline'})
    check('supported login succeeds',status_code==200)
    cookie=next(v.split(';',1)[0] for k,v in headers if k.lower()=='set-cookie')
    status_code,_,_=request('POST','/api/customers',{'name':'Readiness smoke customer'},cookie)
    check('pre-fidelity mutation blocked by explicit administration gate',status_code==423)
    send({'action':'acknowledge','text':'Readiness-only synthetic account. No episode task. Verify normal API transport, raw evidence, snapshots and browser capture; no business conclusion or score.'})
    status_code,_,body=request('POST','/api/customers',{'name':'Readiness smoke customer'},cookie)
    check('normal authenticated API mutation passes through unchanged',status_code==200 and json.loads(body)['name']=='Readiness smoke customer')
    customer_id=json.loads(body)['id']
    status_code,_,_=request('GET',f'/api/customers/{customer_id}',cookie=cookie)
    check('native supported post-state observable',status_code==200)
    from operator_api import run
    replay=run([dict(email='coordinator@pilot.invalid',method='GET',path='/api/customers',
                     rationale='Readiness-only operator API transport check',save_as='actual')])
    check('operator-selected API runner observes actual native response',replay[0]['status']==200 and any(r['id']==customer_id for r in replay[0]['body']))
    for path in ['/pilot/files/../../../../admin/benchmark/benchmarks/v1/hidden/evaluator-instructions.md',
                 '/pilot/files/stage-2/event.json','/pilot/scoring-policy.md']:
        check('source route refuses '+path,request('GET',path)[0]==404)
    # A fabricated hidden path sent to the SPA resolves only to its index.
    code,_,body=request('GET','/benchmarks/v1/hidden/evaluator-instructions.md')
    check('SPA fallback never exposes evaluator file',b'Independent evaluator instructions' not in body)
    send({'action':'boundary','text':'Readiness transport check complete; synthetic customer captured. Not a benchmark episode.',
          'email':'coordinator@pilot.invalid','paths':['/','/customers','/inbox']})
    trace=[json.loads(x) for x in (directory/'observations/trace.jsonl').read_text().splitlines()]
    check('actor identity captured from native session',any(e.get('actor',{}).get('role')=='coordinator' for e in trace if isinstance(e.get('actor'),dict)))
    check('raw request and response retained',any((p/'request.bin').exists() and (p/'response.bin').exists() for p in (directory/'observations/http').iterdir()))
    check('before/after state snapshots retained',sum(e['kind']=='state_snapshot' for e in trace)>=5)
    check('UI screenshot and DOM evidence retained',bool(list((directory/'observations/browser').rglob('desktop.png'))) and bool(list((directory/'observations/browser').rglob('dom.html'))))
    check('stage paused',send({'action':'status'})['at_boundary'])
    check('paused mutation administration blocked',request('POST','/api/customers',{'name':'Should not be created'},cookie)[0]==423)
    try: send({'action':'deliver-next'})
    except ValueError: denied=True
    else: denied=False
    check('undeclared next stage refused',denied)
    seal=send({'action':'seal'})
    check('observation bundle sealed',seal['sealed'])
    check('sealed evidence manifest verifies',verify_bundle(directory)['valid'])
    check('sealed runtime refuses writes',request('POST','/api/customers',{'name':'After seal'},cookie)[0]==423)
    previous='0'*64
    trace=[json.loads(x) for x in (directory/'observations/trace.jsonl').read_text().splitlines()]
    for e in trace:
        check('append-only chain '+e['ref'],e['previous_sha256']==previous)
        digest=e.pop('sha256')
        check('event hash '+e['ref'],hashlib.sha256(json.dumps(e,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==digest)
        previous=digest
    send({'action':'stop'})


ROOT_PARENT=RUN.parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    static()
    if args.live: live()
    report=dict(date=time_now(),passed=len(checks),checks=checks,
                scope='administration readiness only',candidate_tasks_started=0,candidate_scores_created=0)
    (RUN/'readiness/checks.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(checks)} readiness checks passed; no benchmark task or scoring performed.')


def time_now():
    from pilot import now
    return now()


if __name__=='__main__':
    main()
