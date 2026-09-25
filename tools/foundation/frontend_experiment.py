#!/usr/bin/env python3
"""Frozen, isolated frontend comparison; never changes production qualification pins."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen

from seed_yarn_mirror import entries_from_lock, verify

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from session_branch import ACTIVE_REF
EVIDENCE = ROOT / '.foundation/frontend-experiment-evidence'

# Job logs and artifact zips EOF from the review environment, and the only
# record of a failure used to be result.json inside an undownloadable
# artifact. Annotations survive, so every check and the failure itself are
# written to the log as they happen.
ANNOTATION_TEXT_LIMIT = 700


def log(message):
    print(message, flush=True)


def failure_annotations(failure, last_failed_check):
    """Single-line ``::error::`` commands; multi-line dumps cannot annotate."""
    lines = []
    if last_failed_check:
        lines.append("::error file=tools/foundation/frontend_experiment.py::"
                     f"last failed check: {last_failed_check}")
    text = " ".join((failure or "frontend experiment failed without a recorded exception").split())
    if len(text) > ANNOTATION_TEXT_LIMIT:
        text = text[:ANNOTATION_TEXT_LIMIT - 3] + "..."
    lines.append(f"::error file=tools/foundation/frontend_experiment.py::{text}")
    return lines


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def seed(lock, mirror):
    # Accept npm's canonical tarball origin too; normalize ONLY for the strict
    # transport parser. The original frozen lock is never rewritten.
    text = lock.read_text().replace('"https://registry.npmjs.org/', '"https://registry.yarnpkg.com/')
    entries = entries_from_lock(text)
    mirror.mkdir(parents=True, exist_ok=True)
    def fetch(entry):
        target = mirror / entry['filename']
        if target.exists():
            verify(target.read_bytes(), entry['integrity'])
            return
        with urlopen(entry['url'], timeout=60) as response: data = response.read()
        verify(data, entry['integrity'])
        target.write_bytes(data)
    with ThreadPoolExecutor(max_workers=8) as executor: list(executor.map(fetch, entries))


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REF') != ACTIVE_REF:
        raise SystemExit('Authorized hosted branch only')
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    lab = Path(os.environ['RUNNER_TEMP']) / 'foundation-frontend-experiment'
    lab.mkdir()
    proposal = json.loads((ROOT / 'docs/engineering/evidence/phase-2/frontend-resolution-proposal.json').read_text())
    report = {'run_id':os.environ['GITHUB_RUN_ID'], 'commit':os.environ['GITHUB_SHA'], 'status':'running',
              'scope':'Isolated Education frontend candidate; not native ERPNext/Education or production compatibility approval',
              'production_pins_changed':False, 'production_gate_passed':False, 'profiles':{}, 'checks':[]}
    progress = {'last_failed_check': None}
    def run(name, command, cwd=ROOT, env=None, allowed=(0,)):
        result = subprocess.run([str(x) for x in command], cwd=cwd, env=env, text=True, capture_output=True, timeout=600)
        (EVIDENCE / (name+'.txt')).write_text(result.stdout+result.stderr)
        report['checks'].append({'name':name,'exit_code':result.returncode,'status':'pass' if result.returncode==0 else 'fail'})
        if result.returncode not in allowed:
            progress['last_failed_check'] = name
            # The full output stays in the artifact; the log gets the tail so
            # the reason is readable without downloading anything.
            log(f'[check:{name}] exit={result.returncode} allowed={allowed}')
            for line in (result.stdout + result.stderr).strip().splitlines()[-15:]:
                log(f'[check:{name}] {line[:400]}')
            raise RuntimeError(name+' failed: '+str(result.returncode))
        log(f'[check:{name}] exit={result.returncode}')
        return result.stdout.strip()
    try:
        report['node']=run('node-version',['node','--version'])
        report['yarn']=run('yarn-version',['yarn','--version'])
        assert report['node']=='v24.21.0' and report['yarn']=='1.22.22'
        for name in ('baseline','candidate'):
            p = report['profiles'][name] = {'status':'running'}
            source = lab / name / 'education'
            run(name+'-git-init',['git','init',source])
            run(name+'-git-fetch',['git','-C',source,'fetch','--depth','1','https://github.com/frappe/education.git',proposal['upstream_commit']])
            run(name+'-git-checkout',['git','-C',source,'checkout','--detach','FETCH_HEAD'])
            assert run(name+'-git-verify',['git','-C',source,'rev-parse','HEAD'])==proposal['upstream_commit']
            frontend = source / 'frontend'
            p['upstream_commit']=proposal['upstream_commit']
            p['upstream_manifest_sha256']=digest(frontend/'package.json')
            p['upstream_lock_sha256']=digest(frontend/'yarn.lock')
            p['source_sha256']={str(f.relative_to(frontend)):digest(f) for f in sorted((frontend/'src').rglob('*')) if f.is_file()}
            if name=='candidate':
                manifest=json.loads((frontend/'package.json').read_text())
                manifest['resolutions']=proposal['resolutions']
                for section in proposal['direct_dependency_sections']: manifest[section].update(proposal['direct_dependencies'])
                (frontend/'package.json').write_text(json.dumps(manifest,indent=2)+'\n')
                shutil.copyfile(ROOT/'docs/engineering/evidence/phase-2/frontend-candidate.yarn.lock',frontend/'yarn.lock')
            p['manifest_sha256']=digest(frontend/'package.json');p['lock_sha256']=digest(frontend/'yarn.lock')
            if name=='candidate':
                assert p['manifest_sha256']==proposal['candidate_manifest_sha256']
                assert p['lock_sha256']==proposal['candidate_lock_sha256']
            mirror=lab/'mirror';seed(frontend/'yarn.lock',mirror)
            (frontend/'.yarnrc').write_text(f'yarn-offline-mirror "{mirror}"\n')
            run(name+'-install',['yarn','install','--offline','--frozen-lockfile','--non-interactive'],frontend)
            assert digest(frontend/'yarn.lock')==p['lock_sha256'], 'Frozen lock changed'
            audit=EVIDENCE/(name+'-audit.json')
            run(name+'-audit',[sys.executable,ROOT/'tools/foundation/audit_frontend.py',frontend/'node_modules','--output',audit],allowed=(0,1))
            p['audit']=json.loads(audit.read_text())
            p['advisory_entries']=sum(map(len,p['audit']['advisories'].values()))
            edges=EVIDENCE/(name+'-edges.json')
            run(name+'-constraints',['node',ROOT/'tools/foundation/frontend_dependency_graph.cjs',frontend,edges])
            p['dependency_constraints']=json.loads(edges.read_text())
            run(name+'-production-build',['yarn','build'],frontend)
            p['build']='pass'
            smoke=EVIDENCE/(name+'-smoke.json')
            run(name+'-package-api-smoke',['node',ROOT/'tools/foundation/frontend_candidate_smoke.cjs',frontend,smoke])
            p['smoke']=json.loads(smoke.read_text())
            graph=EVIDENCE/(name+'-graph.json')
            env=dict(os.environ, FOUNDATION_FRONTEND_ROOT=str(frontend), FOUNDATION_GRAPH_BUILD=str(lab/(name+'-graph-assets')),
                     FOUNDATION_AUDIT_REPORT=str(audit), FOUNDATION_FRONTEND_GRAPH_REPORT=str(graph))
            run(name+'-module-graph',['node',ROOT/'tools/foundation/runtime_frontend_graph.cjs'],env=env)
            p['graph']=json.loads(graph.read_text())
            p['status']='fail' if p['advisory_entries'] or p['dependency_constraints']['issues'] else 'pass'
        a,b=report['profiles']['baseline'],report['profiles']['candidate']
        assert a['source_sha256']==b['source_sha256'], 'Application source changed'
        assert a['graph']['frappe_ui_source_sha256']==b['graph']['frappe_ui_source_sha256'], 'UI library source unexpectedly changed'
        report['unchanged_application_and_frappe_ui_source']=True
        report['candidate_dependency_constraints_passed']=not b['dependency_constraints']['issues']
        old={f['url'] for v in a['audit']['advisories'].values() for f in v}
        new={f['url'] for v in b['audit']['advisories'].values() for f in v}
        report['removed_advisories']=sorted(old-new);report['introduced_advisories']=sorted(new-old)
        report['status']='fail' if any(p['status']!='pass' for p in report['profiles'].values()) else 'pass'
    except Exception as exc:
        report.update(status='fail',failure=type(exc).__name__+': '+str(exc))
    finally:
        (EVIDENCE/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    if report['status'] != 'pass':
        if 'failure' not in report:
            # No exception: the gate failed on its own verdict (advisories or
            # dependency constraints), which is a different cause and must be
            # distinguishable in the log from a crashed check.
            report['failure'] = 'comparison gate rejected the candidate: ' + ', '.join(
                f"{name}: advisories={p.get('advisory_entries')} "
                f"constraint_issues={len((p.get('dependency_constraints') or {}).get('issues') or [])}"
                for name, p in sorted(report['profiles'].items()))
        for line in failure_annotations(report['failure'], progress['last_failed_check']):
            log(line)
    return 0 if report['status']=='pass' else 1


if __name__=='__main__': raise SystemExit(main())
