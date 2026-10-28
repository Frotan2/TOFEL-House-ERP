"""Expanded real HTTP isolation checks on owned synthetic sites, after native policy.

Writes deliberately target synthetic records only. No UI hiding or mocked permissions.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import quote


def main():
    import requests
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Disposable Actions runner only')
    primary_site = os.environ.get('FOUNDATION_PRIMARY_SITE', 'foundation.localhost')
    secondary_site = os.environ.get('FOUNDATION_SECONDARY_SITE', 'restore.localhost')
    allowed_sites = {'foundation.localhost', 'restore.localhost', 'recovery.localhost'}
    if primary_site not in allowed_sites or secondary_site not in allowed_sites or primary_site == secondary_site:
        raise SystemExit('Only distinct disposable sites may be probed')
    records = json.loads(Path(os.environ['FOUNDATION_BUSINESS_REPORT']).read_text())['records']
    destination = Path(os.environ['FOUNDATION_ISOLATION_REPORT'])
    report = {'status': 'running', 'scope': 'Restricted native policy; real HTTP, synthetic data only',
              'checks': [], 'phase2_gate_passed': False, 'primary_site': primary_site, 'secondary_site': secondary_site}
    base = 'http://127.0.0.1:8080'

    def check(name, fn):
        start = time.monotonic()
        try:
            value = fn()
            report['checks'].append({'name': name, 'status': 'pass', 'observation': value,
                                     'seconds': round(time.monotonic()-start, 3)})
        except Exception as exc:
            # No response bodies, cookies, CSRF tokens or credentials in evidence.
            report['checks'].append({'name': name, 'status': 'fail', 'exception': type(exc).__name__, 'message': str(exc)[:250]})
        destination.write_text(json.dumps(report, indent=2)+'\n')

    def login(user, site=primary_site):
        s = requests.Session()
        s.headers['Host'] = site
        password = os.environ['FOUNDATION_ADMIN_PASSWORD' if user == 'Administrator' else 'FOUNDATION_TEST_PASSWORD']
        r = s.post(base+'/api/method/login', data={'usr': user, 'pwd': password}, timeout=30)
        assert r.status_code == 200, f'login status {r.status_code}'
        r = s.get(base+'/api/method/frappe.auth.get_logged_user', timeout=30)
        assert r.status_code == 200 and r.json().get('message') == user, 'identity mismatch'
        page = s.get(base+'/edu-portal', timeout=30)
        match = re.search(r"window.csrf_token\s*=\s*['\"]([^'\"]+)['\"]", page.text)
        csrf_present = bool(match and match[1] not in ('None', ''))
        report['checks'].append({'name':site+'-'+user+'-portal-csrf-present',
                                'status':'pass' if csrf_present else 'fail',
                                'observation':{'page_http_status':page.status_code,'token_assignment_present':bool(match),'nonempty_token':csrf_present}})
        # A missing token remains a failed gate, while independent read/permission
        # checks continue. Never manufacture a token or disable CSRF validation.
        if csrf_present:
            s.headers['X-Frappe-CSRF-Token'] = match[1]
        return s

    def read(s, path, allowed, expected=None, params=None):
        r = s.get(base+path, params=params, timeout=30, allow_redirects=False)
        if allowed:
            assert r.status_code == 200, f'positive control HTTP {r.status_code}'
            if expected:
                assert r.json()['data']['name'] == expected, 'target mismatch'
        else:
            assert r.status_code == 403, f'expected authorization denial, HTTP {r.status_code}'
            error = r.json()
            types = {error.get('exc_type')} | {item.get('type') for item in error.get('errors', [])}
            assert 'PermissionError' in types, 'denial not a document permission error'
        return {'http_status': r.status_code}

    try:
        alpha, beta = [login(f'validation-{label}@example.test') for label in ('alpha','beta')]
        admin, restored = login('Administrator'), login('Administrator', secondary_site)
        own, other = records['students']
        for version in ('resource', 'v2/document'):
            for s, target, allow, label in ((alpha,own,True,'alpha-own'),(alpha,other,False,'alpha-other'),
                                            (beta,other,True,'beta-own'),(beta,own,False,'beta-other')):
                path=f'/api/{version}/Student/{quote(target, safe="")}'
                if version == 'v2/document': path += '/'
                check(version+'-'+label, lambda s=s,path=path,allow=allow,target=target: read(s,path,allow,target))
        for doctype, key in (('Assessment Result','assessment_result'),('Student Attendance','attendance'),('Sales Invoice','invoice')):
            path='/api/resource/'+quote(doctype, safe='')+'/'+quote(records[key],safe='')
            check(key+'-own', lambda path=path,key=key: read(alpha,path,True,records[key]))
            check(key+'-other', lambda path=path: read(beta,path,False))

        for method in ('get_student_context','get_student_invoices'):
            path='/api/method/education.education.api.'+method
            check(method+'-own', lambda path=path: read(alpha,path,True,params={'student':own}))
            check(method+'-other', lambda path=path: read(beta,path,False,params={'student':own}))
        for user,label,target in ((alpha,'alpha',own),(beta,'beta',other)):
            def listing(user=user,target=target):
                r=user.get(base+'/api/resource/Student',params={'fields':json.dumps(['name'])},timeout=30)
                assert r.status_code==200
                names={d['name'] for d in r.json()['data']}
                assert names=={target}, 'list did not contain exactly the own Student'
                return {'own_only':True}
            check(label+'-rest-list',listing)
            check(label+'-rpc-own',lambda user=user,target=target: read(user,'/api/method/frappe.client.get',True,params={'doctype':'Student','name':target}))
        check('generic-rpc-other',lambda: read(alpha,'/api/method/frappe.client.get',False,params={'doctype':'Student','name':other}))

        def write_other(rpc=False):
            if rpc:
                r=alpha.post(base+'/api/method/frappe.client.set_value',json={'doctype':'Student','name':other,'fieldname':'first_name','value':'Unauthorized synthetic mutation'},timeout=30)
            else:
                r=alpha.put(base+'/api/resource/Student/'+quote(other,safe=''),json={'first_name':'Unauthorized synthetic mutation'},timeout=30)
            assert r.status_code==403 and r.json().get('exc_type')=='PermissionError', f'write not denied by permission check: HTTP {r.status_code}'
            return {'http_status':403,'permission_not_csrf_denial':True}
        check('rest-other-write-denied',write_other)
        check('rpc-other-write-denied',lambda:write_other(True))
        def unchanged():
            r=admin.get(base+'/api/resource/Student/'+quote(other,safe=''),timeout=30)
            assert r.status_code==200 and r.json()['data']['first_name']=='Validation beta', 'unauthorized mutation persisted'
            return {'unchanged':True}
        check('other-student-unchanged',unchanged)

        def file_check(s,allowed):
            r=s.get(base+records['private_file_url'],timeout=30,allow_redirects=False)
            if allowed:
                assert r.status_code==200 and hashlib.sha256(r.content).hexdigest()==records['private_file_sha256']
            else:
                assert r.status_code==403, f'private-file HTTP {r.status_code}'
            return {'http_status':r.status_code}
        guest=requests.Session();guest.headers['Host']=primary_site
        check('proxy-private-own',lambda:file_check(alpha,True))
        check('proxy-private-other',lambda:file_check(beta,False))
        check('proxy-private-guest',lambda:file_check(guest,False))
        check('guest-student-denied',lambda:read(guest,'/api/resource/Student/'+quote(own,safe=''),False))
        def replay_cookie():
            r=requests.get(base+'/api/method/frappe.auth.get_logged_user',headers={'Host':secondary_site,'Cookie':'sid='+alpha.cookies.get('sid')},timeout=30)
            assert r.status_code in (401,403), f'source session accepted by restore site: HTTP {r.status_code}'
            return {'source_sid_rejected_on_restore':True}
        check('cross-site-session-replay-denied',replay_cookie)
        path='/api/resource/ToDo/'+quote(records['source_only_todo'],safe='')
        check('source-only-marker-positive',lambda:read(admin,path,True,records['source_only_todo']))
        def absent_on_restore():
            r=restored.get(base+path,timeout=30)
            assert r.status_code==404, f'source-only marker leaked across site: HTTP {r.status_code}'
            return {'http_status':404}
        check('source-only-marker-absent-on-restore',absent_on_restore)
        def header_override():
            r=admin.get(base+path,headers={'X-Frappe-Site-Name':secondary_site},timeout=30)
            assert r.status_code==200 and r.json()['data']['name']==records['source_only_todo'], 'proxy accepted client site-routing override'
            return {'untrusted_site_header_overwritten':True}
        check('proxy-site-header-fixed-to-host',header_override)
        def sharing_denied(extra=None):
            data={'doctype':'Student','name':own,'user':'validation-beta@example.test','read':1}
            data.update(extra or {})
            r=alpha.post(base+'/api/method/frappe.share.add',json=data,timeout=30)
            assert r.status_code==403 and r.json().get('exc_type')=='PermissionError', f'sharing not denied: HTTP {r.status_code}'
            return {'http_status':403}
        check('student-cannot-share-own-record-to-peer',sharing_denied)
        # Adversarial input to the public dispatcher; no server-side bypass is
        # enabled. The expected result is that supplied flags cannot grant access.
        check('public-rpc-rejects-permission-bypass-flags',lambda:sharing_denied({'flags':{'ignore_share_permission':True},'ignore_permissions':True}))
        check('private-file-still-isolated-after-share-attempts',lambda:file_check(beta,False))
        def signup_disabled():
            r=guest.post(base+'/api/method/frappe.core.doctype.user.user.sign_up',json={'email':'validation-blocked-signup@example.test','full_name':'Blocked Signup','redirect_to':''},timeout=30)
            assert r.status_code==417 and r.json().get('exc_type')=='ValidationError' and 'Sign Up is disabled' in r.text, f'signup not rejected by native setting: HTTP {r.status_code}'
            return {'native_signup_disabled':True}
        check('public-signup-disabled',signup_disabled)
        check('unprovisioned-student-denied-to-alpha',lambda:read(alpha,'/api/resource/Student/'+quote(records['unprovisioned_student'],safe=''),False))
        def unprovisioned_cannot_login():
            r=guest.post(base+'/api/method/login',data={'usr':records['unprovisioned_email'],'pwd':os.environ['FOUNDATION_TEST_PASSWORD']},timeout=30)
            assert r.status_code in (401,403), f'unprovisioned student login HTTP {r.status_code}'
            return {'http_status':r.status_code}
        check('no-automatic-unscoped-student-login',unprovisioned_cannot_login)
        def csrf_enforced():
            payload={'doctype':'User','name':'validation-alpha@example.test','fieldname':'first_name','value':'Validation alpha'}
            headers={'Host':primary_site,'Cookie':'sid='+alpha.cookies.get('sid')}
            for token in (None,'invalid-synthetic-token'):
                h=dict(headers)
                if token: h['X-Frappe-CSRF-Token']=token
                r=requests.post(base+'/api/method/frappe.client.set_value',headers=h,json=payload,timeout=30)
                assert r.status_code==400 and r.json().get('exc_type')=='CSRFTokenError', f'missing/invalid CSRF was not rejected: HTTP {r.status_code}'
            r=alpha.post(base+'/api/method/frappe.client.set_value',json=payload,timeout=30)
            assert r.status_code==200, f'valid-CSRF own-profile control HTTP {r.status_code}'
            return {'missing_and_invalid_tokens_denied':True,'valid_token_positive_control':True}
        check('csrf-negative-and-positive-write-controls',csrf_enforced)
        def policy_revocation():
            r=admin.get(base+'/api/resource/User%20Permission',params={'filters':json.dumps({'user':'validation-alpha@example.test','allow':'Student'}),'fields':json.dumps(['name','user','allow','for_value','apply_to_all_doctypes'])},timeout=30)
            assert r.status_code==200 and len(r.json()['data'])==1
            rule=r.json()['data'][0]
            r=alpha.delete(base+'/api/resource/User%20Permission/'+quote(rule['name'],safe=''),timeout=30)
            assert r.status_code==403 and r.json().get('exc_type')=='PermissionError', 'student could alter native policy'
            removed=False
            try:
                r=admin.delete(base+'/api/resource/User%20Permission/'+quote(rule['name'],safe=''),timeout=30)
                removed=200 <= r.status_code < 300
                assert r.status_code==202, f'admin permission deletion HTTP {r.status_code}'
                for path in ('/api/resource/Student/'+quote(own,safe=''), records['private_file_url']):
                    r=alpha.get(base+path,timeout=30)
                    assert r.status_code==403, 'existing session retained access without required policy'
                r=requests.post(base+'/api/method/login',headers={'Host':primary_site},data={'usr':'validation-alpha@example.test','pwd':os.environ['FOUNDATION_TEST_PASSWORD']},timeout=30)
                assert r.status_code==403 and r.json().get('exc_type')=='PermissionError', 'unscoped Student login accepted'
            finally:
                if removed:
                    payload={k:v for k,v in rule.items() if k!='name'}
                    r=admin.post(base+'/api/resource/User%20Permission',json=payload,timeout=30)
                    assert r.status_code==200, f'policy restoration HTTP {r.status_code}'
            fresh=login('validation-alpha@example.test')
            read(fresh,'/api/resource/Student/'+quote(own,safe=''),True,own)
            return {'student_cannot_edit_policy':True,'existing_session_revoked':True,'unscoped_login_denied':True,'restored_policy_usable':True}
        check('native-policy-removal-fails-closed-and-recovers',policy_revocation)


    except Exception as exc:
        report['checks'].append({'name':'prerequisite','status':'fail','exception':type(exc).__name__,'message':str(exc)[:250]})
    report['status']='pass' if report['checks'] and all(c['status']=='pass' for c in report['checks']) else 'fail'
    destination.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
