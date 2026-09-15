"""Real native DB/controller/HTTP acceptance on isolated synthetic sites only."""
import concurrent.futures
import copy
from datetime import timedelta
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
    report={'scope':'Synthetic content-governance, blueprint/policy configuration, allocation and staff-supervised digital delivery increments (1-4); not full T01-T20','status':'running','checks':[],
            'commit':os.environ['GITHUB_SHA'],'runtime_kind':'Frappe/MariaDB/Redis/HTTP','production':'REJECT'}
    users={'author':'synthetic-author@example.test','other':'synthetic-other@example.test',
           'publisher':'synthetic-publisher@example.test','publisher2':'synthetic-publisher2@example.test',
           'second_author':'synthetic-second-author@example.test','auditor':'synthetic-auditor@example.test','outsider':'synthetic-outsider@example.test',
           'invigilator':'synthetic-invigilator@example.test',
           'candidate':'synthetic-candidate@example.test','candidate2':'synthetic-candidate2@example.test',
           'candidate3':'synthetic-candidate3@example.test','candidate4':'synthetic-candidate4@example.test'}
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
                # `author` is dual-role (Author+Publisher) for increment-1/2 SoD
                # (self-publish/self-review denied despite role union). It is a
                # Publisher for increment-3 operational commands. Author-only
                # denials must use `other` / `second_author`, never `author`.
                mapping={'author':['Placement Author','Placement Publisher'],'other':['Placement Author'],
                         'publisher':['Placement Publisher'],'publisher2':['Placement Publisher'],
                         'second_author':['Placement Author'],'auditor':['Placement Auditor'],'outsider':[],
                         'invigilator':['Placement Invigilator'],
                         'candidate':[],'candidate2':[],'candidate3':[],'candidate4':[]}
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
        # --- Increment 3: blueprint allocation and candidate form generation ---
        # Isolation + increment-1/2 transient recovery ran on the second site.
        # Allocation must execute on the primary site (users already exist on
        # both); otherwise increment-3 records land on the wrong site and
        # names captured from increment 2 are missing (run 34883984456).
        frappe.db.commit();frappe.destroy();connect('placement-test.localhost')
        from toefl_house import allocation
        from toefl_house.policy import canonical as _canonical
        from toefl_house.security import command as _command
        def unavailable(fn,needle):
            frappe.db.savepoint('denial')
            try:fn()
            except frappe.ValidationError as exc:
                assert needle in str(exc),str(exc)
                return {'denied':'ValidationError','reason':str(exc)[:140]}
            else:raise AssertionError('Expected allocation unavailability was accepted')
            finally:frappe.db.rollback(save_point='denial')
        def bank_content(skill,difficulty,i,qtype):
            if qtype=='True False':
                options=[{'id':'true','text':'True'},{'id':'false','text':'False'}];answer='true'
            else:
                options=[{'id':'o%d'%j,'text':'SYN %s %s %d option %d'%(skill,difficulty,i,j)} for j in range(1,5)]
                answer='o1'
            return dict(skill=skill,difficulty=difficulty,question_type=qtype,
                        prompt='SYNTHETIC: bank %s %s %d fixture question.'%(skill,difficulty,i),
                        options=options,answer=answer)
        def build_bank():
            made=[]
            for skill in ('Vocabulary','Grammar','Reading','Listening'):
                for difficulty in ('Entry','Core','Stretch'):
                    for i in range(3):
                        qtype='True False' if i==2 else 'Single Choice'
                        fam=family(users['author'],'BANK-%s-%s%d'%(skill[:3].upper(),difficulty[0].upper(),i))
                        def make(f=fam,c=bank_content(skill,difficulty,i,qtype),k='bank-create-%s-%s-%d'%(skill,difficulty,i)):
                            as_user('author',lambda:api.create_draft(k,f,1,c))
                        make()
                        made.append(fam)
            frappe.db.commit()
            rows=frappe.get_all(api.ITEM,filters={'status':'Draft','owner':users['author']},
                                fields=['name','version'],order_by='creation asc')
            for idx,row in enumerate(rows):
                def pub(r=row,k='bank-publish-%03d'%idx):
                    as_user('publisher',lambda:api.publish(k,r.name,r.version))
                pub()
            return {'bank_families':len(set(made)),'published_total':frappe.db.count(api.ITEM,{'status':'Published'})}
        check('alloc-bank-fixture-published',build_bank)
        alloc_sections=[dict(id='listening_a',skill='Listening',item_count=2,minutes=10),
                        dict(id='reading_a',skill='Reading',item_count=3,minutes=15),
                        dict(id='vocab_a',skill='Vocabulary',item_count=2,minutes=10),
                        dict(id='grammar_a',skill='Grammar',item_count=2,minutes=10)]
        alloc_bp=dict(mode='Digital',sections=alloc_sections,total_minutes=45)
        alloc_bp2=dict(mode='Digital',
                       sections=[dict(id='vocab_b',skill='Vocabulary',item_count=1,minutes=10),
                                 dict(id='grammar_b',skill='Grammar',item_count=1,minutes=10)],
                       total_minutes=20)
        over_bp=dict(mode='Digital',sections=[dict(id='listening_x',skill='Listening',item_count=12,minutes=60)],total_minutes=60)
        spk_bp=dict(mode='Digital',sections=[dict(id='speaking_x',skill='Speaking',item_count=2,minutes=10)],total_minutes=10)
        def publish_config_flow(code,definition,config='blueprint'):
            tag=code[4:].lower()
            doc=as_user('author',lambda:api.create_draft_config('alloc_cfg_%s_create_1'%tag,config,code,1,definition))
            doc=as_user('publisher',lambda:api.review_config('alloc_cfg_%s_review_1'%tag,config,doc['name'],1))
            doc=as_user('publisher2',lambda:api.publish_config('alloc_cfg_%s_publish_1'%tag,config,doc['name'],2))
            assert doc['status']=='Published' and doc['version']==3
            return doc
        def config_fixtures():
            draft_bp=as_user('author',lambda:api.create_draft_config('alloc_cfg_draftbp_001','blueprint','SYN-BP-DRAFT-1',1,alloc_bp))
            draft_pol=as_user('author',lambda:api.create_draft_config('alloc_cfg_draftpol_001','policy','SYN-POL-DRAFT-1',1,good_pol))
            assert draft_bp['status']=='Draft' and draft_pol['status']=='Draft'
            over=publish_config_flow('SYN-BP-OVER-1',over_bp)
            spk=publish_config_flow('SYN-BP-SPK-1',spk_bp)
            main=publish_config_flow('SYN-BP-ALLOC-1',alloc_bp)
            small=publish_config_flow('SYN-BP-ALLOC-2',alloc_bp2)
            main_pol=publish_config_flow('SYN-POL-ALLOC-1',good_pol,'policy')
            return {'draft_bp':draft_bp['name'],'draft_pol':draft_pol['name'],
                    'over_bp':over['name'],'spk_bp':spk['name'],
                    'main_bp':main['name'],'small_bp':small['name'],'main_version':3,
                    'main_pol':main_pol['name'],'main_pol_version':3}
        cfgx=check('alloc-config-fixtures-published',config_fixtures)
        pol_name=cfgx['main_pol']
        main_skills={s['skill'] for s in alloc_sections}
        main_sections=[dict(id=s['id'],skill=s['skill'],item_count=s['item_count']) for s in alloc_sections]
        def solver_pool(excluded_families,skills):
            rows=frappe.get_all(api.ITEM,filters={'status':'Published'},
                                fields=['name','family','skill','difficulty','question_type','options_json'])
            return [dict(name=r.name,family=r.family,skill=r.skill,difficulty=r.difficulty,
                         question_type=r.question_type,options=[o['id'] for o in json.loads(r.options_json)])
                    for r in rows if r.skill in skills and r.family not in excluded_families]
        case=check('alloc-create-case',lambda:as_user('publisher',lambda:api.create_case('alloc_case_key_0001',users['candidate'])))
        assert case['status']=='Open' and case['subject']==users['candidate']
        check('alloc-case-duplicate-subject-denied',lambda:denied(lambda:as_user('publisher',lambda:api.create_case('alloc_case_dup_key_0001',users['candidate']))))
        check('alloc-case-missing-subject-denied',lambda:denied(lambda:as_user('publisher',lambda:api.create_case('alloc_case_missing_001','nobody@example.test'))))
        check('alloc-case-privileged-subject-denied',lambda:denied(lambda:as_user('publisher',lambda:api.create_case('alloc_case_admin_key_01','Administrator'))))
        check('alloc-case-author-denied',lambda:denied(lambda:as_user('second_author',lambda:api.create_case('alloc_case_author_key_1',users['candidate2']))))
        check('alloc-case-outsider-denied',lambda:denied(lambda:as_user('outsider',lambda:api.create_case('alloc_case_outsider_key_1',users['candidate2']))))
        check('alloc-fail-missing-case',lambda:denied(lambda:as_user('publisher',lambda:api.allocate_attempt('alloc_fail_case_0001','nonexistent-case-0001',cfgx['main_bp'],3,pol_name,3))))
        check('alloc-fail-draft-blueprint',lambda:unavailable(lambda:as_user('publisher',lambda:api.allocate_attempt('alloc_fail_draftbp_01',case['name'],cfgx['draft_bp'],1,pol_name,3)),'Only published blueprint'))
        check('alloc-fail-stale-blueprint-version',lambda:unavailable(lambda:as_user('publisher',lambda:api.allocate_attempt('alloc_fail_stalever_01',case['name'],cfgx['main_bp'],1,pol_name,3)),'Stale configuration revision'))
        check('alloc-fail-draft-policy',lambda:unavailable(lambda:as_user('publisher',lambda:api.allocate_attempt('alloc_fail_draftpol_01',case['name'],cfgx['main_bp'],3,cfgx['draft_pol'],1)),'Only published policy'))
        check('alloc-fail-infeasible-quota',lambda:unavailable(lambda:as_user('publisher',lambda:api.allocate_attempt('alloc_fail_over_0001',case['name'],cfgx['over_bp'],3,pol_name,3)),'insufficient eligible families for skill Listening'))
        check('alloc-fail-missing-skill-section',lambda:unavailable(lambda:as_user('publisher',lambda:api.allocate_attempt('alloc_fail_spk_00001',case['name'],cfgx['spk_bp'],3,pol_name,3)),'insufficient eligible families for skill Speaking'))
        alloc=check('alloc-happy-path',lambda:as_user('publisher',lambda:api.allocate_attempt('alloc_attempt_key_001',case['name'],cfgx['main_bp'],3,pol_name,3)))
        assert alloc['status']=='Allocated' and alloc['ordinal']==1 and alloc['item_count']==9
        def manifest_integrity():
            m=frappe.get_doc(api.MANIFEST,alloc['manifest'])
            assert frappe.db.count(api.MANIFEST,{'attempt':alloc['attempt']})==1
            assert m.status=='Committed' and m.algorithm_version==allocation.ALGORITHM_VERSION
            assert len(m.seed)==64 and set(m.seed)<=set('0123456789abcdef')
            form=json.loads(m.form_json)
            assert m.form_hash==digest(form)
            assert form['algorithm']==allocation.ALGORITHM_VERSION and form['seed']==m.seed
            assert form['attempt']==alloc['attempt'] and form['case']==case['name'] and form['subject']==users['candidate']
            assert form['pool_digest']==m.pool_digest
            assert [(s['id'],s['skill'],s['minutes'],s['item_count']) for s in form['sections']]==[(s['id'],s['skill'],s['minutes'],s['item_count']) for s in alloc_sections]
            a=frappe.get_doc(api.ATTEMPT,alloc['attempt'])
            assert a.ordinal==1 and a.status=='Allocated' and a.mode=='Digital' and a.subject==users['candidate']
            assert a.blueprint==cfgx['main_bp'] and a.blueprint_version==3
            assert a.policy==pol_name and a.policy_version==3
            assert a.blueprint_hash==frappe.db.get_value(api.BLUEPRINT,cfgx['main_bp'],'content_hash')
            assert a.policy_hash==frappe.db.get_value(api.POLICY,pol_name,'content_hash')
            items=form['items']
            assert [e['order'] for e in items]==list(range(1,10))
            by_section={}
            for e in items:
                by_section.setdefault(e['section'],[]).append(e)
                row=frappe.db.get_value(api.ITEM,e['item'],['status','skill','difficulty','question_type','options_json','family'],as_dict=True)
                assert row.status=='Published' and row.family==e['family']
                assert row.skill==e['skill'] and row.skill==next(s['skill'] for s in alloc_sections if s['id']==e['section'])
                assert row.difficulty==e['difficulty'] and row.question_type==e['question_type']
                if row.question_type=='Single Choice':
                    assert sorted(e['option_order'])==sorted(o['id'] for o in json.loads(row.options_json))
                else:
                    assert e['option_order'] is None
            for s in alloc_sections:
                picked=by_section[s['id']]
                assert len(picked)==s['item_count'],s
                assert len({e['family'] for e in picked})==len(picked)
                assert len({e['difficulty'] for e in picked})==len(picked)
            assert len({e['family'] for e in items})==9
            pool=solver_pool(set(),main_skills)
            assert m.pool_digest==allocation.pool_digest(pool)
            plan=allocation.allocate(main_sections,pool,m.seed,{})
            assert [(e['order'],e['item']) for e in plan['items']]==[(e['order'],e['item']) for e in items]
            assert [e['option_order'] for e in plan['items']]==[e['option_order'] for e in items]
            return {'one_manifest_per_attempt':True,'hash_bound':True,'quotas_exact':True,'strata_balanced':True,'rerun_identical':True}
        check('alloc-manifest-integrity-and-determinism',manifest_integrity)
        def audit_and_ledger():
            rows=frappe.get_all(api.AUDIT,filters={'target':alloc['attempt']},fields=['action','item_revision','after_hash'])
            assert len(rows)==1 and rows[0].action=='allocate_attempt' and not rows[0].item_revision
            assert rows[0].after_hash==alloc['form_hash']
            op=frappe.get_doc(api.OP,digest(['allocate_attempt','alloc_attempt_key_001']))
            assert op.status=='Complete' and op.actor==users['publisher']
            assert json.loads(op.result_json)['manifest']==alloc['manifest']
            exp=frappe.get_all(api.EXPOSURE,filters={'attempt':alloc['attempt']},fields=['family','event','subject'])
            assert len(exp)==9 and all(e.event=='Reserved' and e.subject==users['candidate'] for e in exp)
            form=json.loads(frappe.get_doc(api.MANIFEST,alloc['manifest']).form_json)
            assert {e.family for e in exp}=={i['family'] for i in form['items']}
            assert len(frappe.get_all(api.AUDIT,filters={'target':case['name'],'action':'create_case'}))==1
            return {'allocation_audit':1,'exposure_rows':9,'receipt_complete':True}
        check('alloc-audit-and-exposure-ledger',audit_and_ledger)
        def alloc_replay():
            count=frappe.db.count(api.AUDIT)
            value=as_user('publisher',lambda:api.allocate_attempt('alloc_attempt_key_001',case['name'],cfgx['main_bp'],3,pol_name,3))
            assert value==alloc and frappe.db.count(api.AUDIT)==count
            assert frappe.db.count(api.ATTEMPT)==1
            return {'same_result':True,'no_new_attempt':True}
        check('alloc-idempotent-replay',alloc_replay)
        check('alloc-changed-payload-conflict',lambda:denied(lambda:as_user('publisher',lambda:api.allocate_attempt('alloc_attempt_key_001',case['name'],cfgx['main_bp'],2,pol_name,3))))
        check('alloc-changed-actor-conflict',lambda:denied(lambda:as_user('publisher2',lambda:api.allocate_attempt('alloc_attempt_key_001',case['name'],cfgx['main_bp'],3,pol_name,3))))
        alloc2=check('alloc-second-attempt-ordinal',lambda:as_user('publisher',lambda:api.allocate_attempt('alloc_attempt_key_002',case['name'],cfgx['main_bp'],3,pol_name,3)))
        assert alloc2['ordinal']==2 and alloc2['attempt']!=alloc['attempt']
        def reuse_controlled():
            f1=json.loads(frappe.get_doc(api.MANIFEST,alloc['manifest']).form_json)['items']
            f2=json.loads(frappe.get_doc(api.MANIFEST,alloc2['manifest']).form_json)['items']
            fam1={e['family'] for e in f1};fam2={e['family'] for e in f2}
            assert not (fam1&fam2)
            assert len(fam2)==9
            counts={r.family:max(0,r.c-(1 if r.family in fam2 else 0)) for r in frappe.db.sql('select family, count(*) as c from `tabTH Placement Exposure` group by family',as_dict=True)}
            pool2=solver_pool(fam1,main_skills)
            m2=frappe.get_doc(api.MANIFEST,alloc2['manifest'])
            plan=allocation.allocate(main_sections,pool2,m2.seed,counts)
            assert [(e['order'],e['item']) for e in plan['items']]==[(e['order'],e['item']) for e in f2]
            return {'no_family_reuse_for_subject':True,'second_rerun_identical':True}
        check('alloc-exposure-reuse-controlled',reuse_controlled)
        case2=check('alloc-create-case-second-subject',lambda:as_user('publisher',lambda:api.create_case('alloc_case_key_0002',users['candidate2'])))
        alloc3=check('alloc-other-subject-independent-pool',lambda:as_user('publisher',lambda:api.allocate_attempt('alloc_attempt_key_010',case2['name'],cfgx['main_bp'],3,pol_name,3)))
        assert alloc3['ordinal']==1
        assert len(frappe.get_all(api.EXPOSURE,filters={'subject':users['candidate2']}))==9
        alloc4=check('alloc-third-attempt',lambda:as_user('publisher',lambda:api.allocate_attempt('alloc_attempt_key_003',case['name'],cfgx['main_bp'],3,pol_name,3)))
        assert alloc4['ordinal']==3
        def fourth_unavailable():
            before={dt:frappe.db.count(dt) for dt in (api.ATTEMPT,api.MANIFEST,api.EXPOSURE,api.OP,api.AUDIT)}
            obs=unavailable(lambda:as_user('publisher',lambda:api.allocate_attempt('alloc_attempt_key_004',case['name'],cfgx['main_bp'],3,pol_name,3)),'insufficient eligible families for skill Reading')
            assert {dt:frappe.db.count(dt) for dt in before}==before
            return dict(obs,no_partial_state=True)
        check('alloc-fourth-attempt-unavailable-fail-closed',fourth_unavailable)
        def cannot_list(dt):
            # No DocType grant (Author/outsider/guard) fails closed with
            # PermissionError; a grant plus 1=0 query returns []. Both are denials.
            try:return not frappe.get_list(dt)
            except frappe.PermissionError:return True
        def cannot_read_doc(doctype,name):
            try:return not frappe.get_doc(doctype,name).has_permission('read')
            except frappe.PermissionError:return True
        def alloc_reads():
            for label in ('second_author','other','outsider'):
                frappe.set_user(users[label])
                for dt in (api.CASE,api.ATTEMPT,api.MANIFEST,api.EXPOSURE):
                    assert cannot_list(dt),label
            frappe.set_user(users['second_author'])
            assert cannot_read_doc(api.ATTEMPT,alloc['attempt'])
            # Dual-role author includes Publisher: operational staff reads apply;
            # role union does not invent extra SoD on allocation records.
            frappe.set_user(users['author'])
            assert frappe.get_doc(api.ATTEMPT,alloc['attempt']).has_permission('read')
            for dt in (api.CASE,api.ATTEMPT,api.MANIFEST,api.EXPOSURE):
                assert frappe.get_list(dt),dt
            frappe.set_user(users['publisher'])
            for dt in (api.CASE,api.ATTEMPT,api.MANIFEST,api.EXPOSURE):
                assert frappe.get_list(dt),dt
            guard_name='AG-'+digest([api.BLUEPRINT,cfgx['main_bp']])[:32]
            assert frappe.db.exists(api.GUARD,guard_name)
            assert cannot_read_doc(api.GUARD,guard_name)
            assert cannot_list(api.GUARD)
            frappe.set_user(users['auditor'])
            for dt in (api.CASE,api.ATTEMPT,api.MANIFEST,api.EXPOSURE):
                assert frappe.get_list(dt),dt
            assert cannot_read_doc(api.GUARD,guard_name)
            return {'staff_only_records':True,'guard_internal':True,'dual_role_author_reads_as_publisher':True}
        check('alloc-role-and-list-parity',alloc_reads)
        def alloc_generic_write():
            frappe.set_user(users['publisher']);doc=frappe.get_doc(api.ATTEMPT,alloc['attempt']);doc.subject='forged@example.test';doc.flags.ignore_permissions=True
            return denied(lambda:doc.save(ignore_permissions=True))
        check('alloc-ignore-permissions-does-not-bypass-controller',alloc_generic_write)
        check('alloc-direct-db-set-denied',lambda:denied(lambda:frappe.get_doc(api.MANIFEST,alloc['manifest']).db_set('form_hash','f'*64)))
        check('alloc-direct-db-update-denied',lambda:denied(lambda:frappe.get_doc(api.ATTEMPT,alloc['attempt']).db_update()))
        check('alloc-delete-denied',lambda:denied(lambda:frappe.delete_doc(api.CASE,case['name'],ignore_permissions=True)))
        def forged_manifest():
            frappe.set_user(users['publisher'])
            with _command('allocate_attempt',users['publisher']):
                frappe.get_doc(dict(doctype=api.MANIFEST,attempt=alloc['attempt'],
                    algorithm_version=allocation.ALGORITHM_VERSION,seed='0'*64,pool_digest='0'*64,
                    form_json=_canonical({'algorithm':allocation.ALGORITHM_VERSION,'items':[]}),
                    form_hash='f'*64,status='Committed',synthetic=1)).insert(ignore_permissions=True)
        check('alloc-forged-manifest-hash-denied',lambda:denied(forged_manifest))
        def alloc_rollback_proof():
            frappe.set_user(users['publisher']);frappe.db.savepoint('alloc_atomic')
            old={dt:frappe.db.count(dt) for dt in (api.ATTEMPT,api.MANIFEST,api.EXPOSURE,api.OP,api.AUDIT)}
            original=frappe.get_doc
            def injected(*args,**kwargs):
                if args and isinstance(args[0],dict) and args[0].get('doctype')==api.EXPOSURE:raise RuntimeError('synthetic allocation exposure failure')
                return original(*args,**kwargs)
            try:
                with patch.object(frappe,'get_doc',side_effect=injected):api.allocate_attempt('alloc_atomic_key_0001',case2['name'],cfgx['main_bp'],3,pol_name,3)
            except RuntimeError:frappe.db.rollback(save_point='alloc_atomic')
            else:raise AssertionError('Failure injection did not execute')
            assert {dt:frappe.db.count(dt) for dt in old}==old
            return {'real_database_rollback':True,'injected_boundary':'exposure reservation'}
        check('alloc-atomic-attempt-manifest-exposure-rollback',alloc_rollback_proof)
        case4=check('alloc-create-case-transient-subject',lambda:as_user('publisher',lambda:api.create_case('alloc_case_key_0004',users['candidate4'])))
        def alloc_transient(exhaust=False):
            frappe.set_user(users['publisher']);frappe.db.commit()
            calls=[];original=allocation.allocate
            prev=frappe.db.count(api.ATTEMPT,{'case_name':case4['name']})
            key='alloc_exhaust_key_0001' if exhaust else 'alloc_retry_key_0001'
            def flaky(*args,**kwargs):
                calls.append(1)
                if exhaust or len(calls)==1:raise frappe.QueryDeadlockError('synthetic allocation deadlock')
                return original(*args,**kwargs)
            with patch.object(allocation,'allocate',side_effect=flaky):
                if exhaust:
                    try:api.allocate_attempt(key,case4['name'],cfgx['main_bp'],3,pol_name,3)
                    except frappe.QueryDeadlockError:pass
                    else:raise AssertionError('Retry exhaustion must fail closed')
                else:result=api.allocate_attempt(key,case4['name'],cfgx['main_bp'],3,pol_name,3)
            assert len(calls)==(4 if exhaust else 2)
            assert frappe.db.count(api.ATTEMPT,{'case_name':case4['name']})==prev+(0 if exhaust else 1)
            if not exhaust:
                m=frappe.get_doc(api.MANIFEST,result['manifest']);form=json.loads(m.form_json)
                assert m.form_hash==digest(form)
            return {'attempts':len(calls),'whole_command_reentered':True,'exhaustion':exhaust}
        check('alloc-whole-command-transient-recovery',alloc_transient)
        check('alloc-retry-exhaustion-bounded',lambda:alloc_transient(True))
        frappe.db.commit();frappe.destroy();connect('placement-second.localhost')
        def alloc_second_site():
            assert frappe.db.count(api.CASE)==0 and frappe.db.count(api.ATTEMPT)==0
            assert frappe.db.count(api.MANIFEST)==0 and frappe.db.count(api.EXPOSURE)==0
            return {'allocation_absent_on_second_site':True}
        check('second-site-no-first-site-allocation-record',alloc_second_site)
        frappe.destroy();connect('placement-test.localhost')
        # --- Increment 4: staff-supervised Digital verify / deliver / save / seal ---
        check('deliver-verify-publisher-denied',lambda:denied(lambda:as_user('publisher',lambda:api.verify_attempt('deliver_pub_verify_0001',alloc3['attempt'],1))))
        check('deliver-verify-author-denied',lambda:denied(lambda:as_user('second_author',lambda:api.verify_attempt('deliver_auth_verify_0001',alloc3['attempt'],1))))
        check('deliver-verify-outsider-denied',lambda:denied(lambda:as_user('outsider',lambda:api.verify_attempt('deliver_out_verify_0001',alloc3['attempt'],1))))
        def allocator_sod():
            frappe.set_user('Administrator')
            u=frappe.get_doc('User',users['publisher']);u.append('roles',{'role':'Placement Invigilator'});u.save();frappe.db.commit();frappe.clear_cache(user=u.name)
            try:return denied(lambda:as_user('publisher',lambda:api.verify_attempt('deliver_sod_verify_0001',alloc3['attempt'],1)))
            finally:
                frappe.set_user('Administrator');u=frappe.get_doc('User',users['publisher']);u.roles=[];u.append('roles',{'role':'Placement Publisher'});u.save();frappe.db.commit();frappe.clear_cache(user=u.name)
        check('deliver-allocator-operator-denied',allocator_sod)
        check('deliver-before-verify-denied',lambda:denied(lambda:as_user('invigilator',lambda:api.deliver_attempt('deliver_before_verify_001',alloc['attempt'],1))))
        def physical_denied():
            phys=publish_config_flow('SYN-BP-PHYS-1',dict(alloc_bp2,mode='Physical'))
            phys_alloc=as_user('publisher',lambda:api.allocate_attempt('alloc_phys_key_0001',case2['name'],phys['name'],3,pol_name,3))
            obs=denied(lambda:as_user('invigilator',lambda:api.verify_attempt('deliver_phys_verify_0001',phys_alloc['attempt'],1)))
            assert frappe.get_doc(api.ATTEMPT,phys_alloc['attempt']).status=='Allocated'
            return dict(obs,mode='Physical',status='Allocated')
        check('deliver-physical-mode-denied',physical_denied)
        verified=check('deliver-verify-happy',lambda:as_user('invigilator',lambda:api.verify_attempt('deliver_verify_key_0001',alloc3['attempt'],1)))
        assert verified['status']=='Verified' and verified['version']==2 and verified['verified_by']==users['invigilator']
        def verify_replay():
            count=frappe.db.count(api.AUDIT)
            value=as_user('invigilator',lambda:api.verify_attempt('deliver_verify_key_0001',alloc3['attempt'],1))
            assert value==verified and frappe.db.count(api.AUDIT)==count
            return {'same_result':True,'no_duplicate_audit':True}
        check('deliver-verify-idempotent',verify_replay)
        check('deliver-verify-stale-version-denied',lambda:denied(lambda:as_user('invigilator',lambda:api.verify_attempt('deliver_stale_verify_0001',alloc3['attempt'],1))))
        check('deliver-second-verify-denied',lambda:denied(lambda:as_user('invigilator',lambda:api.verify_attempt('deliver_second_verify_001',alloc3['attempt'],2))))
        delivered=check('deliver-happy-path',lambda:as_user('invigilator',lambda:api.deliver_attempt('deliver_attempt_key_001',alloc3['attempt'],2)))
        assert delivered['status']=='In Progress' and delivered['version']==3 and delivered['item_count']==9
        def deliver_replay():
            count=frappe.db.count(api.AUDIT)
            value=as_user('invigilator',lambda:api.deliver_attempt('deliver_attempt_key_001',alloc3['attempt'],2))
            assert value==delivered and frappe.db.count(api.AUDIT)==count
            return {'same_result':True,'no_duplicate_delivery':True}
        check('deliver-idempotent-replay',deliver_replay)
        def exposure_converted():
            rows=frappe.get_all(api.EXPOSURE,filters={'attempt':alloc3['attempt']},fields=['family','event'])
            reserved={r.family for r in rows if r.event=='Reserved'}
            delivered_f={r.family for r in rows if r.event=='Delivered'}
            assert reserved==delivered_f and len(reserved)==9
            return {'reserved':9,'delivered':9,'reserved_retained':True}
        check('deliver-exposure-converted',exposure_converted)
        def projection_strips_secrets():
            projection=delivered['projection'];blob=json.dumps(projection)
            assert 'seed' not in projection and 'algorithm' not in projection and 'pool_digest' not in projection
            seed=frappe.db.get_value(api.MANIFEST,alloc3['manifest'],'seed')
            assert seed and seed not in blob
            for item in projection['items']:
                assert 'family' not in item and 'item' not in item and 'answer' not in item
                assert item['prompt'].startswith('SYNTHETIC: ') and item['options']
            key_names=[row.name for row in frappe.get_all(api.KEY,fields=['name'])]
            assert not any(name in blob for name in key_names)
            return {'items':len(projection['items']),'no_seed_or_key':True}
        check('deliver-projection-strips-secrets',projection_strips_secrets)
        def clock_started():
            a=frappe.get_doc(api.ATTEMPT,alloc3['attempt'])
            assert a.started_at and a.deadline_at and a.status=='In Progress'
            assert delivered['started_at'] and delivered['deadline_at']
            return {'started_at':delivered['started_at'],'deadline_at':delivered['deadline_at']}
        check('deliver-clock-started',clock_started)
        first=delivered['projection']['items'][0]
        oid=first['options'][0]['id'];occ=first['order']
        oid2=first['options'][1]['id'] if len(first['options'])>1 else oid
        check('deliver-save-publisher-denied',lambda:denied(lambda:as_user('publisher',lambda:api.save_response('deliver_pub_save_0001',alloc3['attempt'],3,occ,0,oid,0))))
        check('deliver-save-unknown-occurrence-denied',lambda:denied(lambda:as_user('invigilator',lambda:api.save_response('deliver_bad_occ_0001',alloc3['attempt'],3,99,0,oid,0))))
        check('deliver-save-unknown-option-denied',lambda:denied(lambda:as_user('invigilator',lambda:api.save_response('deliver_bad_opt_0001',alloc3['attempt'],3,occ,0,'not_an_option',0))))
        check('deliver-save-missing-requires-empty-option',lambda:denied(lambda:as_user('invigilator',lambda:api.save_response('deliver_missing_opt_0001',alloc3['attempt'],3,occ,0,oid,1))))
        saved=check('deliver-save-response',lambda:as_user('invigilator',lambda:api.save_response('deliver_save_key_0001',alloc3['attempt'],3,occ,0,oid,0)))
        assert saved['revision']==1 and saved['option_id']==oid and saved['missing']==0
        def save_replay():
            count=frappe.db.count(api.AUDIT)
            value=as_user('invigilator',lambda:api.save_response('deliver_save_key_0001',alloc3['attempt'],3,occ,0,oid,0))
            assert value==saved and frappe.db.count(api.AUDIT)==count
            assert frappe.db.count(api.RESPONSE,{'attempt':alloc3['attempt'],'occurrence':occ})==1
            return {'same_result':True,'one_revision':True}
        check('deliver-save-idempotent',save_replay)
        check('deliver-save-stale-revision-denied',lambda:denied(lambda:as_user('invigilator',lambda:api.save_response('deliver_stale_save_0001',alloc3['attempt'],3,occ,0,oid2,0))))
        revised=check('deliver-save-revise',lambda:as_user('invigilator',lambda:api.save_response('deliver_revise_key_0001',alloc3['attempt'],3,occ,1,oid2,0)))
        assert revised['revision']==2 and revised['option_id']==oid2
        def timeout_seal():
            started=frappe.utils.get_datetime(frappe.db.get_value(api.ATTEMPT,alloc3['attempt'],'started_at'))
            before=frappe.db.count(api.RESPONSE,{'attempt':alloc3['attempt']})
            with patch.object(api,'_now',return_value=started+timedelta(minutes=46)):
                value=as_user('invigilator',lambda:api.save_response('deliver_timeout_save_0001',alloc3['attempt'],3,2,0,oid,0))
            assert value['status']=='Sealed' and value['seal_reason']=='Timeout' and value['version']==4
            assert value['missing_count']==8
            assert frappe.db.count(api.RESPONSE,{'attempt':alloc3['attempt'],'occurrence':2,'missing':0})==0
            assert frappe.db.count(api.RESPONSE,{'attempt':alloc3['attempt']})==before+8
            return {'seal_reason':'Timeout','missing_count':8,'late_save_rejected':True}
        check('deliver-deadline-timeout-seal',timeout_seal)
        check('deliver-save-after-seal-denied',lambda:denied(lambda:as_user('invigilator',lambda:api.save_response('deliver_after_seal_0001',alloc3['attempt'],4,occ,2,oid,0))))
        check('deliver-seal-after-seal-denied',lambda:denied(lambda:as_user('invigilator',lambda:api.seal_attempt('deliver_reseal_key_0001',alloc3['attempt'],4,'Submitted'))))
        verified2=check('deliver-verify-second-form',lambda:as_user('invigilator',lambda:api.verify_attempt('deliver_verify_alloc2_001',alloc2['attempt'],1)))
        assert verified2['status']=='Verified'
        delivered2=check('deliver-second-form',lambda:as_user('invigilator',lambda:api.deliver_attempt('deliver_attempt_alloc2_1',alloc2['attempt'],2)))
        first2=delivered2['projection']['items'][0]
        saved2=check('deliver-save-second-form',lambda:as_user('invigilator',lambda:api.save_response('deliver_save_alloc2_0001',alloc2['attempt'],3,first2['order'],0,first2['options'][0]['id'],0)))
        assert saved2['revision']==1
        sealed2=check('deliver-submit-seal',lambda:as_user('invigilator',lambda:api.seal_attempt('deliver_seal_alloc2_0001',alloc2['attempt'],3,'Submitted')))
        assert sealed2['status']=='Sealed' and sealed2['seal_reason']=='Submitted' and sealed2['missing_count']==8
        def deliver_reads():
            frappe.set_user(users['invigilator'])
            for dt in (api.CASE,api.ATTEMPT,api.EXPOSURE,api.RESPONSE):
                assert frappe.get_list(dt),dt
            assert cannot_list(api.MANIFEST) and cannot_list(api.GUARD)
            frappe.set_user(users['second_author'])
            for dt in (api.CASE,api.ATTEMPT,api.MANIFEST,api.EXPOSURE,api.RESPONSE):
                assert cannot_list(dt),dt
            frappe.set_user(users['publisher'])
            assert frappe.get_list(api.RESPONSE) and frappe.get_list(api.MANIFEST)
            frappe.set_user(users['auditor'])
            assert frappe.get_list(api.RESPONSE) and frappe.get_list(api.MANIFEST)
            return {'invigilator_no_manifest':True,'author_denied':True,'staff_response_readable':True}
        check('deliver-role-and-list-parity',deliver_reads)
        def deliver_generic_write():
            frappe.set_user(users['invigilator']);doc=frappe.get_doc(api.ATTEMPT,alloc3['attempt']);doc.subject='forged@example.test';doc.flags.ignore_permissions=True
            return denied(lambda:doc.save(ignore_permissions=True))
        check('deliver-ignore-permissions-does-not-bypass-controller',deliver_generic_write)
        resp_name=frappe.db.get_value(api.RESPONSE,{'attempt':alloc3['attempt'],'occurrence':occ,'revision':2},'name')
        check('deliver-direct-db-set-denied',lambda:denied(lambda:frappe.get_doc(api.RESPONSE,resp_name).db_set('option_id','forged')))
        check('deliver-delete-denied',lambda:denied(lambda:frappe.delete_doc(api.RESPONSE,resp_name,ignore_permissions=True)))
        check('deliver-verify-fourth',lambda:as_user('invigilator',lambda:api.verify_attempt('deliver_verify_alloc4_001',alloc4['attempt'],1)))
        def deliver_rollback_proof():
            frappe.set_user(users['invigilator']);frappe.db.savepoint('deliver_atomic')
            old={dt:frappe.db.count(dt) for dt in (api.ATTEMPT,api.EXPOSURE,api.RESPONSE,api.OP,api.AUDIT)}
            original=frappe.get_doc
            def injected(*args,**kwargs):
                if args and isinstance(args[0],dict) and args[0].get('doctype')==api.EXPOSURE and args[0].get('event')=='Delivered':
                    raise RuntimeError('synthetic delivery exposure failure')
                return original(*args,**kwargs)
            try:
                with patch.object(frappe,'get_doc',side_effect=injected):api.deliver_attempt('deliver_atomic_key_0001',alloc4['attempt'],2)
            except RuntimeError:frappe.db.rollback(save_point='deliver_atomic')
            else:raise AssertionError('Failure injection did not execute')
            assert {dt:frappe.db.count(dt) for dt in old}==old
            assert frappe.get_doc(api.ATTEMPT,alloc4['attempt']).status=='Verified'
            return {'real_database_rollback':True,'injected_boundary':'delivered exposure'}
        check('deliver-atomic-exposure-rollback',deliver_rollback_proof)
        def deliver_transient(exhaust=False):
            frappe.set_user(users['invigilator']);frappe.db.commit()
            if exhaust:
                as_user('invigilator',lambda:api.verify_attempt('deliver_verify_alloc_0001',alloc['attempt'],1));frappe.db.commit()
                target,version,key=alloc['attempt'],2,'deliver_exhaust_key_0001'
            else:
                target,version,key=alloc4['attempt'],2,'deliver_retry_key_0001'
            calls=[];original=api._now
            def flaky():
                calls.append(1)
                if exhaust or len(calls)==1:raise frappe.QueryDeadlockError('synthetic delivery deadlock')
                return original()
            with patch.object(api,'_now',side_effect=flaky):
                if exhaust:
                    try:api.deliver_attempt(key,target,version)
                    except frappe.QueryDeadlockError:pass
                    else:raise AssertionError('Retry exhaustion must fail closed')
                else:result=api.deliver_attempt(key,target,version)
            assert len(calls)==(4 if exhaust else 2)
            if exhaust:
                assert frappe.get_doc(api.ATTEMPT,target).status=='Verified'
            else:
                assert result['status']=='In Progress' and frappe.db.count(api.EXPOSURE,{'attempt':target,'event':'Delivered'})==9
            return {'attempts':len(calls),'whole_command_reentered':True,'exhaustion':exhaust}
        check('deliver-whole-command-transient-recovery',lambda:deliver_transient(False))
        check('deliver-retry-exhaustion-bounded',lambda:deliver_transient(True))
        frappe.db.commit();frappe.destroy();connect('placement-second.localhost')
        def deliver_second_site():
            assert frappe.db.count(api.CASE)==0 and frappe.db.count(api.ATTEMPT)==0
            assert frappe.db.count(api.RESPONSE)==0 and frappe.db.count(api.EXPOSURE)==0
            return {'delivery_absent_on_second_site':True}
        check('second-site-no-first-site-delivery-record',deliver_second_site)
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
        sessions={label:login(label) for label in ('author','other','publisher','publisher2','second_author','auditor','outsider','invigilator')}
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
        # --- Increment 3 over HTTP: case + allocation routes, CSRF, containment, races, revocation ---
        def http_case_create():
            r=post('publisher','create_case',dict(request_key='http_case_key_0001',subject=users['candidate3']))
            assert r.status_code==200,f'case create HTTP {r.status_code}'
            return r.json()['message']
        httpcase=check('http-alloc-case-create',http_case_create)
        http_alloc_payload=dict(request_key='http_alloc_key_0001',case=httpcase['name'],
                                blueprint=cfgx['main_bp'],blueprint_version=3,policy=pol_name,policy_version=3)
        def http_alloc():
            r=post('publisher','allocate_attempt',http_alloc_payload);assert r.status_code==200,f'allocate HTTP {r.status_code}'
            return r.json()['message']
        httpalloc=check('http-alloc-positive-create',http_alloc)
        assert httpalloc['status']=='Allocated' and httpalloc['ordinal']==1
        check('http-alloc-guest-denied',lambda:http_denied(requests.post(base+'/api/method/toefl_house.api.allocate_attempt',headers={'Host':'placement-test.localhost'},json=http_alloc_payload,timeout=30)))
        check('http-alloc-unrelated-role-denied',lambda:http_denied(post('outsider','allocate_attempt',dict(http_alloc_payload,request_key='http_alloc_out_0001'))))
        check('http-alloc-wrong-role-denied',lambda:http_denied(post('second_author','allocate_attempt',dict(http_alloc_payload,request_key='http_alloc_author_01'))))
        check('http-alloc-case-wrong-role-denied',lambda:http_denied(post('second_author','create_case',dict(request_key='http_case_second_001',subject=users['candidate3']))))
        check('http-alloc-get-cannot-mutate',lambda:http_denied(sessions['publisher'].get(base+'/api/method/toefl_house.api.allocate_attempt',params={'request_key':'http_alloc_get_0001'},timeout=30)))
        def http_alloc_csrf():
            s=sessions['publisher'];token=s.headers.pop('X-Frappe-CSRF-Token')
            try:return http_denied(s.post(base+'/api/method/toefl_house.api.allocate_attempt',json=dict(http_alloc_payload,request_key='http_alloc_csrf_0001'),timeout=30),csrf=True)
            finally:s.headers['X-Frappe-CSRF-Token']=token
        check('http-alloc-csrf-negative-with-positive-control',http_alloc_csrf)
        attempt_url=base+'/api/resource/'+quote(api.ATTEMPT,safe='')+'/'+httpalloc['attempt']
        check('http-alloc-direct-crud-mutation-denied',lambda:http_denied(sessions['publisher'].put(attempt_url,json={'subject':'forged@example.test'},timeout=30)))
        check('http-alloc-other-role-read-denied',lambda:http_denied(sessions['second_author'].get(attempt_url,timeout=30)))
        def http_alloc_idem():
            def request(_):
                s=requests.Session();s.headers.update(sessions['publisher'].headers);s.cookies.update(sessions['publisher'].cookies)
                return s.post(base+'/api/method/toefl_house.api.allocate_attempt',json=dict(http_alloc_payload,blueprint=cfgx['small_bp'],request_key='http_alloc_idem_0001'),timeout=40)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rs=list(pool.map(request,range(2)))
            assert [r.status_code for r in rs]==[200,200],str([r.json().get('exc_type') for r in rs])
            results=[r.json()['message'] for r in rs];assert results[0]==results[1]
            assert frappe.db.count(api.ATTEMPT,{'case_name':httpcase['name']})==2
            assert frappe.db.count(api.AUDIT,{'target':results[0]['attempt']})==1
            return {'http_statuses':[200,200],'one_attempt_for_key':True}
        check('http-alloc-concurrent-create-idempotency',http_alloc_idem)
        def http_alloc_race():
            def request(i):
                s=requests.Session();s.headers.update(sessions['publisher'].headers);s.cookies.update(sessions['publisher'].cookies)
                return s.post(base+'/api/method/toefl_house.api.allocate_attempt',json=dict(http_alloc_payload,blueprint=cfgx['small_bp'],request_key='http_alloc_race_%04d'%i),timeout=40)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rs=list(pool.map(request,range(2)))
            assert [r.status_code for r in rs]==[200,200],str([r.json().get('exc_type') for r in rs])
            results=[r.json()['message'] for r in rs]
            assert sorted(r['ordinal'] for r in results)==[3,4]
            fams=[{i['family'] for i in json.loads(frappe.get_doc(api.MANIFEST,r['manifest']).form_json)['items']} for r in results]
            assert not (fams[0]&fams[1])
            return {'http_statuses':[200,200],'ordinals':[3,4],'concurrent_forms_disjoint':True}
        check('http-alloc-concurrent-distinct-keys',http_alloc_race)

        # --- Increment 4 over HTTP: verify/deliver/save/seal, CSRF, containment, races, revocation ---
        def http_verify():
            r=post('invigilator','verify_attempt',dict(request_key='http_verify_key_0001',attempt=httpalloc['attempt'],expected_version=1))
            assert r.status_code==200,f'verify HTTP {r.status_code} {r.text[:200]}'
            return r.json()['message']
        httpverified=check('http-deliver-verify',http_verify)
        assert httpverified['status']=='Verified' and httpverified['version']==2
        http_deliver_payload=dict(request_key='http_deliver_key_0001',attempt=httpalloc['attempt'],expected_version=2)
        def http_deliver():
            r=post('invigilator','deliver_attempt',http_deliver_payload);assert r.status_code==200,f'deliver HTTP {r.status_code} {r.text[:200]}'
            return r.json()['message']
        httpdelivered=check('http-deliver-positive',http_deliver)
        assert httpdelivered['status']=='In Progress' and httpdelivered['version']==3
        check('http-deliver-guest-denied',lambda:http_denied(requests.post(base+'/api/method/toefl_house.api.deliver_attempt',headers={'Host':'placement-test.localhost'},json=http_deliver_payload,timeout=30)))
        check('http-deliver-unrelated-role-denied',lambda:http_denied(post('outsider','deliver_attempt',dict(http_deliver_payload,request_key='http_deliver_out_0001'))))
        check('http-deliver-wrong-role-denied',lambda:http_denied(post('second_author','deliver_attempt',dict(http_deliver_payload,request_key='http_deliver_author_01'))))
        check('http-deliver-publisher-denied',lambda:http_denied(post('publisher','deliver_attempt',dict(http_deliver_payload,request_key='http_deliver_pub_0001'))))
        check('http-deliver-get-cannot-mutate',lambda:http_denied(sessions['invigilator'].get(base+'/api/method/toefl_house.api.deliver_attempt',params={'request_key':'http_deliver_get_0001'},timeout=30)))
        def http_deliver_csrf():
            s=sessions['invigilator'];token=s.headers.pop('X-Frappe-CSRF-Token')
            try:return http_denied(s.post(base+'/api/method/toefl_house.api.deliver_attempt',json=dict(http_deliver_payload,request_key='http_deliver_csrf_0001'),timeout=30),csrf=True)
            finally:s.headers['X-Frappe-CSRF-Token']=token
        check('http-deliver-csrf-negative-with-positive-control',http_deliver_csrf)
        check('http-deliver-direct-crud-mutation-denied',lambda:http_denied(sessions['invigilator'].put(attempt_url,json={'status':'Sealed'},timeout=30)))
        http_first=httpdelivered['projection']['items'][0]
        http_save_payload=dict(request_key='http_save_key_0001',attempt=httpalloc['attempt'],expected_version=3,
                               occurrence=http_first['order'],expected_revision=0,option_id=http_first['options'][0]['id'],missing=0)
        def http_save():
            r=post('invigilator','save_response',http_save_payload);assert r.status_code==200,f'save HTTP {r.status_code} {r.text[:200]}'
            return r.json()['message']
        httpsaved=check('http-save-positive',http_save)
        assert httpsaved['revision']==1
        resp_url=base+'/api/resource/'+quote(api.RESPONSE,safe='')+'/'+frappe.db.get_value(api.RESPONSE,{'attempt':httpalloc['attempt'],'occurrence':http_first['order'],'revision':1},'name')
        check('http-deliver-other-role-response-read-denied',lambda:http_denied(sessions['second_author'].get(resp_url,timeout=30)))
        def http_save_idem():
            p=dict(http_save_payload,request_key='http_save_idem_0001',occurrence=httpdelivered['projection']['items'][1]['order'],
                   option_id=httpdelivered['projection']['items'][1]['options'][0]['id'])
            def request(_):
                s=requests.Session();s.headers.update(sessions['invigilator'].headers);s.cookies.update(sessions['invigilator'].cookies)
                return s.post(base+'/api/method/toefl_house.api.save_response',json=p,timeout=40)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rs=list(pool.map(request,range(2)))
            assert [r.status_code for r in rs]==[200,200],str([r.json().get('exc_type') for r in rs])
            results=[r.json()['message'] for r in rs];assert results[0]==results[1]
            assert frappe.db.count(api.RESPONSE,{'attempt':httpalloc['attempt'],'occurrence':p['occurrence']})==1
            return {'http_statuses':[200,200],'one_revision':True}
        check('http-save-concurrent-idempotency',http_save_idem)
        def http_seal():
            r=post('invigilator','seal_attempt',dict(request_key='http_seal_key_0001',attempt=httpalloc['attempt'],expected_version=3,reason='Submitted'))
            assert r.status_code==200,f'seal HTTP {r.status_code} {r.text[:200]}'
            return r.json()['message']
        httpsealed=check('http-seal-submitted',http_seal)
        assert httpsealed['status']=='Sealed' and httpsealed['seal_reason']=='Submitted'
        def deliver_revoke():
            frappe.set_user('Administrator');u=frappe.get_doc('User',users['invigilator']);u.roles=[];u.save();frappe.db.commit();frappe.clear_cache(user=u.name)
            return http_denied(post('invigilator','seal_attempt',dict(request_key='http_deliver_revoked_001',attempt=httpalloc['attempt'],expected_version=4,reason='Submitted')))
        check('http-deliver-revoked-invigilator-old-session-denied',deliver_revoke)
        def alloc_revoke():
            frappe.set_user('Administrator');u=frappe.get_doc('User',users['publisher']);u.roles=[];u.save();frappe.db.commit();frappe.clear_cache(user=u.name)
            return http_denied(post('publisher','allocate_attempt',dict(http_alloc_payload,blueprint=cfgx['small_bp'],request_key='http_alloc_revoked_001')))
        check('http-alloc-revoked-publisher-old-session-denied',alloc_revoke)
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
