#!/usr/bin/env python3
"""Administration completeness and evidence integrity only; never semantic scoring."""
import hashlib,json,stat,subprocess
from pathlib import Path
from collections import Counter
from pilot import RUN,ROOT,inventory,verify_bundle,sha,dependency_inventory

def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def main():
    suite=json.loads((RUN/'admin/benchmark/benchmarks/v1/suite-manifest.json').read_text())
    excludes=[json.loads(l) for l in (RUN/'reports/invalid-attempts.jsonl').read_text().splitlines()]
    excluded={(x['scenario_id'],x['attempt']) for x in excludes}
    progress=[json.loads(l) for l in (RUN/'reports/administration-progress.jsonl').read_text().splitlines()]
    selected={}
    for x in progress:
        if (x['scenario_id'],x['attempt']) not in excluded:selected[x['scenario_id']]=x
    records=[];failures=[]
    for entry in suite['scenarios']:
        sid=entry['id'];row=selected.get(sid)
        if not row:failures.append(sid);continue
        directory=Path(row['directory']);obs=directory/'observations';m=json.loads((directory/'bundle-manifest.json').read_text())
        verify_bundle(directory)
        trace=[json.loads(l) for l in (obs/'trace.jsonl').read_text().splitlines()]
        previous='0'*64;stage=1;boundaries=[];faults=[];http_errors=[];requests={};counts=Counter();pages=[];mutations=0;legacy=[]
        for event in trace:
            original=dict(event);actual=original.pop('sha256')
            assert original['previous_sha256']==previous,(sid,event['ref'],'trace link')
            if digest(original)!=actual:
                # Legacy emitter hashed a per-file sha256 then overwrote that
                # key with the event digest. Reproduce from sealed file bytes;
                # never alter the original trace or invent replacement hashes.
                if event['kind']=='operator_artifact':original['sha256']=sha(obs/event['path'])
                elif event['kind']=='source_file_read':original['sha256']=sha(obs/'inputs'/event['path'])
                else:raise AssertionError((sid,event['ref'],'unexplained trace digest'))
                assert digest(original)==actual,(sid,event['ref'],'legacy digest reconstruction')
                legacy.append(event['ref'])
            previous=actual;kind=event['kind'];counts[kind]+=1
            if kind in ['harness_observation_fault','harness_browser_capture_fault']:faults.append(event)
            if kind=='later_source_event_delivered':
                assert boundaries==list(range(1,stage+1)) and event['stage']==stage+1 and event['same_database']
                stage=event['stage']
            if kind=='stage_boundary':assert event['stage']==stage;boundaries.append(stage)
            if kind=='supported_http_request':
                assert event['stage']==stage
                requests[event['request_id']]=event
                assert sha(obs/event['artifact']/'request.bin')==event['body_sha256']
                mutations+=event['method'] not in ['GET','HEAD','OPTIONS'] and not event['path'].startswith('/api/auth/')
            if kind=='supported_http_response':
                request=requests[event['request_id']]
                assert sha(obs/request['artifact']/'response.bin')==event['body_sha256']
                if event['status']>=400:http_errors.append(dict(ref=event['ref'],stage=event['stage'],path=request['path'],method=request['method'],status=event['status']))
            if kind=='browser_capture':
                folder=obs/event['artifact']
                for path in folder.glob('*/page.json'):
                    page=json.loads(path.read_text());text=(path.parent/'text.txt').read_text()
                    pages.append(dict(stage=event['stage'],requested_path=page['requested_path'],actual_url=page['url'],page_not_found='Page not found.' in text))
        assert boundaries==list(range(1,entry['stages']+1))==m['completed_stages']
        assert not m['scored'] and not row['observation_invalid'] and not faults
        assert counts['runtime_isolation_verified']==1 and counts['operator_fidelity_acknowledgement']==1
        ready=next(e for e in trace if e['kind']=='sandboxed_runtime_ready');assert ready['ai_enabled'] is False
        isolation=next(e for e in trace if e['kind']=='runtime_isolation_verified')
        assert isolation['prior_listener_absent'] and Path(isolation['database'])==directory/'data/frostline.db'
        assert not any(e['kind']=='supported_http_request' and e['method'] not in ['GET','HEAD','OPTIONS'] and (e['path'].startswith('/api/ai/') or e['path'].startswith('/api/settings')) for e in trace)
        expected=json.loads((RUN/'scenarios'/sid/'baseline/input-hashes.json').read_text())
        assert inventory(obs/'inputs/stage-1')==expected
        for n in range(2,entry['stages']+1):
            actual=inventory(obs/'inputs'/f'stage-{n}')
            assert set(actual)=={'submission-contract.md','event.json','event.md'}
            delivered=next(e for e in trace if e['kind']=='later_source_event_delivered' and e['stage']==n)
            assert actual==delivered['hashes']
        readonly=all((p.stat().st_mode & 0o222)==0 for p in obs.rglob('*') if p.is_file());assert readonly
        records.append(dict(scenario_id=sid,attempt=row['attempt'],directory=str(directory.relative_to(ROOT)),completed_stages=boundaries,sealed=True,file_hashes_valid=True,trace_chain_valid=True,legacy_trace_hash_field_reconstruction_refs=legacy,read_only_files=True,files=len(m['files']),trace_events=len(trace),browser_pages=pages,http_errors=http_errors,observed_mutation_requests=mutations,bundle_sha256=m['observation_bundle_sha256'],scored=False))
    provenance=json.loads((RUN/'admin/provenance.json').read_text());sources={}
    for name,value in provenance.items():
        repo=Path(value['source']);ref=value['ref']
        commit=subprocess.check_output(['git','-C',str(repo),'rev-parse',ref+'^{commit}'],text=True).strip()
        obj=subprocess.check_output(['git','-C',str(repo),'rev-parse',ref],text=True).strip()
        status=subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True)
        paths=['app'] if name=='hvac-crm-yolo' else ['benchmarks/v1','docs']
        archive=subprocess.check_output(['git','-C',str(repo),'archive',ref,*paths])
        archive_hash=hashlib.sha256(archive).hexdigest()
        assert commit==value['commit'] and obj==value['reference_object'] and archive_hash==value['archive_sha256'] and not status
        sources[name]=dict(commit=commit,reference_object=obj,archive_sha256=archive_hash,working_tree_clean=True)
    assert inventory(RUN/'candidate/app',('node_modules','dist','data'))==json.loads((RUN/'admin/candidate-source-hashes.json').read_text())
    assert inventory(RUN/'candidate/app/dist')==json.loads((RUN/'admin/build-hashes.json').read_text())
    assert dependency_inventory()==json.loads((RUN/'admin/dependency-hashes.json').read_text())
    report=dict(run_id='pilot-001',phase='administration and evidence collection only',scored=False,scenario_count=len(records),declared_scenario_count=len(suite['scenarios']),completed_stage_count=sum(len(x['completed_stages']) for x in records),failed_or_incomplete_administration_scenarios=failures,excluded_attempts=excludes,sources=sources,candidate_runtime_source_build_dependencies_unchanged=True,scenarios=records,integrity_valid=not failures,trace_hash_contract_note='Legacy operator_artifact/source_file_read events hashed a file sha256 field before overwriting the same key with the event digest. Verification restores that input field from the sealed referenced file in memory and reproduces the original event digest exactly; no evidence files are modified.')
    destination=RUN/'reports/administration-audit.json'
    if destination.exists() and not (destination.stat().st_mode & 0o222):
        assert json.loads(destination.read_text())==report,'Current verification differs from sealed administration audit'
    else:destination.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['scenarios','sources','excluded_attempts']},indent=2))
if __name__=='__main__':main()
