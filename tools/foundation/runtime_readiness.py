"""Owned synthetic role, payroll privacy and HTTP operational qualification.

Runs only after existing recovery/isolation fixtures; never changes DocPerms.
"""
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or sys.argv[1:] != ['foundation.localhost']:
        raise SystemExit('Disposable hosted foundation only')
    import frappe
    import requests
    records = json.loads(Path(os.environ['FOUNDATION_BUSINESS_REPORT']).read_text())['records']
    report = {'status':'running','scope':'Synthetic native roles, real REST and operational HTTP; not production certification', 'checks':[], 'security_gate_passed':False}
    output = Path(os.environ['FOUNDATION_READINESS_REPORT'])
    frappe.init(site='foundation.localhost', sites_path=str(Path.cwd()))
    frappe.connect()
    frappe.set_user('Administrator')
    def check(name, fn):
        try:
            value = fn()
            report['checks'].append({'name':name,'status':'pass','observation':value})
        except Exception as exc:
            report['checks'].append({'name':name,'status':'fail','exception':type(exc).__name__,'message':str(exc)[:250]})
        output.write_text(json.dumps(report,indent=2)+'\n')
    sessions = {}
    try:
        for label,role in [('academic','Academics User'),('teacher','Instructor'),('accountant','Accounts User'),('hr','HR User'),('employee','Employee'),('guardian','Guardian')]:
            def provision(label=label,role=role):
                assert frappe.db.exists('Role',role), 'Native role unavailable: '+role
                user=frappe.get_doc({'doctype':'User','email':f'validation-{label}@example.test','first_name':'Validation '+label,'send_welcome_email':0,'user_type':'Website User' if label=='guardian' else 'System User','new_password':os.environ['FOUNDATION_TEST_PASSWORD'],'roles':[{'role':role}]}).insert()
                return {'user':user.name,'native_role':role}
            check('provision-'+label,provision)
        def links():
            employee=frappe.get_doc('Employee',records['employee'])
            employee.user_id='validation-teacher@example.test'
            employee.save()
            guardian=frappe.get_doc({'doctype':'Guardian','guardian_name':'Validation Guardian','user':'validation-guardian@example.test'}).insert()
            student=frappe.get_doc('Student',records['students'][0])
            student.append('guardians',{'guardian':guardian.name,'relation':'Father'})
            student.save()
            return {'teacher_employee_instructor_link':True,'guardian_linked_to_alpha_only':True}
        check('native-teacher-and-guardian-links',links)
        payroll={}
        def salary_fixture():
            from frappe.utils import get_first_day, get_last_day, today
            calendar=frappe.get_doc('Holiday List',records['holiday_list'])
            holiday_assignment=frappe.get_doc({'doctype':'Holiday List Assignment','holiday_list':calendar.name,'applicable_for':'Employee','assigned_to':records['employee'],'from_date':calendar.from_date}).insert()
            holiday_assignment.submit()
            component=frappe.get_doc({'doctype':'Salary Component','salary_component':'Validation Basic','salary_component_abbr':'VBASE','type':'Earning'}).insert()
            structure=frappe.get_doc({'doctype':'Salary Structure','name':'Validation Monthly','company':records['company'],'currency':'USD','payroll_frequency':'Monthly','earnings':[{'salary_component':component.name,'amount':100}]}).insert()
            structure.submit()
            assignment=frappe.get_doc({'doctype':'Salary Structure Assignment','employee':records['employee'],'salary_structure':structure.name,'from_date':get_first_day(today()),'base':100,'company':records['company'],'currency':'USD'}).insert()
            assignment.submit()
            slip=frappe.get_doc({'doctype':'Salary Slip','employee':records['employee'],'company':records['company'],'salary_structure':structure.name,'start_date':get_first_day(today()),'end_date':get_last_day(today()),'posting_date':today(),'payroll_frequency':'Monthly'}).insert()
            payroll['slip']=slip.name
            return {'draft_salary_slip':slip.name,'posting_proven':False}
        check('native-draft-payroll-fixture',salary_fixture)
        frappe.db.commit()
        for label in ('academic','teacher','accountant','hr','employee','guardian','alpha','beta'):
            def login(label=label):
                s=requests.Session();s.headers['Host']='foundation.localhost'
                r=s.post('http://127.0.0.1:8080/api/method/login',data={'usr':f'validation-{label}@example.test','pwd':os.environ['FOUNDATION_TEST_PASSWORD']},timeout=30)
                assert r.status_code==200, f'HTTP {r.status_code}'
                sessions[label]=s
                return {'http_status':200}
            check('login-'+label,login)
        def read(label,doctype,name,expected):
            r=sessions[label].get('http://127.0.0.1:8080/api/resource/'+quote(doctype,safe='')+'/'+quote(name,safe=''),timeout=30)
            assert r.status_code==expected, f'{label} {doctype}: expected {expected}, observed {r.status_code}'
            if expected==200: assert r.json()['data']['name']==name
            if expected==403: assert r.json().get('exc_type')=='PermissionError'
            return {'http_status':r.status_code}
        for label,expected in [('academic',200),('teacher',200),('guardian',200)]:
            check(label+'-linked-student-read',lambda label=label,expected=expected:read(label,'Student',records['students'][0],expected))
        check('guardian-other-student-denied',lambda:read('guardian','Student',records['students'][1],403))
        # Preserve native-role baseline, then test supported explicit scoping.
        def guardian_scope():
            student=frappe.get_doc('Student',records['students'][0])
            for allow,value in [('Student',student.name),('Customer',student.customer)]:
                frappe.get_doc({'doctype':'User Permission','user':'validation-guardian@example.test','allow':allow,'for_value':value,'apply_to_all_doctypes':1}).insert()
            frappe.db.commit()
            frappe.clear_cache(user='validation-guardian@example.test')
            return {'native_scopes_applied':True,'fail_closed_guardian_provisioning_proven':False}
        check('guardian-native-scope-configuration',guardian_scope)
        check('guardian-scoped-own-student-read',lambda:read('guardian','Student',records['students'][0],200))
        check('guardian-scoped-other-student-denied',lambda:read('guardian','Student',records['students'][1],403))
        for label,expected in [('accountant',200),('hr',403),('teacher',403),('guardian',403),('employee',403)]:
            check(label+'-finance-boundary',lambda label=label,expected=expected:read(label,'Sales Invoice',records['invoice'],expected))
        for label,expected in [('hr',200),('teacher',200),('academic',403),('accountant',403),('guardian',403),('employee',403),('alpha',403)]:
            def salary_read(label=label,expected=expected):
                assert 'slip' in payroll,'Salary fixture unavailable; no payroll authorization claim'
                return read(label,'Salary Slip',payroll['slip'],expected)
            check(label+'-payroll-boundary',salary_read)
        for label in ('alpha','beta'):
            def cache(label=label):
                r=sessions[label].get('http://127.0.0.1:8080/edu-portal',timeout=30)
                assert r.status_code==200
                headers={k:r.headers.get(k) for k in ('Cache-Control','Vary','X-Content-Type-Options','Content-Security-Policy')}
                assert 'no-store' in (headers['Cache-Control'] or '').lower(), 'Authenticated HTML lacks Cache-Control: no-store'
                return headers
            check(label+'-authenticated-html-cache-policy',cache)
        report['unverified']=['full mixed-role/report/export/print coverage','payroll GL posting','guardian portal and account relinking','TLS and production proxy headers','scheduled execution and service restart durability','cross-release upgrade']
    finally:
        report['status']='fail' if any(c['status']=='fail' for c in report['checks']) else 'pass'
        output.write_text(json.dumps(report,indent=2)+'\n')
        frappe.destroy()
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
