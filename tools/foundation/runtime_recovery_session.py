"""Capture an owned source session before backup; prove restore revocation later.

The SID stays in a private runner-temporary file, never in evidence or stdout.
"""
import json
import os
from pathlib import Path
import sys


def main():
    import requests
    if os.environ.get('GITHUB_ACTIONS') != 'true' or sys.argv[1:] not in (['capture'], ['verify']):
        raise SystemExit('Disposable runner capture/verify only')
    path = Path(os.environ['FOUNDATION_CAPTURED_SESSION'])
    base = 'http://127.0.0.1:8000'
    if sys.argv[1] == 'capture':
        session = requests.Session()
        session.headers['Host'] = 'foundation.localhost'
        r = session.post(base+'/api/method/login', data={'usr':'validation-alpha@example.test', 'pwd':os.environ['FOUNDATION_TEST_PASSWORD']}, timeout=30)
        assert r.status_code == 200, f'Capture login HTTP {r.status_code}'
        sid = session.cookies.get('sid')
        assert sid and sid != 'Guest'
        path.write_text(json.dumps({'sid':sid}))
        path.chmod(0o600)
        print('Authenticated source session captured privately before backup')
    else:
        sid = json.loads(path.read_text())['sid']
        for site, expected in (('foundation.localhost',200), ('recovery.localhost',403)):
            r = requests.get(base+'/api/method/frappe.auth.get_logged_user', headers={'Host':site,'Cookie':'sid='+sid}, timeout=30)
            assert r.status_code == expected, f'Captured session on {site}: HTTP {r.status_code}'
            if expected == 200:
                assert r.json()['message'] == 'validation-alpha@example.test'
        print('Captured source session remains valid only on source; restored copy denied')


if __name__ == '__main__':
    main()
