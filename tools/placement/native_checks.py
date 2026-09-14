"""Real native DB/controller/HTTP acceptance on isolated synthetic sites only."""
import concurrent.futures
import copy
import json
import os
from pathlib import Path
import time
import traceback
from unittest.mock import patch
from urllib.parse import quote


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':raise RuntimeError('Hosted synthetic runner only')
    import frappe
    import requests
    from toefl_house import api
    from toefl_house.policy import digest
    output=Path(os.environ['PLACEMENT_REPORT'])
    report={'scope':'Real native content-governance increment only; not full T01–T20','status':'running','checks':[],
            'commit':os.environ['GITHUB_SHA'],'runtime_kind':'Frappe/MariaDB/Redis/HTTP','production':'REJECT'}
    users={'author':'synthetic-author@example.test','other':'synthetic-other@example.test',
           'publisher':'synthetic-publisher@example.test','auditor':'synthetic-auditor@example.test','outsider':'synthetic-outsider@example.test'}
    item=None
    def check(name,fn):
        start=time.monotonic()
        try:
            value=fn();frappe.db.commit()
            report['checks'].append({'name':name,'status':'pass','observation':value,'seconds':round(time.monotonic()-start,3)})
            return value
        except Exception as exc:
            frappe.db.rollback()
            report['checks'].append({'name':name,'status':'fail','exception':type(exc).__name__,'message':str(exc)[:600]})
            raise
        finally:output.write_text(json.dumps(report,indent=2,default=str)+'\n')
    def denied(fn):
        frappe.db.savepoint('denial')
        try:fn()
        except (frappe.PermissionError,frappe.ValidationError,frappe.DuplicateEntryError) as exc:return {'denied':type(exc).__name__}
        else:raise AssertionError('Expected denial was accepted')
        finally:frappe.db.rollback(save_point='denial')
    def content(answer='a'):
        return dict(skill='Grammar',difficulty='Entry',question_type='Single Choice',prompt='SYNTHETIC: select the fixture option.',options=[{'id':'a','text':'Fixture A'},{'id':'b','text':'Fixture B'}],answer=answer)
    def family(actor,tail):return 'SYN-'+digest(actor)[:12].upper()+'-'+tail
    def as_user(label,fn):frappe.set_user(users[label]);return fn()
    def connect(site):
        frappe.init(site=site,sites_path=str(Path.cwd()));frappe.connect();frappe.set_user('Administrator')
    try:
        for site in ('placement-test.localhost','placement-second.localhost'):
            connect(site)
            assert frappe.conf.allow_tests==1 and frappe.conf.toefl_house_synthetic_only==1
            def setup():
                mapping={'author':['Placement Author','Placement Publisher'],'other':['Placement Author'],
                         'publisher':['Placement Publisher'],'auditor':['Placement Auditor'],'outsider':[]}
                for label,roles in mapping.items():
                    frappe.get_doc(dict(doctype='User',email=users[label],first_name='Synthetic '+label,
                        enabled=1,send_welcome_email=0,new_password=os.environ['PLACEMENT_TEST_PASSWORD'],
                        roles=[{'role':r} for r in roles])).insert()
                return {'site':site,'users':len(users),'apps':frappe.get_installed_apps()}
            check('native-fixtures-'+site,setup);frappe.destroy()
        connect('placement-test.localhost')
        before_counts={dt:frappe.db.count(dt) for dt in ['Student','Student Applicant','Program Enrollment','Course Enrollment','Assessment Result','Sales Invoice','GL Entry','Salary Slip']}
        check('administrator-not-an-implicit-business-actor',lambda:denied(lambda:api.create_draft('admin_attempt_001',family(users['author'],'ADMIN'),1,content())))
        def disabled():
            original=frappe.conf.toefl_house_synthetic_only;frappe.conf.toefl_house_synthetic_only=0
            try:return denied(lambda:as_user('author',lambda:api.create_draft('disabled_gate_001',family(users['author'],'OFF'),1,content())))
            finally:frappe.conf.toefl_house_synthetic_only=original
        check('disabled-site-fails-closed',disabled)
        check('unrelated-role-denied',lambda:denied(lambda:as_user('outsider',lambda:api.create_draft('outsider_try_001',family(users['outsider'],'NO'),1,content()))))
        item=check('create-native-draft',lambda:as_user('author',lambda:api.create_draft('native_create_001',family(users['author'],'ONE'),1,content())))
        first_key=frappe.db.get_value(api.ITEM,item['name'],'key_revision')
        def replay():
            count=frappe.db.count(api.AUDIT)
            value=as_user('author',lambda:api.create_draft('native_create_001',family(users['author'],'ONE'),1,content()))
            assert value==item and frappe.db.count(api.AUDIT)==count
            return {'same_result':True,'no_duplicate_audit':True}
        check('idempotent-replay',replay)
        check('database-family-revision-unique',lambda:denied(lambda:as_user('author',lambda:api.create_draft('duplicate_family_001',family(users['author'],'ONE'),1,content()))))
        check('changed-payload-conflict',lambda:denied(lambda:as_user('author',lambda:api.create_draft('native_create_001',family(users['author'],'ONE'),1,content('b')))))
        check('changed-actor-conflict',lambda:denied(lambda:as_user('other',lambda:api.create_draft('native_create_001',family(users['author'],'ONE'),1,content()))))
        check('family-author-namespace-enforced',lambda:denied(lambda:as_user('other',lambda:api.create_draft('other_family_001',family(users['author'],'ONE'),2,content()))))
        check('self-publication-denied-despite-role-union',lambda:denied(lambda:as_user('author',lambda:api.publish('self_publish_001',item['name'],1))))
        item=check('revise-draft-append-key-history',lambda:as_user('author',lambda:api.revise_draft('native_revise_001',item['name'],1,content('b'))))
        def key_history():
            assert frappe.db.get_value(api.KEY,first_key,'answer')=='a'
            assert frappe.db.count(api.KEY,{'item_revision':item['name']})==2
            return {'old_key_preserved':True}
        check('old-key-not-overwritten',key_history)
        check('key-history-direct-update-denied',lambda:denied(lambda:frappe.get_doc(api.KEY,first_key).db_set('answer','b')))
        check('stale-draft-edit-denied',lambda:denied(lambda:as_user('author',lambda:api.revise_draft('native_stale_001',item['name'],1,content()))))
        check('other-author-edit-denied',lambda:denied(lambda:as_user('other',lambda:api.revise_draft('native_other_001',item['name'],2,content()))))
        item=check('independent-native-publication',lambda:as_user('publisher',lambda:api.publish('native_publish_001',item['name'],2)))
        assert item['status']=='Published'
        check('published-edit-denied',lambda:denied(lambda:as_user('author',lambda:api.revise_draft('published_edit_001',item['name'],3,content()))))
        def generic_write():
            frappe.set_user(users['author']);doc=frappe.get_doc(api.ITEM,item['name']);doc.prompt='SYNTHETIC: forged mutation';doc.flags.ignore_permissions=True
            return denied(lambda:doc.save(ignore_permissions=True))
        check('ignore-permissions-does-not-bypass-controller',generic_write)
        check('direct-db-set-denied',lambda:denied(lambda:frappe.get_doc(api.ITEM,item['name']).db_set('status','Draft')))
        check('direct-db-update-denied',lambda:denied(lambda:frappe.get_doc(api.ITEM,item['name']).db_update()))
        check('delete-denied',lambda:denied(lambda:frappe.delete_doc(api.ITEM,item['name'],ignore_permissions=True)))
        def native_reads():
            frappe.set_user(users['other']);doc=frappe.get_doc(api.ITEM,item['name']);assert doc.has_permission('read')
            key=frappe.get_doc(api.KEY,doc.key_revision);assert not key.has_permission('read')
            assert not frappe.get_list(api.KEY,filters={'item_revision':doc.name})
            frappe.set_user(users['auditor']);assert not key.has_permission('read')
            assert len(frappe.get_list(api.AUDIT,filters={'item_revision':doc.name}))==3
            return {'published_prompt_readable':True,'key_restricted':True,'audit_events':3}
        check('native-role-and-list-parity',native_reads)
        def rollback_proof():
            frappe.set_user(users['author']);frappe.db.savepoint('atomic_failure')
            old=frappe.db.count(api.ITEM);oldkey=frappe.db.count(api.KEY);oldop=frappe.db.count(api.OP)
            original=frappe.get_doc
            def injected(*args,**kwargs):
                if args and isinstance(args[0],dict) and args[0].get('doctype')==api.AUDIT:raise RuntimeError('synthetic failure at audit append')
                return original(*args,**kwargs)
            try:
                with patch.object(frappe,'get_doc',side_effect=injected):api.create_draft('atomic_failure_001',family(users['author'],'ROLLBACK'),1,content())
            except RuntimeError:frappe.db.rollback(save_point='atomic_failure')
            else:raise AssertionError('Failure injection did not execute')
            assert (frappe.db.count(api.ITEM),frappe.db.count(api.KEY),frappe.db.count(api.OP))==(old,oldkey,oldop)
            return {'real_database_rollback':True,'injected_boundary':'audit append'}
        check('atomic-item-key-receipt-audit-rollback',rollback_proof)
        frappe.db.commit();frappe.destroy();connect('placement-second.localhost')
        check('second-site-no-first-site-record',lambda:{'absent':not frappe.db.exists(api.ITEM,item['name'])} if not frappe.db.exists(api.ITEM,item['name']) else (_ for _ in ()).throw(AssertionError('Cross-site record')))
        frappe.destroy();connect('placement-test.localhost')
        base='http://127.0.0.1:18000'
        for _ in range(60):
            try:
                r=requests.get(base+'/api/method/ping',headers={'Host':'placement-test.localhost'},timeout=3)
                if r.status_code==200:break
            except requests.RequestException:pass
            time.sleep(1)
        else:raise AssertionError('HTTP backend not ready')
        def login(label):
            s=requests.Session();s.headers['Host']='placement-test.localhost'
            r=s.post(base+'/api/method/login',json={'usr':users[label],'pwd':os.environ['PLACEMENT_TEST_PASSWORD']},timeout=30)
            assert r.status_code==200,f'login {label}: HTTP {r.status_code}'
            sid=s.cookies.get('sid');assert sid and sid!='Guest'
            # Native server-side fixture observation only, not a browser-CSRF qualification claim.
            native_session=frappe.cache.hget('session',sid);token=native_session['data']['csrf_token'];assert token
            s.headers['X-Frappe-CSRF-Token']=token
            return s
        sessions={label:login(label) for label in ('author','other','publisher','auditor','outsider')}
        def post(label,method,payload):return sessions[label].post(base+'/api/method/toefl_house.api.'+method,json=payload,timeout=40)
        def http_denied(response,csrf=False):
            assert response.status_code in (400,403,404,405,409,417),f'Unexpected HTTP {response.status_code}'
            data=response.json()
            if not csrf:assert data.get('exc_type')!='CSRFTokenError','Not an authorization denial'
            return {'http_status':response.status_code,'exception':data.get('exc_type')}
        payload=dict(request_key='http_create_key_001',family=family(users['author'],'HTTP'),revision=1,content=content())
        def http_create():
            r=post('author','create_draft',payload);assert r.status_code==200,f'create HTTP {r.status_code}'
            return r.json()['message']
        httpitem=check('http-positive-create',http_create)
        check('http-guest-denied',lambda:http_denied(requests.post(base+'/api/method/toefl_house.api.create_draft',headers={'Host':'placement-test.localhost'},json=payload,timeout=30)))
        check('http-unrelated-role-denied',lambda:http_denied(post('outsider','create_draft',dict(payload,request_key='http_outsider_001'))))
        check('http-get-cannot-mutate',lambda:http_denied(sessions['author'].get(base+'/api/method/toefl_house.api.create_draft',params={'request_key':'get_not_allowed_001'},timeout=30)))
        def csrf_negative():
            s=sessions['author'];token=s.headers.pop('X-Frappe-CSRF-Token')
            try:return http_denied(s.post(base+'/api/method/toefl_house.api.create_draft',json=dict(payload,request_key='http_csrf_fail_001'),timeout=30),csrf=True)
            finally:s.headers['X-Frappe-CSRF-Token']=token
        check('http-csrf-negative-with-positive-control',csrf_negative)
        url=base+'/api/resource/'+quote(api.ITEM,safe='')+'/'+httpitem['name']
        check('http-direct-crud-mutation-denied',lambda:http_denied(sessions['author'].put(url,json={'status':'Published','flags':{'ignore_permissions':1}},timeout=30)))
        check('http-other-author-draft-read-denied',lambda:http_denied(sessions['other'].get(url,timeout=30)))
        keyname=frappe.db.get_value(api.ITEM,httpitem['name'],'key_revision')
        check('http-auditor-key-read-denied',lambda:http_denied(sessions['auditor'].get(base+'/api/resource/'+quote(api.KEY,safe='')+'/'+keyname,timeout=30)))
        def concurrent_create():
            p=dict(payload,request_key='http_concurrent_create_001',family=family(users['author'],'RACE'))
            def request(_):
                s=requests.Session();s.headers.update(sessions['author'].headers);s.cookies.update(sessions['author'].cookies)
                return s.post(base+'/api/method/toefl_house.api.create_draft',json=p,timeout=40)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rs=list(pool.map(request,range(2)))
            assert [r.status_code for r in rs]==[200,200],str([{'status':r.status_code,'exception':r.json().get('exc_type')} for r in rs])
            results=[r.json()['message'] for r in rs];assert results[0]==results[1]
            frappe.db.rollback();assert frappe.db.count(api.ITEM,{'family':p['family']})==1
            assert frappe.db.count(api.AUDIT,{'item_revision':results[0]['name']})==1
            return {'http_statuses':[200,200],'one_item_and_audit':True}
        check('http-concurrent-create-idempotency',concurrent_create)
        def concurrent_publish():
            def request(i):
                s=requests.Session();s.headers.update(sessions['publisher'].headers);s.cookies.update(sessions['publisher'].cookies)
                return s.post(base+'/api/method/toefl_house.api.publish',json={'request_key':f'http_race_publish_00{i}','item_name':httpitem['name'],'expected_version':1},timeout=40)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rs=list(pool.map(request,range(2)))
            statuses=sorted(r.status_code for r in rs);assert statuses==[200,417],str([{'status':r.status_code,'exception':r.json().get('exc_type')} for r in rs])
            frappe.db.rollback();assert frappe.db.count(api.AUDIT,{'item_revision':httpitem['name'],'action':'publish'})==1
            return {'http_statuses':statuses,'one_publication':True}
        check('http-concurrent-publication-cas',concurrent_publish)
        def revoke():
            frappe.set_user('Administrator');u=frappe.get_doc('User',users['other']);u.roles=[];u.save();frappe.db.commit();frappe.clear_cache(user=u.name)
            return http_denied(post('other','create_draft',dict(payload,request_key='revoked_actor_001',family=family(users['other'],'REVOKED'))))
        check('http-role-revocation-old-session-denied',revoke)
        def no_side_effects():
            after={dt:frappe.db.count(dt) for dt in before_counts};assert before_counts==after
            return {'native_domain_counts_unchanged':after}
        check('no-student-enrollment-academic-finance-payroll-writes',no_side_effects)
        report['status']='pass'
    except Exception as exc:
        report['status']='fail';report['failure']={'type':type(exc).__name__,'message':str(exc)[:600]}
        print('Native qualification failed:',type(exc).__name__,str(exc)[:600],flush=True)
        print(traceback.format_exc(),flush=True)
    finally:
        output.write_text(json.dumps(report,indent=2,default=str)+'\n')
        frappe.destroy()
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
