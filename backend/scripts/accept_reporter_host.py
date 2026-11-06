"""Read-only reporter/camera acceptance on the actual host. Prompts for password.

No reports, devices, notifications, migrations, service restarts or deletions are
performed. Optional FFmpeg decoding validates video frames, not only playlist HTTP.
"""
import argparse
from datetime import datetime, timezone
import getpass
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:18000')
    parser.add_argument('--email', required=True)
    parser.add_argument('--property-id', type=int)
    parser.add_argument('--decode', action='store_true', help='Require FFmpeg to decode a live camera frame.')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'operational-evidence/reporter-acceptance.json')
    args = parser.parse_args()
    origin = urlsplit(args.url)
    if origin.scheme not in ('http', 'https') or not origin.hostname or origin.username or origin.password or origin.query or origin.fragment:
        parser.error('Use an HTTP(S) backend URL without credentials, query or fragment.')
    if args.decode and not shutil.which('ffmpeg'):
        parser.error('Install FFmpeg before using --decode.')
    password = getpass.getpass('Reporter/owner password: ')
    result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'checks': [], 'physical_device_tested': False}
    def record(name, passed, **details):
        result['checks'].append({'name': name, 'passed': passed, **details})
        print(('PASS ' if passed else 'FAIL ') + name)
    try:
        with httpx.Client(base_url=args.url.rstrip('/'), timeout=25, follow_redirects=False) as client:
            response = client.get('/health/ready')
            record('database and MQTT readiness', response.status_code == 200)
            response = client.post('/api/v1/auth/login', json={'email': args.email, 'password': password})
            if response.status_code != 200:
                raise RuntimeError('Login failed; check the account and deployed backend.')
            token = response.json()['access_token']
            auth = {'Authorization': 'Bearer ' + token}
            record('reporter login', True)
            profile = client.get('/api/v1/auth/me', headers=auth)
            profile.raise_for_status()
            properties = [p for p in profile.json()['properties'] if p['role'] in ('owner', 'reporter')]
            target = next((p for p in properties if args.property_id is None or p['id'] == args.property_id), None)
            if target is None:
                raise RuntimeError('No authorized reporter/owner property is available.')
            params = {'property_id': target['id']}
            response = client.get('/api/v1/reporter/summary', params=params, headers=auth)
            record('property summary', response.status_code == 200)
            cameras = client.get('/api/v1/reporter/cameras', params=params, headers=auth)
            cameras.raise_for_status()
            record('camera configuration present', bool(cameras.json()))
            for camera in cameras.json():
                record(f"camera #{camera['id']} health", camera['connection_status'] == 'online')
                if not camera['enabled']:
                    continue
                grant = client.post(f"/api/v1/reporter/cameras/{camera['id']}/live/access", params=params, headers=auth)
                record(f"camera #{camera['id']} live authorization", grant.status_code == 200)
                if grant.status_code != 200:
                    continue
                url = grant.json()['url']
                response = client.get(url)
                valid = response.status_code == 200 and response.text.startswith('#EXTM3U')
                record(f"camera #{camera['id']} live playlist", valid)
                if valid and args.decode:
                    process = subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-i', args.url.rstrip('/') + url,
                        '-frames:v', '1', '-f', 'null', '-'], capture_output=True, timeout=45)
                    record(f"camera #{camera['id']} video frame decoded", process.returncode == 0)
            # Never log the media grants, email, password or access token.
            print('Complete the physical-device and browser checklist in docs/runbooks/reporter-completion.md.')
    except Exception as error:
        record('acceptance completed', False, error_type=type(error).__name__)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print('Sanitized evidence written to', args.output)
    return 0 if result['checks'] and all(item['passed'] for item in result['checks']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
