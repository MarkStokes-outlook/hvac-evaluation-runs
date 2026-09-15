#!/usr/bin/env python3
"""Stop only verified leftover pilot Node listeners after a harness fault."""
import os
import signal
import subprocess
import time
from pilot import APP, BACKEND_PORT, port_in_use

result=subprocess.run(['lsof','-t','-nP',f'-iTCP:{BACKEND_PORT}','-sTCP:LISTEN'],capture_output=True,text=True)
for pid in sorted(set(int(x) for x in result.stdout.split())):
    cwd=subprocess.run(['lsof','-a','-p',str(pid),'-d','cwd','-Fn'],capture_output=True,text=True).stdout.splitlines()
    command=subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True).strip()
    if 'n'+str(APP) not in cwd or 'node --import tsx server/index.ts' not in command:
        raise RuntimeError('Refusing to stop an unrelated listener')
    os.kill(pid,signal.SIGTERM)
    print(f'Stopped verified leftover pilot Node listener {pid}')
for _ in range(100):
    if not port_in_use():break
    time.sleep(.05)
else:raise RuntimeError('Listener survived cleanup')
print('Pilot backend port is free; no source files changed')
