"""Isolated Frappe patch-upgrade experiment; never switch live fixture app code."""
import json
import os
from pathlib import Path
import subprocess
import sys

OLD='33bf510b17afcaaa857ed38b921d8e9e50dcd232'
NEW='988e54f3c4c291e2077a83809663f123731abe76'

def main():
    if os.environ.get('GITHUB_ACTIONS')!='true': raise SystemExit('Disposable runner only')
    lab=Path(os.environ['FOUNDATION_LAB']); bench=lab/'upgrade-bench';cli=lab/'tools/bin/bench'
    report={'status':'running','scope':'Isolated five-upstream-app bundle with a Frappe patch upgrade; other app revisions held fixed; not rollback or full production acceptance','from_commit':OLD,'to_commit':NEW,'checks':[]}
    def run(label,cmd,cwd=None):
        r=subprocess.run([str(c) for c in cmd],cwd=cwd or lab,text=True,capture_output=True,timeout=1200)
        report['checks'].append({'name':label,'status':'pass' if r.returncode==0 else 'fail','exit_code':r.returncode})
        if r.returncode: raise RuntimeError(label+': '+r.stderr[-1200:])
        return r.stdout.strip()
    def b(label,*args):return run(label,[cli,*args],bench)
    try:
        source=lab/'upgrade-frappe-source'
        run('clone-pinned-previous-release',['git','clone','--depth','1','--branch','v16.33.0','https://github.com/frappe/frappe',source])
        assert run('verify-old-source',['git','-C',source,'rev-parse','HEAD'])==OLD
        run('isolated-bench-init',[cli,'init',bench,'--frappe-path',source,'--python',os.environ['FOUNDATION_BENCH_PYTHON'],'--no-backups','--skip-redis-config-generation','--no-procfile','--skip-assets'])
        for k,v in {'redis_cache':'redis://127.0.0.1:12379','redis_queue':'redis://127.0.0.1:11379','redis_socketio':'redis://127.0.0.1:11379'}.items():b('config-'+k,'set-config','--global',k,v)
        b('new-upgrade-site','new-site','upgrade.localhost','--db-name','foundation_upgrade_probe','--db-type','mariadb','--db-host','127.0.0.1','--db-port','13306','--db-root-password',os.environ['FOUNDATION_ROOT_PASSWORD'],'--db-password',os.environ['FOUNDATION_UPGRADE_PASSWORD'],'--admin-password',os.environ['FOUNDATION_ADMIN_PASSWORD'],'--mariadb-user-host-login-scope','%')
        root=Path(__file__).resolve().parents[2]
        matrix=json.loads((root/'docs/engineering/foundation-version-matrix.json').read_text())
        pins={c['name']:c for c in matrix['components']}
        report['held_fixed_apps']={}
        for app in ('erpnext','education','payments','hrms'):
            b('get-'+app,'get-app','--skip-assets',str(lab/'sources'/app))
            sha=run('verify-'+app,['git','-C',bench/'apps'/app,'rev-parse','HEAD'])
            assert sha==pins[app]['commit']
            report['held_fixed_apps'][app]=sha
            b('install-'+app,'--site','upgrade.localhost','install-app',app)
        os.environ['FOUNDATION_BUSINESS_REPORT']=str(lab/'upgrade-business.json')
        os.environ['FOUNDATION_RESTORE_REPORT']=str(lab/'upgrade-preservation.json')
        run('old-bundle-native-business-fixture',[bench/'env/bin/python',root/'tools/foundation/runtime_smoke.py','upgrade.localhost'],bench/'sites')
        report['business_before']=json.loads(Path(os.environ['FOUNDATION_BUSINESS_REPORT']).read_text())
        b('old-migrate' ,'--site','upgrade.localhost','migrate')
        b('old-build','build')
        raw=b('create-native-upgrade-marker','--site','upgrade.localhost','execute','frappe.client.insert','--kwargs',json.dumps({'doc':{'doctype':'ToDo','description':'Validation immutable upgrade marker'}}))
        doc=json.loads(raw); name=doc['name']
        b('pre-upgrade-backup','--site','upgrade.localhost','backup','--with-files')
        run('fetch-pinned-target',['git','-C',bench/'apps/frappe','fetch','https://github.com/frappe/frappe',NEW])
        run('advance-isolated-dependency',['git','-C',bench/'apps/frappe','checkout','--detach',NEW])
        assert run('verify-new-source',['git','-C',bench/'apps/frappe','rev-parse','HEAD'])==NEW
        b('target-requirements','setup','requirements')
        b('target-migrate','--site','upgrade.localhost','migrate')
        b('target-build','build')
        after=json.loads(b('read-native-upgrade-marker','--site','upgrade.localhost','execute','frappe.client.get','--kwargs',json.dumps({'doctype':'ToDo','name':name})))
        assert after['description']==doc['description'] and after['creation']==doc['creation']
        run('upgraded-bundle-records-files-and-schema',[bench/'env/bin/python',root/'tools/foundation/runtime_restore.py','upgrade.localhost'],bench/'sites')
        report['business_after']=json.loads(Path(os.environ['FOUNDATION_RESTORE_REPORT']).read_text())
        report['native_record_preserved']=True
        b('target-replay-migrate','--site','upgrade.localhost','migrate')
        report['status']='pass'
    except Exception as e:
        report['status']='fail';report['failure']=str(e)
    finally:
        Path(os.environ['FOUNDATION_UPGRADE_REPORT']).write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['status']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
