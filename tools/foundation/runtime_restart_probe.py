"""Read-only native state and queued-job proof across controlled process restart.

Only Gunicorn/RQ process replacement is tested; not Redis/DB/host failure or HA.
"""
import json
import os
from pathlib import Path
import sys
import time
import uuid


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or sys.argv[1:] not in (['prepare'], ['verify']):
        raise SystemExit('Disposable hosted restart probe only')
    import frappe
    import requests
    from rq.job import Job
    state_path = Path(os.environ['FOUNDATION_LAB']) / 'restart-probe-state.json'
    output = Path(os.environ['FOUNDATION_RESTART_REPORT'])
    report = {'status': 'running', 'scope': 'Controlled Gunicorn/RQ process restart only; Redis and MariaDB stay running', 'checks': []}
    frappe.init(site='foundation.localhost', sites_path=str(Path.cwd()))
    frappe.connect()
    frappe.set_user('Administrator')
    try:
        from frappe.utils.background_jobs import get_redis_conn
        if sys.argv[1] == 'prepare':
            records = json.loads(Path(os.environ['FOUNDATION_BUSINESS_REPORT']).read_text())['records']
            student = frappe.get_doc('Student', records['students'][0])
            marker = 'foundation-restart-' + uuid.uuid4().hex
            frappe.cache.set_value(marker, marker, expires_in_sec=600)
            job = frappe.enqueue('frappe.utils.now', queue='short', job_id=marker, enqueue_after_commit=False)
            status = job.get_status(refresh=True)
            assert getattr(status, 'value', str(status)) == 'queued', 'Job must be queued while the only worker is stopped'
            state_path.write_text(json.dumps({'job_id': job.id, 'marker': marker, 'student': student.name, 'student_name': student.student_name}))
            state_path.chmod(0o600)
            report.update(status='prepared', job_queued_while_worker_stopped=True)
        else:
            state = json.loads(state_path.read_text())
            assert frappe.cache.get_value(state['marker']) == state['marker'], 'Cache value not retained across client process restart'
            student = frappe.get_doc('Student', state['student'])
            assert student.student_name == state['student_name'], 'Native record changed'
            job = Job.fetch(state['job_id'], connection=get_redis_conn())
            started = time.monotonic()
            for _ in range(90):
                status = job.get_status(refresh=True)
                status = getattr(status, 'value', str(status))
                if status in ('finished', 'failed', 'stopped', 'canceled'): break
                time.sleep(1)
            assert status == 'finished', 'Previously queued job did not finish after replacement worker: ' + status
            assert isinstance(job.return_value(), str), 'Native job result missing'
            for _ in range(60):
                try:
                    response = requests.get('http://127.0.0.1:8080/api/method/ping', headers={'Host': 'foundation.localhost'}, timeout=2)
                    if response.status_code == 200 and response.json().get('message') == 'pong': break
                except (requests.RequestException, ValueError): pass
                time.sleep(1)
            else: raise AssertionError('Replacement web process did not serve native ping through proxy')
            report.update(status='pass', native_record_preserved=True, cache_value_preserved=True,
                          previously_queued_job_status=status, native_job_result_type='str',
                          proxy_native_ping='pong', seconds=round(time.monotonic()-started, 3),
                          limitations=['No Redis or database restart', 'No host crash or failover', 'No exactly-once or in-flight job claim', 'No pre-existing browser-session continuity claim'])
            frappe.cache.delete_value(state['marker'])
    except Exception as exc:
        report.update(status='fail', exception=type(exc).__name__, message=str(exc)[:250])
        raise
    finally:
        output.write_text(json.dumps(report, indent=2)+'\n')
        frappe.destroy()


if __name__ == '__main__': main()
