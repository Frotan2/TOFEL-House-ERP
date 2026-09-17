"""Recover only sanitized Placement qualification artifacts on an ephemeral runner."""
import hashlib
import base64
import gzip
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
sys_path = ROOT / 'tools'
import sys
sys.path.insert(0, str(sys_path))
from session_branch import ACTIVE_REF

# This workflow runs from the active session branch. The source branch below
# is historical evidence provenance and is checked separately; it is not an
# authorization to execute qualification on that old branch.
HISTORICAL_SOURCE_BRANCH='arena/01a09bf3-tofel-house-erp'
if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REF')!=ACTIVE_REF:
    raise SystemExit('Authorized hosted branch only')
run=os.environ['SOURCE_RUN']
if not run.isdigit():raise SystemExit('Numeric source run required')
out=ROOT/'.foundation/recovered-placement'/run;out.mkdir(parents=True,exist_ok=True)
metadata=json.loads(subprocess.check_output(['gh','api',f'repos/{os.environ["GITHUB_REPOSITORY"]}/actions/runs/{run}']))
if metadata['head_branch']!=HISTORICAL_SOURCE_BRANCH or metadata['name']!='Placement synthetic content qualification':
    raise SystemExit('Not an authorized placement qualification source')
subprocess.run(['gh','run','download',run,'--name',f'placement-content-{run}-{metadata["run_attempt"]}','--dir',str(out/'artifact')],check=True)
# Read only the runner's sanitized report/log directory, never site configs/backups.
folder=next((out/'artifact').rglob('placement-evidence'))
reports={p.name:json.loads(p.read_text()) for p in folder.glob('*.json')}
logs={p.name:p.read_text() for p in folder.glob('*.txt')}
record={'status':'pass' if reports.get('result.json',{}).get('status')=='pass' else 'fail',
        'scope':'Lossless recovery of sanitized hosted placement evidence, not new execution',
        'source_run':run,'source_commit':metadata['head_sha'],'source_url':metadata['html_url'],
        'reports':reports,'logs':logs}
(out/'recovered.json').write_text(json.dumps(record,indent=2)+'\n')

# Split losslessly rather than truncating full logs to the Checks API text cap.
raw=json.dumps(record,separators=(",",":"),ensure_ascii=True).encode()
encoded=base64.b64encode(gzip.compress(raw,mtime=0)).decode()
chunks=[encoded[i:i+42000] for i in range(0,len(encoded),42000)]
for i,data in enumerate(chunks):
    part={"status":record["status"],"encoding":"gzip+base64-part","source_run":run,
          "source_commit":metadata["head_sha"],"payload_sha256":hashlib.sha256(raw).hexdigest(),
          "part":i,"parts":len(chunks),"data":data}
    target=out/f"part-{i}.json";target.write_text(json.dumps(part)+"\n")
    subprocess.run(["python3",str(ROOT/"tools/foundation/publish_evidence.py"),str(target),
                    "--name",f"Placement recovered {run} part {i+1}/{len(chunks)}"],check=True)
