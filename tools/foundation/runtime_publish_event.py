"""Publish only owned synthetic markers through native realtime for socket tests."""
import os
from pathlib import Path
import sys
import json
if os.environ.get('GITHUB_ACTIONS') != 'true' or sys.argv[1:] not in (['document'],['task']):
    raise SystemExit('Disposable runner markers only')
import frappe
frappe.init(site='foundation.localhost',sites_path=str(Path.cwd()))
try:
    frappe.connect()
    r=json.loads(Path(os.environ['FOUNDATION_BUSINESS_REPORT']).read_text())['records']
    if sys.argv[1]=='document':
        frappe.publish_realtime('foundation_probe',{'marker':'owned-alpha-document'},doctype='Student',docname=r['students'][0])
    else:
        frappe.publish_realtime('foundation_probe',{'marker':'owned-task-progress'},task_id='foundation-owned-secret-task')
finally:
    frappe.destroy()
