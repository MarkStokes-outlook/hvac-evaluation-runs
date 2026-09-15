#!/usr/bin/env python3
"""Operator transport/evidence helpers. Business choices are supplied per stage.

Does not read hidden files or generate scenario answers. Every action goes through
the same recorded candidate HTTP API used by the UI. Supports source-only native
activities without inventing customer identity, physical tests or downstream acts.
"""
import argparse
import json
from pathlib import Path
import time
import subprocess
import sys

from pilot import RUN, send, verify_bundle
from operator_api import run


def start(sid,attempt):
    from pilot import ROOT, SOCKET
    if SOCKET.exists():raise ValueError('Another administration session is active')
    log_path=RUN/'admin/runtime-start-logs'/f'{sid}-{attempt}-{time.time_ns()}.log'
    log_path.parent.mkdir(parents=True,exist_ok=True)
    with log_path.open('wb') as log:
        process=subprocess.Popen([sys.executable,'-B',str(ROOT/'harness/pilot.py'),'serve',sid,'--attempt',attempt],
                                 stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    for _ in range(200):
        if process.poll() is not None:raise RuntimeError(log_path.read_text())
        if SOCKET.exists():
            status=send({'action':'status'})
            if status['scenario_id']!=sid:raise RuntimeError('Unexpected scenario on control socket')
            if sid!='SMOKE':ack(sid)
            return send({'action':'status'})
        time.sleep(.1)
    raise RuntimeError('Runtime startup timed out; see '+str(log_path))


def ack(sid):
    status=send({'action':'status'})
    if status['scenario_id']!=sid: raise ValueError('Active scenario mismatch')
    source=Path(status['directory'])/'input/stage-1'
    case=(source/'case.md').read_text()
    task=(source/'task.md').read_text()
    send({'action':'acknowledge','text':
        'Operator: Codex, acting only in the supplied FrostLine capacities. Reviewed exact initial public case/task/common contract and baseline adaptation log. Full source facts/unknowns preserved; native defaults/placeholders confer no business fact or authority. Candidate guidance limited to supported API/UI interactions. Context: prior administration/setup review; no hidden scenario oracle, rubric, reference reasoning, calibration answers or evaluator reasoning consulted for operation. Only canonical docs and current-stage facts govern business decisions. Optional AI disabled. No candidate repair/configuration or external credentials. All external acts sandboxed as exact issued instructions; no invented downstream completion/approval. Soft 30-minute stage budget; elapsed time is diagnostic only.'})
    send({'action':'note','origin':'administrator delivers exact public inputs','classification':'public task delivery',
          'text':task+'\n\n'+case})
    return send({'action':'status'})


def execute(sid,path):
    status=send({'action':'status'})
    if status['scenario_id']!=sid: raise ValueError('Active scenario mismatch')
    plan=json.loads(Path(path).read_text())
    stage=status['stage']
    if plan['scenario_id']!=sid or plan['stage']!=stage: raise ValueError('Action plan stage mismatch')
    # Preserve the literal operator plan in the immutable evidence workflow.
    send({'action':'capture','file':str(Path(path).resolve()),
          'text':f'Literal operator-selected actions, {sid} stage {stage}; authored from public case and canonical docs only.',
          'origin':'operator'})
    results=run(plan['actions'])
    output=RUN/'operator-work'/sid/f'stage-{stage}-results-{time.time_ns()}.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
    send({'action':'capture','file':str(output),'text':'Exact supported API results, including errors; no inferred successful business state','origin':'candidate HTTP responses captured by operator'})
    if len(results)==len(plan['actions']) and all(r['status']<400 for r in results):
        for event in plan.get('sandbox_events',[]):
            send(dict(action='sandbox-event',origin='operator issues exact instruction recorded in candidate operation',
                      classification='instruction only; downstream completion/acceptance not invented',
                      text=event['text'],actor=event.get('actor'),source_refs=event.get('source_refs',[])))
    summary=[]
    for action,result in zip(plan['actions'],results):
        body=result['body']
        observation={k:v for k,v in body.items() if k in ['id','job_no','quote_no','po_no','status','invoice_status','error','message','name','counts','outcome','valuation','totals']} if isinstance(body,dict) else {'record_count':len(body)} if isinstance(body,list) else {'raw':result['raw_body'][:300]}
        summary.append(dict(method=action.get('method','GET'),path=action['path'],status=result['status'],observation=observation))
    print(json.dumps(dict(results_file=str(output),actions=summary),indent=2,ensure_ascii=False),flush=True)
    return results


def close(sid,handoff,paths,email):
    status=send({'action':'status'})
    if status['scenario_id']!=sid: raise ValueError('Active scenario mismatch')
    send({'action':'boundary','text':Path(handoff).read_text(),'paths':paths,'email':email})
    print(json.dumps(send({'action':'status'}),indent=2))


def finish(sid,handoff,paths,email):
    close(sid,handoff,paths,email)
    status=send({'action':'status'})
    sealed=send({'action':'seal'})
    result=verify_bundle(status['directory'])
    send({'action':'stop'})
    from pilot import SOCKET
    for _ in range(100):
        if not SOCKET.exists():break
        time.sleep(.05)
    if SOCKET.exists():raise RuntimeError('Runtime stop did not complete')
    record=dict(scenario_id=sid,attempt=Path(status['directory']).name,completed_stages=status['completed_stages'],
                sealed=True,integrity_verified=result['valid'],bundle_sha256=sealed['bundle_sha256'],
                observation_invalid=status['invalid'],directory=status['directory'],scored=False)
    path=RUN/'reports/administration-progress.jsonl'
    with path.open('a') as stream:stream.write(json.dumps(record)+'\n')
    print(json.dumps(record,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('batch');p.add_argument('literal_list')
    p=sub.add_parser('administer');p.add_argument('scenario');p.add_argument('plan');p.add_argument('handoff');p.add_argument('--attempt',default='operational-001');p.add_argument('--path',action='append',default=[]);p.add_argument('--email',default='coordinator@pilot.invalid')
    p=sub.add_parser('ack');p.add_argument('scenario')
    p=sub.add_parser('start');p.add_argument('scenario');p.add_argument('--attempt',required=True)
    p=sub.add_parser('execute');p.add_argument('scenario');p.add_argument('plan')
    p=sub.add_parser('boundary');p.add_argument('scenario');p.add_argument('handoff')
    p.add_argument('--path',action='append',default=[]);p.add_argument('--email',default='coordinator@pilot.invalid')
    p=sub.add_parser('finish');p.add_argument('scenario');p.add_argument('handoff')
    p.add_argument('--path',action='append',default=[]);p.add_argument('--email',default='coordinator@pilot.invalid')
    args=parser.parse_args()
    if args.command=='batch':
        for entry in json.loads(Path(args.literal_list).read_text()):
            sid=entry['scenario'];plan=entry['plan'];print(json.dumps(start(sid,entry.get('attempt','operational-001'))),flush=True)
            results=execute(sid,plan)
            if len(results)!=len(json.loads(Path(plan).read_text())['actions']) or any(r['status']>=400 for r in results):raise RuntimeError('Candidate action did not complete; inspect recorded result before continuing')
            finish(sid,entry['handoff'],entry.get('paths',['/','/inbox']),entry.get('email','coordinator@pilot.invalid'))
    elif args.command=='administer':
        print(json.dumps(start(args.scenario,args.attempt)));execute(args.scenario,args.plan);finish(args.scenario,args.handoff,args.path or ['/','/inbox'],args.email)
    elif args.command=='start':print(json.dumps(start(args.scenario,args.attempt),indent=2))
    elif args.command=='ack': print(json.dumps(ack(args.scenario),indent=2))
    elif args.command=='execute':execute(args.scenario,args.plan)
    elif args.command=='finish':finish(args.scenario,args.handoff,args.path or ['/','/inbox'],args.email)
    else:close(args.scenario,args.handoff,args.path or ['/','/inbox'],args.email)


if __name__=='__main__':main()
