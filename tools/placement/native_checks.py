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
    report={'scope':'Synthetic content-governance and blueprint/policy configuration increment (1-2); not full T01-T20','status':'running','checks':[],
            'commit':os.environ['GITHUB_SHA'],'runtime_kind':'Frappe/MariaDB/Redis/HTTP','production':'REJECT'}
    users={'author':'synthetic-author@example.test','other':'synthetic-other@example.test',
           'publisher':'synthetic-publisher@example.test','publisher2':'synthetic-publisher2@example.test',
           'second_author':'synthetic-second-author@example.test','auditor':'synthetic-auditor@example.test','outsider':'synthetic-outsider@example.test'}
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
    # Synthetic configuration fixtures. Structural values are fixture data, not
    # approved operational policy (P1-P5 remain owner deliverables).
    bp_code='SYN-BP-MAIN-1'
    pol_code='SYN-POL-MAIN-1'
    good_bp=dict(mode='Digital',
                 sections=[dict(id='listening',skill='Listening',minutes=30,item_count=10),
                           dict(id='reading',skill='Reading',minutes=40,item_count=12)],
                 total_minutes=70)
    revised_bp=dict(mode='Digital',
                    sections=[dict(id='listening',skill='Listening',minutes=20,item_count=8),
                              dict(id='reading',skill='Reading',minutes=50,item_count=14)],
                    total_minutes=70)
    conflict_bp=dict(good_bp,total_minutes=71)
    bad_mode_bp=dict(good_bp,mode='Remote')
    good_pol=dict(result_validity_days=90,retest_wait_days=14,
                  release_working_days=2,appeal_working_days=5,retention_years=3)
    bad_pol=dict(good_pol,retention_years=11)
    try:
        for site in ('placement-test.localhost','placement-second.localhost'):
            connect(site)
            assert frappe.conf.allow_tests==1 and frappe.conf.toefl_house_synthetic_only==1
            def setup():
                mapping={'author':['Placement Author','Placement Publisher'],'other':['Placement Author'],
                         'publisher':['Placement Publisher'],'publisher2':['Placement Publisher'],
                         'second_author':['Placement Author'],'auditor':['Placement Auditor'],'outsider':[]}
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
        # --- Increment 2: blueprint/policy configuration governance ---
        check('config-conflicting-quotas-create-denied',lambda:denied(lambda:as_user('author',lambda:api.create_draft_config('cfg_conflict_001','blueprint',bp_code,1,conflict_bp))))
        check('config-invalid-mode-create-denied',lambda:denied(lambda:as_user('author',lambda:api.create_draft_config('cfg_badmode_0001','blueprint',bp_code,1,bad_mode_bp))))
        check('config-out-of-bounds-policy-create-denied',lambda:denied(lambda:as_user('author',lambda:api.create_draft_config('cfg_bad_policy_01','policy',pol_code,1,bad_pol))))
        check('config-unknown-type-denied',lambda:denied(lambda:as_user('author',lambda:api.create_draft_config('cfg_unknown_type_1','bank',bp_code,1,good_bp))))
        check('config-non-synthetic-code-denied',lambda:denied(lambda:as_user('author',lambda:api.create_draft_config('cfg_realcode_001','blueprint','REAL-BP',1,good_bp))))
        bp=check('config-create-blueprint-draft',lambda:as_user('author',lambda:api.create_draft_config('cfg_create_bp_001','blueprint',bp_code,1,good_bp)))
        assert bp['status']=='Draft' and bp['version']==1
        check('config-duplicate-code-revision-unique',lambda:denied(lambda:as_user('second_author',lambda:api.create_draft_config('cfg_dup_code_001','blueprint',bp_code,1,good_bp))))
        def cfg_replay():
            count=frappe.db.count(api.AUDIT)
            value=as_user('author',lambda:api.create_draft_config('cfg_create_bp_001','blueprint',bp_code,1,good_bp))
            assert value==bp and frappe.db.count(api.AUDIT)==count
            return {'same_result':True,'no_duplicate_audit':True}
        check('config-idempotent-replay',cfg_replay)
        check('config-changed-payload-conflict',lambda:denied(lambda:as_user('author',lambda:api.create_draft_config('cfg_create_bp_001','blueprint',bp_code,1,conflict_bp))))
        check('config-changed-actor-conflict',lambda:denied(lambda:as_user('second_author',lambda:api.create_draft_config('cfg_create_bp_001','blueprint',bp_code,1,good_bp))))
        pol=check('config-create-policy-draft',lambda:as_user('author',lambda:api.create_draft_config('cfg_create_pol_001','policy',pol_code,1,good_pol)))
        bp=check('config-revise-draft',lambda:as_user('author',lambda:api.revise_draft_config('cfg_revise_bp_001','blueprint',bp['name'],1,revised_bp)))
        assert bp['version']==2 and bp['status']=='Draft'
        check('config-other-author-revise-denied',lambda:denied(lambda:as_user('second_author',lambda:api.revise_draft_config('cfg_other_revise_001','blueprint',bp['name'],2,good_bp))))
        check('config-stale-version-revise-denied',lambda:denied(lambda:as_user('author',lambda:api.revise_draft_config('cfg_stale_revise_001','blueprint',bp['name'],1,good_bp))))
        check('config-self-review-denied-despite-role-union',lambda:denied(lambda:as_user('author',lambda:api.review_config('cfg_self_review_001','blueprint',bp['name'],2))))
        bp=check('config-independent-review',lambda:as_user('publisher',lambda:api.review_config('cfg_review_bp_001','blueprint',bp['name'],2)))
        assert bp['status']=='Reviewed'
        check('config-review-freezes-content',lambda:denied(lambda:as_user('author',lambda:api.revise_draft_config('cfg_frozen_revise_001','blueprint',bp['name'],3,revised_bp))))
        check('config-reviewer-self-publish-denied',lambda:denied(lambda:as_user('publisher',lambda:api.publish_config('cfg_self_publish_001','blueprint',bp['name'],3))))
        check('config-author-publish-denied',lambda:denied(lambda:as_user('author',lambda:api.publish_config('cfg_author_publish_001','blueprint',bp['name'],3))))
        bp=check('config-independent-publication',lambda:as_user('publisher2',lambda:api.publish_config('cfg_publish_bp_001','blueprint',bp['name'],3)))
        assert bp['status']=='Published'
        check('config-published-revise-denied',lambda:denied(lambda:as_user('author',lambda:api.revise_draft_config('cfg_pub_revise_001','blueprint',bp['name'],4,good_bp))))
        check('config-retire-by-author-denied',lambda:denied(lambda:as_user('author',lambda:api.retire_config('cfg_author_retire_001','blueprint',bp['name'],4))))
        bp=check('config-independent-retirement',lambda:as_user('publisher2',lambda:api.retire_config('cfg_retire_bp_001','blueprint',bp['name'],4)))
        assert bp['status']=='Retired'
        check('config-retired-is-terminal',lambda:denied(lambda:as_user('publisher',lambda:api.retire_config('cfg_retired_again_001','blueprint',bp['name'],5))))
        pol=check('config-policy-review',lambda:as_user('publisher',lambda:api.review_config('cfg_review_pol_001','policy',pol['name'],1)))
        pol=check('config-policy-independent-publication',lambda:as_user('publisher2',lambda:api.publish_config('cfg_publish_pol_001','policy',pol['name'],2)))
        assert pol['status']=='Published'
        def cfg_generic_write():
            frappe.set_user(users['publisher2']);doc=frappe.get_doc(api.BLUEPRINT,bp['name']);doc.status='Draft';doc.flags.ignore_permissions=True
            return denied(lambda:doc.save(ignore_permissions=True))
        check('config-ignore-permissions-does-not-bypass-controller',cfg_generic_write)
        check('config-direct-db-set-denied',lambda:denied(lambda:frappe.get_doc(api.POLICY,pol['name']).db_set('status','Retired')))
        check('config-direct-db-update-denied',lambda:denied(lambda:frappe.get_doc(api.BLUEPRINT,bp['name']).db_update()))
        check('config-delete-denied',lambda:denied(lambda:frappe.delete_doc(api.BLUEPRINT,bp['name'],ignore_permissions=True)))
        def cfg_audit_shape():
            frappe.set_user(users['auditor'])
            rows=frappe.get_all(api.AUDIT,filters={'target':bp['name']},fields=['action','item_revision','before_key','after_key'])
            assert len(rows)==5,rows
            assert all(not r.item_revision and not r.before_key and not r.after_key for r in rows)
            actions=sorted(r.action for r in rows)
            assert actions==sorted(['create_blueprint','revise_blueprint','review_blueprint','publish_blueprint','retire_blueprint']),actions
            return {'config_audit_rows':len(rows),'actions':actions,'no_item_key_references':True}
        check('config-audit-ledger-shape',cfg_audit_shape)
        def cfg_native_reads():
            frappe.set_user(users['second_author'])
            assert not frappe.get_doc(api.BLUEPRINT,bp['name']).has_permission('read')
            assert frappe.get_doc(api.POLICY,pol['name']).has_permission('read')
            frappe.set_user(users['author'])
            assert frappe.get_doc(api.BLUEPRINT,bp['name']).has_permission('read')
            frappe.set_user(users['publisher2'])
            assert frappe.get_doc(api.BLUEPRINT,bp['name']).has_permission('read')
            assert frappe.get_doc(api.POLICY,pol['name']).has_permission('read')
            frappe.set_user(users['auditor'])
            assert frappe.get_doc(api.POLICY,pol['name']).has_permission('read')
            assert not frappe.get_doc(api.BLUEPRINT,bp['name']).has_permission('read')
            frappe.set_user(users['second_author'])
            assert not frappe.get_list(api.BLUEPRINT,filters={'code':bp_code})
            frappe.set_user(users['auditor'])
            assert not frappe.get_list(api.BLUEPRINT,filters={'code':bp_code})
            assert len(frappe.get_list(api.POLICY,filters={'code':pol_code}))==1
            return {'own_and_published_visible':True,'retired_hidden_from_auditor':True,'list_parity':True}
        check('config-role-and-list-parity',cfg_native_reads)
        def cfg_rollback_proof():
            frappe.set_user(users['author']);frappe.db.savepoint('cfg_atomic')
            old=frappe.db.count(api.BLUEPRINT);oldop=frappe.db.count(api.OP)
            original=frappe.get_doc
            def injected(*args,**kwargs):
                if args and isinstance(args[0],dict) and args[0].get('doctype')==api.AUDIT:raise RuntimeError('synthetic configuration audit failure')
                return original(*args,**kwargs)
            try:
                with patch.object(frappe,'get_doc',side_effect=injected):api.create_draft_config('cfg_atomic_bp_0001','blueprint','SYN-BP-ROLLBACK-1',1,good_bp)
            except RuntimeError:frappe.db.rollback(save_point='cfg_atomic')
            else:raise AssertionError('Failure injection did not execute')
            assert (frappe.db.count(api.BLUEPRINT),frappe.db.count(api.OP))==(old,oldop)
            return {'real_database_rollback':True,'injected_boundary':'audit append'}
        check('config-atomic-doc-receipt-audit-rollback',cfg_rollback_proof)
        frappe.db.commit();frappe.destroy();connect('placement-second.localhost')
        check('second-site-no-first-site-record',lambda:{'absent':not frappe.db.exists(api.ITEM,item['name'])} if not frappe.db.exists(api.ITEM,item['name']) else (_ for _ in ()).throw(AssertionError('Cross-site record')))
        def cfg_second_site():
            assert not frappe.db.exists(api.BLUEPRINT,bp['name']) and not frappe.db.exists(api.POLICY,pol['name'])
            return {'config_absent_on_second_site':True}
        check('second-site-no-first-site-config-record',cfg_second_site)

        def transient_recovery(exhaust=False):
            frappe.set_user(users['author']);frappe.db.commit()
            suffix='EXHAUST' if exhaust else 'RETRY'
            f=family(users['author'],suffix);calls=[];original=api._new_key
            previous=frappe.db.sql('SELECT @@SESSION.innodb_lock_wait_timeout')[0][0]
            def flaky(*args):
                calls.append(1)
                assert frappe.db.sql('SELECT @@SESSION.innodb_lock_wait_timeout')[0][0]==5
                if exhaust or len(calls)==1:raise frappe.QueryDeadlockError('Synthetic transient after item insert')
                return original(*args)
            with patch.object(api,'_new_key',side_effect=flaky):
                if exhaust:
                    try:api.create_draft('native_exhaust_retry_001',f,1,content())
                    except frappe.QueryDeadlockError:pass
                    else:raise AssertionError('Retry exhaustion must fail closed')
                else:result=api.create_draft('native_transient_retry_001',f,1,content())
            assert len(calls)==(4 if exhaust else 2)
            assert frappe.db.count(api.ITEM,{'family':f})==(0 if exhaust else 1)
            if not exhaust:assert frappe.db.count(api.AUDIT,{'item_revision':result['name']})==1
            assert frappe.db.sql('SELECT @@SESSION.innodb_lock_wait_timeout')[0][0]==previous
            return {'attempts':len(calls),'rollback_and_wait_restore':True,'exhaustion':exhaust}
        check('native-whole-command-transient-recovery',transient_recovery)
        check('native-retry-exhaustion-bounded',lambda:transient_recovery(True))
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
        sessions={label:login(label) for label in ('author','other','publisher','publisher2','second_author','auditor','outsider')}
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
        # --- Increment 2 over HTTP: routes, CSRF, CRUD containment, races, revocation ---
        http_bp_def=dict(good_bp)
        http_pol_def=dict(good_pol)
        cfg_payload=dict(request_key='http_cfg_create_001',config='blueprint',code='SYN-BP-HTTP-1',revision=1,definition=http_bp_def)
        def http_cfg_create():
            r=post('author','create_draft_config',cfg_payload);assert r.status_code==200,f'config create HTTP {r.status_code}'
            return r.json()['message']
        httpbp=check('http-config-positive-create',http_cfg_create)
        check('http-config-guest-denied',lambda:http_denied(requests.post(base+'/api/method/toefl_house.api.create_draft_config',headers={'Host':'placement-test.localhost'},json=cfg_payload,timeout=30)))
        check('http-config-unrelated-role-denied',lambda:http_denied(post('outsider','create_draft_config',dict(cfg_payload,request_key='http_cfg_outsider_001'))))
        check('http-config-get-cannot-mutate',lambda:http_denied(sessions['author'].get(base+'/api/method/toefl_house.api.create_draft_config',params={'request_key':'http_cfg_get_0001'},timeout=30)))
        def cfg_csrf_negative():
            s=sessions['author'];token=s.headers.pop('X-Frappe-CSRF-Token')
            try:return http_denied(s.post(base+'/api/method/toefl_house.api.create_draft_config',json=dict(cfg_payload,request_key='http_cfg_csrf_0001'),timeout=30),csrf=True)
            finally:s.headers['X-Frappe-CSRF-Token']=token
        check('http-config-csrf-negative-with-positive-control',cfg_csrf_negative)
        cfg_url=base+'/api/resource/'+quote(api.BLUEPRINT,safe='')+'/'+httpbp['name']
        check('http-config-direct-crud-mutation-denied',lambda:http_denied(sessions['author'].put(cfg_url,json={'status':'Published','flags':{'ignore_permissions':1}},timeout=30)))
        check('http-config-other-author-read-denied',lambda:http_denied(sessions['second_author'].get(cfg_url,timeout=30)))
        def concurrent_cfg_create():
            p=dict(cfg_payload,request_key='http_cfg_concurrent_001',code='SYN-BP-RACE-1')
            def request(_):
                s=requests.Session();s.headers.update(sessions['author'].headers);s.cookies.update(sessions['author'].cookies)
                return s.post(base+'/api/method/toefl_house.api.create_draft_config',json=p,timeout=40)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rs=list(pool.map(request,range(2)))
            assert [r.status_code for r in rs]==[200,200],str([{'status':r.status_code,'exception':r.json().get('exc_type')} for r in rs])
            results=[r.json()['message'] for r in rs];assert results[0]==results[1]
            frappe.db.rollback();assert frappe.db.count(api.BLUEPRINT,{'code':p['code']})==1
            assert frappe.db.count(api.AUDIT,{'target':results[0]['name']})==1
            return {'http_statuses':[200,200],'one_doc_and_audit':True}
        check('http-config-concurrent-create-idempotency',concurrent_cfg_create)
        def concurrent_cfg_publish():
            race_def=dict(good_bp)
            doc=as_user('author',lambda:api.create_draft_config('cfg_race_create_001','blueprint','SYN-BP-RACE2-1',1,race_def))
            as_user('publisher',lambda:api.review_config('cfg_race_review_001','blueprint',doc['name'],1))
            frappe.db.commit()
            def request(i):
                s=requests.Session();s.headers.update(sessions['publisher2'].headers);s.cookies.update(sessions['publisher2'].cookies)
                return s.post(base+'/api/method/toefl_house.api.publish_config',json={'request_key':f'http_cfg_race_pub_00{i}','config':'blueprint','name':doc['name'],'expected_version':2},timeout=40)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rs=list(pool.map(request,range(2)))
            statuses=sorted(r.status_code for r in rs);assert statuses==[200,417],str([{'status':r.status_code,'exception':r.json().get('exc_type')} for r in rs])
            frappe.db.rollback();assert frappe.db.count(api.AUDIT,{'target':doc['name'],'action':'publish_blueprint'})==1
            return {'http_statuses':statuses,'one_publication':True}
        check('http-config-concurrent-publication-cas',concurrent_cfg_publish)
        def http_cfg_policy_flow():
            r=post('author','create_draft_config',dict(request_key='http_cfg_pol_0001',config='policy',code='SYN-POL-HTTP-1',revision=1,definition=http_pol_def))
            assert r.status_code==200,f'policy create HTTP {r.status_code}'
            name=r.json()['message']['name']
            r=post('publisher','review_config',dict(request_key='http_cfg_pol_review_001',config='policy',name=name,expected_version=1))
            assert r.status_code==200,f'policy review HTTP {r.status_code}'
            r=post('publisher2','publish_config',dict(request_key='http_cfg_pol_publish_001',config='policy',name=name,expected_version=2))
            assert r.status_code==200,f'policy publish HTTP {r.status_code}'
            return name
        polhttp=check('http-config-policy-draft-review-publish-flow',http_cfg_policy_flow)
        def revoke():
            frappe.set_user('Administrator');u=frappe.get_doc('User',users['other']);u.roles=[];u.save();frappe.db.commit();frappe.clear_cache(user=u.name)
            return http_denied(post('other','create_draft',dict(payload,request_key='revoked_actor_001',family=family(users['other'],'REVOKED'))))
        check('http-role-revocation-old-session-denied',revoke)
        def cfg_revoke():
            frappe.set_user('Administrator');u=frappe.get_doc('User',users['publisher2']);u.roles=[];u.save();frappe.db.commit();frappe.clear_cache(user=u.name)
            return http_denied(post('publisher2','retire_config',dict(request_key='cfg_revoked_retire_001',config='policy',name=polhttp,expected_version=3)))
        check('http-config-revoked-publisher-old-session-denied',cfg_revoke)
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
