"""Literal operator decision recorder; no scenario solution generation."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
C='coordinator@pilot.invalid'
def action(path,body=None,method='POST',email=C,refs=None,**extra):
    return dict(email=email,path=path,method=method,body=body,source_refs=refs or [],**extra)
def write(sid,decision,tasks,message,extra=None,stage=1,links=None,gets=None,email=C):
    links=links or {}; refs=[sid+' current public case/task','docs/governance/decision-rights-and-operational-authority.md','docs/operations/exceptions-handoffs-and-next-action-control.md']
    def activity(kind,subject,body):return action('/api/activities',dict(links,kind=kind,subject=subject,body=body,**({'direction':'outbound'} if kind=='email' else {})),email=email,refs=refs)
    actions=[action('/api/enquiries/1',method='GET',email=email),action('/api/enquiries/1',{'status':'in_progress'},'PATCH',email,refs)]
    actions += extra or []
    actions += [activity('note',sid+' source review and operator decision',decision)]
    actions += [activity('task',sid+' '+subject,body) for subject,body in tasks]
    if message:actions += [activity('email',sid+' sandbox issued communication',message)]
    actions += [action(path,method='GET',email=email) for path in (gets or ['/api/dashboard','/api/enquiries/1'])]
    events=[] if not message else [dict(actor='Codex in supplied duty capacity',source_refs=refs,text=message)]
    directory=ROOT/'pilot-001/operator-work'/sid;directory.mkdir(parents=True,exist_ok=True)
    (directory/f'stage-{stage}-plan.json').write_text(json.dumps(dict(scenario_id=sid,stage=stage,actions=actions,sandbox_events=events),indent=2))
    (directory/f'stage-{stage}-handoff.md').write_text(sid+' operator handoff, stage '+str(stage)+'\n\n'+decision+'\n\n'+ '\n\n'.join(subject+': '+body for subject,body in tasks)+'\n\nExact issued sandbox communication (no receipt/downstream acts inferred):\n'+message+'\n\nThe raw candidate responses, snapshots, source input and browser captures govern observable state. Notes/tasks are supported manual business records; no native domain action is inferred from prose. Required native defaults/host dates are not source facts or contractual authority. Original source retained. Unknown calendar dates are represented by body review triggers, not invented dates. No hidden scenario material, AI, repair or scoring used.\n')
