#!/usr/bin/env python3
"""Reproduce pilot extraction and build without changing either source repo."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=ROOT.parent
RUN=ROOT/'pilot-001'


def extract(repo,ref,paths,target):
    reference_object=subprocess.check_output(['git','-C',str(repo),'rev-parse',ref],text=True).strip()
    commit=subprocess.check_output(['git','-C',str(repo),'rev-parse',ref+'^{commit}'],text=True).strip()
    archive=subprocess.check_output(['git','-C',str(repo),'archive',ref,*paths])
    with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
        if target.exists() and any(target.iterdir()):
            # Verify pinned tracked files instead of overwriting existing data.
            for member in tree.getmembers():
                if member.isfile():
                    path=target/member.name
                    expected=tree.extractfile(member).read()
                    if not path.is_file() or path.read_bytes()!=expected:
                        raise ValueError('Existing extraction differs from frozen artefact: '+str(path))
        else:
            target.mkdir(parents=True,exist_ok=True)
            tree.extractall(target,filter='data')
    return dict(ref=ref,reference_object=reference_object,commit=commit,source=str(repo),archive_sha256=hashlib.sha256(archive).hexdigest())


def main():
    specs=[('hvac-crm-yolo','run-001-claude-opus-5-high-001',['app'],RUN/'candidate'),
           ('hvac-business-reference','frostline-fit-benchmark-v1.0.0',['benchmarks/v1','docs'],RUN/'admin/benchmark')]
    provenance={name:extract(WORKSPACE/name,ref,paths,target) for name,ref,paths,target in specs}
    (RUN/'admin').mkdir(parents=True,exist_ok=True)
    (RUN/'admin/provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    app=RUN/'candidate/app'
    installed=WORKSPACE/'hvac-crm-yolo/app'
    if not (app/'node_modules').exists():
        if (installed/'package-lock.json').read_bytes()!=(app/'package-lock.json').read_bytes():
            raise ValueError('Existing dependency lock differs from frozen candidate; install npm ci in the runtime copy instead')
        shutil.copytree(installed/'node_modules',app/'node_modules',symlinks=True)
    result=subprocess.run(['npm','run','build'],cwd=app,capture_output=True,text=True,check=True)
    (RUN/'readiness').mkdir(parents=True,exist_ok=True)
    (RUN/'readiness/build.log').write_text(result.stdout+result.stderr)
    versions={name:subprocess.check_output([name,'--version'],text=True).strip() for name in ['node','npm','python3']}
    (RUN/'readiness/runtime-versions.json').write_text(json.dumps(versions,indent=2)+'\n')
    listing=subprocess.run(['npm','ls','--json','--depth=0'],cwd=app,capture_output=True,text=True)
    (RUN/'readiness/installed-packages.json').write_text(listing.stdout)
    if listing.returncode:
        raise ValueError('Dependency listing reports a problem; inspect installed-packages.json')
    print(json.dumps(dict(extracted=provenance,built=True,versions=versions),indent=2))


if __name__=='__main__':main()
