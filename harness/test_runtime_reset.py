#!/usr/bin/env python3
"""Two independent synthetic runtimes verify child shutdown and DB isolation."""
import json
import time
from administration_operator import start
from pilot import RUN, SOCKET, port_in_use, send
from operator_api import request

checks=[]
for index in [1,2]:
    status=start('SMOKE',f'reset-repair-{index}-{time.time_ns()}')
    send({'action':'acknowledge','text':'Synthetic runtime reset test only; no benchmark episode or business authority.'})
    login=request('POST','/api/auth/login',{'email':'coordinator@pilot.invalid','password':'frostline'})
    cookie=next(v.split(';',1)[0] for k,v in login['headers'] if k.lower()=='set-cookie')
    current=request('GET','/api/customers',cookie=cookie)
    assert current['body']==[], 'New runtime inherited prior synthetic records'
    checks.append(f'runtime-{index} clean supported API state')
    marker=request('POST','/api/customers',{'name':f'Synthetic isolation marker {index}'},cookie)
    assert marker['status']==200
    checks.append(f'runtime-{index} supported mutation captured')
    send({'action':'snapshot','text':'Synthetic reset-test final state'})
    send({'action':'stop'})
    for _ in range(100):
        if not SOCKET.exists() and not port_in_use():break
        time.sleep(.1)
    else:raise RuntimeError('Runtime/socket survived shutdown')
    checks.append(f'runtime-{index} process-group and listener stopped')
report=dict(passed=len(checks),checks=checks,scope='harness repair verification only',
            benchmark_tasks_executed=0,candidate_modified=False)
(RUN/'readiness/reset-repair-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
