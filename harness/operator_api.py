#!/usr/bin/env python3
"""Execute operator-selected actions through the candidate's supported HTTP API.

No rubric, oracle, desired business assertions, database writes or automatic
scenario solution is present. An action plan records literal choices made by
the operator. Responses can supply IDs for later actions using JSON pointers.
"""
import argparse
import http.client
import json
from pathlib import Path
import re

from pilot import PUBLIC_PORT, RUN, send


def pointer(value,path):
    for part in path.lstrip('/').split('/') if path else []:
        part=part.replace('~1','/').replace('~0','~')
        value=value[int(part)] if isinstance(value,list) else value[part]
    return value


def resolve(value,responses):
    if isinstance(value,dict) and set(value)=={'$response','pointer'}:
        return pointer(responses[value['$response']],value['pointer'])
    if isinstance(value,dict): return {k:resolve(v,responses) for k,v in value.items()}
    if isinstance(value,list): return [resolve(v,responses) for v in value]
    return value


def request(method,path,body=None,cookie=None):
    if not path.startswith('/api/') or path.startswith('//'):
        raise ValueError('Only supported candidate /api/ paths accepted')
    route_list=json.loads((RUN/'admin/supported-api-routes.json').read_text())
    clean_path=path.split('?',1)[0]
    supported=any(route['method']==method and re.fullmatch(re.sub(r':[A-Za-z_]+',r'[^/]+',route['path']),clean_path) for route in route_list)
    if not supported: raise ValueError(f'Not in supported route catalogue: {method} {path}')
    connection=http.client.HTTPConnection('127.0.0.1',PUBLIC_PORT,timeout=120)
    headers={'Content-Type':'application/json'}
    if cookie: headers['Cookie']=cookie
    payload=None if body is None else json.dumps(body,ensure_ascii=False).encode()
    connection.request(method,path,body=payload,headers=headers)
    response=connection.getresponse()
    raw=response.read()
    result=dict(status=response.status,headers=response.getheaders(),raw_body=raw.decode('utf-8',errors='replace'))
    try: result['body']=json.loads(raw)
    except (json.JSONDecodeError,UnicodeDecodeError): result['body']=None
    connection.close()
    return result


def run(actions):
    status=send({'action':'status'})
    if status['sealed'] or status['at_boundary'] or not status['fidelity_acknowledged']:
        raise ValueError('Actions require acknowledged active stage')
    cookies={};responses={};results=[]
    initial_stage=status['stage']
    for index,action in enumerate(actions):
        current=send({'action':'status'})
        if current['stage']!=initial_stage or current['at_boundary'] or current['sealed']:
            raise ValueError('Stage changed while action plan was running')
        email=action['email']
        if email not in cookies:
            login=request('POST','/api/auth/login',{'email':email,'password':'frostline'})
            if login['status']!=200: raise ValueError('Sandbox login failed')
            cookies[email]=next(v.split(';',1)[0] for k,v in login['headers'] if k.lower()=='set-cookie')
        method=action.get('method','GET').upper()
        body=resolve(action.get('body'),responses)
        path=action['path']
        for name,value in action.get('path_responses',{}).items():
            path=path.replace('{'+name+'}',str(resolve(value,responses)))
        send({'action':'note','origin':'operator',
              'classification':'operator-selected supported API action; no harness business judgement',
              'text':json.dumps(dict(email=email,method=method,path=path,body=body,
                   rationale=action.get('rationale',''),authority_source_refs=action.get('source_refs',[])),ensure_ascii=False)})
        result=request(method,path,body,cookies[email])
        results.append(result)
        if 'save_as' in action:
            if action['save_as'] in responses: raise ValueError('Duplicate response reference')
            responses[action['save_as']]=result['body']
        if result['status']>=400 and not action.get('continue_on_http_error',False):
            # Report an actual app response. Do not correct the action, label it
            # a policy failure or silently bridge an unsuccessful operation.
            break
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('request');p.add_argument('--email',required=True);p.add_argument('--method',default='GET')
    p.add_argument('--path',required=True);p.add_argument('--body-file');p.add_argument('--source-ref',action='append',default=[])
    p.add_argument('--rationale',default='')
    p=sub.add_parser('replay');p.add_argument('plan')
    args=parser.parse_args()
    if args.command=='request':
        body=json.loads(Path(args.body_file).read_text()) if args.body_file else None
        actions=[dict(email=args.email,method=args.method,path=args.path,body=body,
                      source_refs=args.source_ref,rationale=args.rationale)]
    else:
        value=json.loads(Path(args.plan).read_text())
        if set(value)-{'actions','operator','provenance'}: raise ValueError('Unknown plan fields')
        actions=value['actions']
    print(json.dumps(run(actions),indent=2,ensure_ascii=False))


if __name__=='__main__': main()
