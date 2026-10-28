"""Publish only owned synthetic markers through native realtime for socket tests."""
import os
from pathlib import Path
import sys
import json
if os.environ.get('GITHUB_ACTIONS') != 'true' or sys.argv[1:] not in (['document'],['task'],['prepare'],['revoke']):
    raise SystemExit('Disposable runner markers only')
import frappe
frappe.init(site='foundation.localhost',sites_path=str(Path.cwd()))
try:
    frappe.connect()
    r=json.loads(Path(os.environ['FOUNDATION_BUSINESS_REPORT']).read_text())['records']
    if sys.argv[1]=='prepare':
        from frappe.utils.background_jobs import enqueue
        frappe.set_user('validation-alpha@example.test')
        job=enqueue('frappe.utils.now',queue='short',job_id='foundation-resource-task')
        path=Path(os.environ['FOUNDATION_REALTIME_TASK'])
        path.write_text(json.dumps({'id':job.id}))
    elif sys.argv[1]=='revoke':
        from frappe.sessions import clear_sessions
        clear_sessions(user='validation-alpha@example.test',force=True)
        frappe.db.commit()
    elif sys.argv[1]=='document':
        frappe.publish_realtime('foundation_probe',{'marker':'owned-alpha-document'},doctype='Student',docname=r['students'][0])
    else:
        frappe.publish_realtime('foundation_probe',{'marker':'owned-task-progress'},task_id=json.loads(Path(os.environ['FOUNDATION_REALTIME_TASK']).read_text())['id'])
finally:
    frappe.destroy()
