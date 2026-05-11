# KIS API 접근 토큰 발급 및 자동 갱신 모듈 (파일 쮨시로 재시작 시 재사용)
import requests
import json
import urllib3
from datetime import datetime, timedelta
from pathlib import Path
from config.settings import KIS_APP_KEY, KIS_APP_SECRET, KIS_BASE_URL, KIS_IS_MOCK

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOKEN_FILE = Path(__file__).parent / 'config' / 'token_cache.json'

def _load_token_from_file():
    if not TOKEN_FILE.exists():
        return None, None
    try:
        with open(TOKEN_FILE, 'r') as f:
            data = json.load(f)
        expires_at = datetime.fromisoformat(data['expires_at'])
        if expires_at > datetime.now():
            return data['token'], expires_at
    except Exception:
        pass
    return None, None

def _save_token_to_file(token, expires_at):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, 'w') as f:
        json.dump({'token': token, 'expires_at': expires_at.isoformat()}, f)

def get_access_token():
    token, expires_at = _load_token_from_file()
    if token:
        return token

    url = f'{KIS_BASE_URL}/oauth2/tokenP'
    headers = {'content-type': 'application/json'}
    body = {
        'grant_type': 'client_credentials',
        'appkey': KIS_APP_KEY,
        'appsecret': KIS_APP_SECRET
    }

    # 모의투자 서버는 SSL 인증서 호스트명 불일치 문제가 있어 verify=False 사용
    verify = not KIS_IS_MOCK
    res = requests.post(url, headers=headers, data=json.dumps(body), verify=verify)
    res.raise_for_status()
    data = res.json()

    token = data['access_token']
    expires_at = datetime.now() + timedelta(seconds=data['expires_in'] - 60)
    _save_token_to_file(token, expires_at)

    return token

def get_headers(tr_id):
    token = get_access_token()
    return {
        'content-type': 'application/json',
        'authorization': f'Bearer {token}',
        'appkey': KIS_APP_KEY,
        'appsecret': KIS_APP_SECRET,
        'tr_id': tr_id
    }
