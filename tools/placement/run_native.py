#!/usr/bin/env python3
"""Ephemeral hosted backend qualification. No production data or core edits."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
BRANCH = 'refs/heads/arena/01a0a055-tofel-house-erp'


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REF') != BRANCH:
        raise SystemExit('Hosted authorized branch only; no local/production execution')
    evidence = ROOT / '.foundation/placement-evidence';evidence.mkdir(parents=True, exist_ok=True)
    lab = Path(os.environ['RUNNER_TEMP']) / 'placement-runtime';lab.mkdir(mode=0o700)
    benchdir = lab / 'bench'; sources = lab / 'sources';sources.mkdir()
    matrix = json.loads((ROOT / 'docs/engineering/foundation-version-matrix.json').read_text())
    parts = {p['name']:p for p in matrix['components']}
    py = Path(os.environ['RUNNER_TEMP']) / 'foundation-runner-probe/python/bin/python3'
    secrets_ = [secrets.token_urlsafe(32) for _ in range(4)]
    rootpw, adminpw, dbpw, userpw = secrets_
    for s in secrets_:print('::add-mask::'+s, flush=True)
    secretfile = lab/'db-password';secretfile.write_text(rootpw);secretfile.chmod(0o600)
    env = dict(os.environ, PATH=str(lab/'tools/bin')+os.pathsep+os.environ['PATH'], UV_PYTHON_DOWNLOADS='never',
               UV_NATIVE_TLS='true', PYTHONUNBUFFERED='1', CI='1', PLACEMENT_TEST_PASSWORD=userpw,
               PLACEMENT_REPORT=str(evidence/'native-checks.json'))
    report = dict(scope='Synthetic content-governance backend increment; NOT full Placement qualification',
                  commit=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  status='running', checks=[], production='REJECT', runtime_complete=False)
    processes=[]
    def redact(text):
        values=list(secrets_)
        for f in benchdir.glob('sites/*/site_config.json'):
            data=json.loads(f.read_text());values.extend(str(v) for k,v in data.items() if any(x in k.lower() for x in ['password','secret','encryption_key']) and v)
        for v in values:text=text.replace(v,'[REDACTED]')
        return text
    def run(label,args,cwd=None,timeout=1200):
        started=time.monotonic();print(label,flush=True)
        p=subprocess.run([str(a) for a in args],cwd=cwd or lab,env=env,text=True,capture_output=True,timeout=timeout)
        (evidence/(label+'.txt')).write_text(redact(p.stdout+p.stderr))
        report['checks'].append(dict(name=label,exit_code=p.returncode,seconds=round(time.monotonic()-started,3)))
        if p.returncode:raise RuntimeError(f'{label} failed (exit {p.returncode}); see retained log')
        return p.stdout.strip()
    def bench(label,*args):return run(label,[lab/'tools/bin/bench',*args],benchdir)
    try:
        run('python-version',[py,'--version']);run('node-version',['node','--version']);run('yarn-version',['yarn','--version'])
        run('tools-env',[py,'-m','venv',lab/'tools'])
        run('tools-install',[lab/'tools/bin/python','-m','pip','install','frappe-bench==5.31.0','uv==0.11.6'])
        (lab/'.yarnrc').write_text('--install.frozen-lockfile true\n--install.non-interactive true\n')
        for name in ('frappe','erpnext','education','payments','hrms'):
            d=sources/name;c=parts[name]
            run('init-'+name,['git','init',d]);run('origin-'+name,['git','-C',d,'remote','add','origin',c['repository']])
            run('fetch-'+name,['git','-C',d,'fetch','--depth','1','origin',c['commit']])
            run('checkout-'+name,['git','-C',d,'checkout','--detach','FETCH_HEAD'])
            assert run('sha-'+name,['git','-C',d,'rev-parse','HEAD'])==c['commit']
        for name,port in [('mariadb','13306:3306'),('redis-queue','11379:6379'),('redis-cache','12379:6379')]:
            image=parts['mariadb' if name=='mariadb' else 'redis']['image_digest'];assert '@sha256:' in image
            args=['docker','run','--detach','--name','placement-'+name,'--publish','127.0.0.1:'+port]
            if name=='mariadb':args+=['--mount',f'type=bind,source={secretfile},target=/run/secrets/db-password,readonly','--env','MARIADB_ROOT_PASSWORD_FILE=/run/secrets/db-password','--env','MARIADB_ROOT_HOST=%','--health-cmd','healthcheck.sh --connect --innodb_initialized','--health-interval','2s','--health-retries','30',image,'--character-set-server=utf8mb4','--collation-server=utf8mb4_unicode_ci']
            else:args+=[image]
            run('start-'+name,args)
        for _ in range(60):
            if subprocess.check_output(['docker','inspect','placement-mariadb','--format','{{.State.Health.Status}}'],text=True).strip()=='healthy':break
            time.sleep(2)
        else:raise RuntimeError('MariaDB readiness timeout')
        benchinit=[lab/'tools/bin/bench','init',benchdir,'--frappe-path',sources/'frappe','--python',py,'--no-backups','--skip-redis-config-generation','--no-procfile','--skip-assets','--verbose']
        run('bench-init',benchinit)
        for key,value in {'redis_cache':'redis://127.0.0.1:12379','redis_queue':'redis://127.0.0.1:11379','redis_socketio':'redis://127.0.0.1:11379'}.items():bench('config-'+key,'set-config','--global',key,value)
        for name in ('erpnext','education','payments','hrms'):bench('get-'+name,'get-app','--skip-assets',str(sources/name))
        for name in ('foundation_security','toefl_house'):
            export=lab/'owned'/name;shutil.copytree(ROOT/'apps'/name,export,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            run('export-init-'+name,['git','init','--initial-branch','arena/01a0a055-tofel-house-erp',export])
            run('export-add-'+name,['git','-C',export,'add','.'])
            run('export-commit-'+name,['git','-C',export,'-c','user.name=Synthetic qualification','-c','user.email=validation@example.test','commit','-m','Exact app export '+os.environ['GITHUB_SHA']])
            bench('get-'+name,'get-app','--soft-link','--skip-assets',str(export))
        run('pip-check',[lab/'tools/bin/uv','pip','check','--python',benchdir/'env/bin/python'])
        for site in ('placement-test.localhost','placement-second.localhost'):
            bench('new-'+site,'new-site',site,'--db-type','mariadb','--db-host','127.0.0.1','--db-port','13306','--db-root-username','root','--db-root-password',rootpw,'--admin-password',adminpw,'--db-password',dbpw,'--no-mariadb-socket')
            for name in ('erpnext','education','payments','hrms','foundation_security','toefl_house'):bench('install-'+site+'-'+name,'--site',site,'install-app',name)
            for key in ('allow_tests','toefl_house_synthetic_only','disable_website_cache'):bench('enable-'+site+'-'+key,'--site',site,'set-config',key,'1','--parse')
            bench('migrate-'+site,'--site',site,'migrate');bench('migrate-replay-'+site,'--site',site,'migrate')
        log=lab/'gunicorn.log';stream=log.open('w')
        server=subprocess.Popen([str(benchdir/'env/bin/gunicorn'),'--bind','127.0.0.1:18000','--workers','2','frappe.app:application'],cwd=benchdir/'sites',env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        processes.append((server,stream,log))
        run('native-acceptance',[benchdir/'env/bin/python',ROOT/'tools/placement/native_checks.py'],benchdir/'sites')
        report['runtime_complete']=True
        report['installed_apps']=bench('list-apps','--site','placement-test.localhost','list-apps','--format','json')
        for name in ('frappe','erpnext','education','payments','hrms'):
            d=benchdir/'apps'/name
            assert run('final-sha-'+name,['git','-C',d,'rev-parse','HEAD'])==parts[name]['commit']
            assert not run('unchanged-'+name,['git','-C',d,'diff','--name-only'])
        report['status']='pass'
    except Exception as exc:
        report['status']='fail';report['failure']=redact(str(exc));print(report['failure'],flush=True)
    finally:
        for proc,stream,log in processes:
            try:
                os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=20)
            except ProcessLookupError:pass
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
            stream.close();(evidence/'gunicorn.txt').write_text(redact(log.read_text()))
        for name in ('mariadb','redis-queue','redis-cache'):
            subprocess.run(['docker','rm','--force','--volumes','placement-'+name],capture_output=True,timeout=30)
        secretfile.unlink(missing_ok=True)
        for p in evidence.glob('*.json'):p.write_text(redact(p.read_text()))
        (evidence/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
