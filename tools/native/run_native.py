#!/usr/bin/env python3
"""Ephemeral hosted backend qualification. No production data or core edits."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
EXPORT_BRANCH = 'product-export'


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Hosted authorized branch only; no local/production execution')
    evidence = ROOT / '.foundation/placement-evidence';evidence.mkdir(parents=True, exist_ok=True)
    lab = Path(os.environ['RUNNER_TEMP']) / 'placement-runtime';lab.mkdir(mode=0o700)
    benchdir = lab / 'bench'; sources = lab / 'sources';sources.mkdir()
    matrix = json.loads((ROOT / 'docs/engineering/foundation-version-matrix.json').read_text())
    parts = {p['name']:p for p in matrix['components']}
    py = Path(os.environ['RUNNER_TEMP']) / 'foundation-runner-probe/python/bin/python3'
    secrets_ = [secrets.token_urlsafe(32) for _ in range(5)]
    rootpw, adminpw, dbpw, userpw, restorepw = secrets_
    for s in secrets_:print('::add-mask::'+s, flush=True)
    secretfile = lab/'db-password';secretfile.write_text(rootpw);secretfile.chmod(0o600)
    # The hosted image can supply a MySQL client while this qualification pins
    # MariaDB. MySQL 8's default histogram query is not implemented by MariaDB;
    # disable only that client-side optional metadata request, when supported.
    # Keep the wrapper ahead of Bench's PATH rather than changing the pinned DB.
    dump_binary = shutil.which('mysqldump')
    if not dump_binary:
        raise RuntimeError('Hosted runner has no mysqldump client for Bench backup')
    dump_help = subprocess.run([dump_binary, '--help'], text=True, capture_output=True, check=False).stdout
    dump_wrapper = lab/'tools/bin/mysqldump'; dump_wrapper.parent.mkdir(parents=True, exist_ok=True)
    dump_option = ' --column-statistics=0' if '--column-statistics' in dump_help else ''
    dump_wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(dump_binary) + dump_option + ' "$@"\n')
    dump_wrapper.chmod(0o700)
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
    def run(label,args,cwd=None,timeout=1200,input_text=None,env_overrides=None):
        started=time.monotonic();print(label,flush=True)
        child_env = dict(env)
        child_env.update(env_overrides or {})
        options = dict(cwd=cwd or lab,env=child_env,text=True,capture_output=True,timeout=timeout)
        if input_text is not None:
            options["input"] = input_text
        p=subprocess.run([str(a) for a in args],**options)
        (evidence/(label+'.txt')).write_text(redact(p.stdout+p.stderr))
        report['checks'].append(dict(name=label,exit_code=p.returncode,seconds=round(time.monotonic()-started,3)))
        if p.returncode:
            # Surface the redacted tail of the failed step in the runner-result
            # annotation itself: retained-log artifacts are not always reachable
            # from every evidence-retrieval environment.
            tail=redact(p.stdout+p.stderr).strip()[-2500:]
            raise RuntimeError(f'{label} failed (exit {p.returncode}); see retained log\n--- {label} log tail ---\n{tail}')
        return p.stdout.strip()
    def bench(label,*args):return run(label,[lab/'tools/bin/bench',*args],benchdir)
    def create_site(label,site,site_db_password,set_default=False):
        payload=json.dumps({'site':site,'db_root_password':rootpw,
                            'admin_password':adminpw,'db_password':site_db_password,
                            'db_host':'127.0.0.1','db_port':13306,
                            'set_default_site':set_default})
        return run(label,[py,ROOT/'tools/native/site_setup.py'],input_text=payload,
                   env_overrides={'SITE_BENCH_DIR':str(benchdir),
                                  'SITE_PYTHON':str(benchdir/'env/bin/python')})
    def product_backup(label,site):
        return run(label,[benchdir/'env/bin/python',ROOT/'tools/native/run_product_backup.py',site],
                   cwd=benchdir/'sites',
                   env_overrides={'BENCH_DIR':str(benchdir),'SITE_NAME':site})
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
            run('export-init-'+name,['git','init','--initial-branch',EXPORT_BRANCH,export])
            run('export-add-'+name,['git','-C',export,'add','.'])
            run('export-commit-'+name,['git','-C',export,'-c','user.name=Synthetic qualification','-c','user.email=validation@example.test','commit','-m','Exact app export '+os.environ['GITHUB_SHA']])
            bench('get-'+name,'get-app','--soft-link','--skip-assets',str(export))
        run('pip-check',[lab/'tools/bin/uv','pip','check','--python',benchdir/'env/bin/python'])
        for site in ('placement-test.localhost','placement-second.localhost'):
            create_site('new-'+site,site,dbpw)
            for name in ('erpnext','education','payments','hrms','foundation_security','toefl_house'):bench('install-'+site+'-'+name,'--site',site,'install-app',name)
            for key in ('allow_tests','toefl_house_synthetic_only','disable_website_cache'):bench('enable-'+site+'-'+key,'--site',site,'set-config',key,'1','--parse')
            bench('migrate-'+site,'--site',site,'migrate');bench('migrate-replay-'+site,'--site',site,'migrate')
        log=lab/'gunicorn.log';stream=log.open('w')
        server=subprocess.Popen([str(benchdir/'env/bin/gunicorn'),'--bind','127.0.0.1:18000','--workers','2','frappe.app:application'],cwd=benchdir/'sites',env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        processes.append((server,stream,log))
        run('native-acceptance',[benchdir/'env/bin/python',ROOT/'tools/native/native_checks.py'],benchdir/'sites')
        # D8-scoped synthetic persistence rehearsal. The product adapter calls
        # pinned Frappe native backup/restore while moving GPG/MariaDB secrets
        # off child argv. This is not Owner evidence, offsite backup, production
        # recovery objective, or a topology claim.
        expectation=lab/'product-restore-expectation.json'
        env['PLACEMENT_RESTORE_EXPECTATION']=str(expectation)
        env['PLACEMENT_RESTORE_REPORT']=str(expectation)
        run('capture-product-restore-snapshot',[benchdir/'env/bin/python',ROOT/'tools/native/runtime_restore.py','capture','placement-test.localhost'],benchdir/'sites')
        bench('enable-native-backup-encryption','--site','placement-test.localhost','execute',
              "frappe.db.set_single_value('System Settings', 'encrypt_backup', 1)")
        product_backup('backup-placement-test-with-files','placement-test.localhost')
        backup_dir=benchdir/'sites'/'placement-test.localhost'/'private/backups'
        database_suffix='-database-enc.sql.gz'
        database=max(backup_dir.glob('*'+database_suffix),key=lambda p:p.stat().st_mtime_ns)
        backup_set=database.name[:-len(database_suffix)]
        private_files=backup_dir/(backup_set+'-private-files-enc.tar')
        public_files=backup_dir/(backup_set+'-files-enc.tar')
        for artifact in (database,private_files,public_files):
            if not artifact.is_file() or artifact.stat().st_size <= 0:
                raise RuntimeError('Native encrypted backup set is incomplete: '+artifact.name)
        sidecar=backup_dir/(backup_set+'-site_config_backup-enc.json')
        recovered_backup_config=json.loads(sidecar.read_text())
        backup_encryption_key=recovered_backup_config.get('backup_encryption_key')
        if not isinstance(backup_encryption_key,str) or not backup_encryption_key:
            raise RuntimeError('Native site-config sidecar did not preserve backup_encryption_key')
        report['product_backup']={label:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for label,p in
                                  (('database',database),('private_files',private_files),('public_files',public_files))}
        restore_site='placement-restore.localhost'
        create_site('new-placement-restore-site',restore_site,restorepw)
        restore_backup_dir=benchdir/'sites'/restore_site/'private/backups'
        restore_backup_dir.mkdir(parents=True,exist_ok=True)
        for artifact in (database,public_files,private_files):shutil.copy2(artifact,restore_backup_dir/artifact.name)
        for name in ('erpnext','education','payments','hrms','foundation_security','toefl_house'):bench('install-'+restore_site+'-'+name,'--site',restore_site,'install-app',name)
        for key in ('allow_tests','toefl_house_synthetic_only','disable_website_cache'):bench('enable-'+restore_site+'-'+key,'--site',restore_site,'set-config',key,'1','--parse')
        restore_payload=json.dumps({'site':restore_site,'backup_set':backup_set,
                                    'encryption_key':backup_encryption_key,
                                    'db_root_password':rootpw,'admin_password':adminpw})
        run('restore-placement-test-with-files',
            [benchdir/'env/bin/python',ROOT/'product/restore.py'],cwd=benchdir,
            input_text=restore_payload,
            env_overrides={'BENCH_DIR':str(benchdir),'SITE_NAME':restore_site})
        source_config=json.loads((benchdir/'sites'/'placement-test.localhost'/'site_config.json').read_text())
        restore_config_file=benchdir/'sites'/restore_site/'site_config.json'
        restore_config=json.loads(restore_config_file.read_text())
        assert source_config['db_name'] != restore_config['db_name']
        assert source_config.get('db_password') != restore_config.get('db_password')
        assert source_config.get('encryption_key')
        restore_config['encryption_key'] = source_config['encryption_key']
        for key in ('allow_tests','toefl_house_synthetic_only','disable_website_cache'):restore_config[key]=source_config[key]
        restore_config_file.write_text(json.dumps(restore_config,indent=2)+'\n');restore_config_file.chmod(0o600)
        report['product_restore_context']={'separate_database':True,'source_db_credentials_copied':False,
                                           'site_encryption_key_restored':True,'site':restore_site}
        bench('migrate-placement-restore-site','--site',restore_site,'migrate')
        product_restore=evidence/'product-restore-result.json';env['PLACEMENT_RESTORE_REPORT']=str(product_restore)
        run('verify-product-restore-snapshot',[benchdir/'env/bin/python',ROOT/'tools/native/runtime_restore.py','verify',restore_site],benchdir/'sites')
        report['product_restore']=json.loads(product_restore.read_text())
        report['runtime_complete']=True
        report['installed_apps']=bench('list-apps','--site','placement-test.localhost','list-apps','--format','json')
        for name in ('frappe','erpnext','education','payments','hrms'):
            d=benchdir/'apps'/name
            assert run('final-sha-'+name,['git','-C',d,'rev-parse','HEAD'])==parts[name]['commit']
            assert not run('unchanged-'+name,['git','-C',d,'diff','--name-only'])
        report['status']='pass'
    except Exception as exc:
        report['status']='fail';report['failure']=redact(str(exc));print(report['failure'],flush=True)
        # Surface the failure as a check-run annotation.
        #
        # The job log is stored on a results blob that is not always
        # retrievable (the host returns EOF), which left a failing scenario
        # completely undiagnosable through the API: the run reported "failure"
        # at a step name and nothing else. Annotations are retrievable, so the
        # redacted traceback tail is emitted here as well. This adds
        # diagnosability only - the exit code and report status are unchanged.
        import traceback
        detail=redact(traceback.format_exc())
        report['traceback']=detail
        # Emit the exception type and the failing frames, not the tail of the
        # formatted text: an exception whose message embeds library warnings
        # pushes the actual `File .../line N` frames out of a fixed-size tail,
        # which is what happened on run 35420617771.
        frames=traceback.extract_tb(exc.__traceback__)
        emit=[f'{type(exc).__name__}: {redact(str(exc))[:600]}']
        emit += [f'at {f.filename}:{f.lineno} in {f.name}' for f in frames[-8:]]
        emit += [f'src> {redact((f.line or "").strip())[:300]}' for f in frames[-4:]]
        for line in emit:
            safe=line.replace('%','%25').replace('\r','%0D').replace('\n','%0A')
            print('::error::'+safe,flush=True)
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
