# 네이버 증권 테마 크롤링 및 3단계 방어 로직 모듈
import requests
import json
import os
import time
from datetime import datetime
from bs4 import BeautifulSoup

THEME_CACHE = 'config/theme_cache.json'
THEME_LIST_URL = 'https://finance.naver.com/sise/theme.naver'
THEME_DETAIL_URL = 'https://finance.naver.com/sise/sise_group_detail.naver'

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://finance.naver.com/',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8',
}

MIN_MKTCAP_BIL = 5000   # 시총 최소 5000억 (억원 단위)
MAX_STOCKS_PER_THEME = 5

_crawl_source = 'unknown'  # 마지막 get_top_themes() 호출 결과: live | cache | fallback


def get_crawl_source() -> str:
    return _crawl_source

# 3단계 폴백 — 하드코딩 기본 테마
FALLBACK_THEMES = {
    '반도체': [('005930', '삼성전자'), ('000660', 'SK하이닉스'), ('009150', '삼성전기'), ('042700', '한미반도체'), ('000760', 'DB하이텍')],
    '2차전지': [('006400', '삼성SDI'), ('373220', 'LG에너지솔루션'), ('096770', 'SK이노베이션'), ('003670', '포스코퓨처엠'), ('051910', 'LG화학')],
    '바이오/제약': [('207940', '삼성바이오로직스'), ('068270', '셀트리온'), ('000100', '유한양행'), ('128940', '한미약품'), ('185750', '종근당')],
    '방산': [('012450', '한화에어로스페이스'), ('064350', '현대로템'), ('079550', 'LIG넥스원'), ('272210', '한화시스템'), ('103140', '풍산')],
    '자동차': [('005380', '현대차'), ('000270', '기아'), ('012330', '현대모비스'), ('204320', 'HL만도'), ('011210', '현대위아')],
    '금융': [('105560', 'KB금융'), ('055550', '신한지주'), ('086790', '하나금융지주'), ('032830', '삼성생명'), ('000810', '삼성화재')],
    '조선/중공업': [('329180', 'HD현대중공업'), ('010140', '삼성중공업'), ('042660', '한화오션'), ('010620', '현대미포조선'), ('267250', 'HD현대')],
    'AI/플랫폼': [('035420', 'NAVER'), ('035720', '카카오'), ('018260', '삼성SDS'), ('017670', 'SK텔레콤'), ('030200', 'KT')],
    '철강/소재': [('005490', 'POSCO홀딩스'), ('010130', '고려아연'), ('004020', '현대제철'), ('001230', '동국제강'), ('103140', '풍산')],
    '에너지/화학': [('010950', 'S-Oil'), ('015760', '한국전력'), ('078930', 'GS'), ('011170', '롯데케미칼'), ('011780', '금호석유')],
}


def _fetch_theme_list() -> list:
    """네이버 테마 목록 크롤링 — 테마별 no, name, change_rate 반환."""
    res = requests.get(THEME_LIST_URL, headers=_HEADERS, timeout=10)
    res.raise_for_status()
    res.encoding = 'euc-kr'
    soup = BeautifulSoup(res.text, 'html.parser')

    themes = []
    for row in soup.select('table tr'):
        a_tag = row.select_one('td a[href*="no="]')
        if not a_tag:
            continue
        href = a_tag.get('href', '')
        theme_no = href.split('no=')[-1].split('&')[0]
        theme_name = a_tag.text.strip()
        if not theme_name or not theme_no.isdigit():
            continue

        # 등락률: td 중 -30~30 범위 숫자 파싱
        change_rate = 0.0
        for td in row.select('td'):
            text = td.text.strip().replace('%', '').replace('+', '').replace(',', '')
            try:
                val = float(text)
                if -30 < val < 30:
                    change_rate = val
                    break
            except ValueError:
                continue

        themes.append({'no': theme_no, 'name': theme_name, 'change_rate': change_rate})

    if len(themes) < 20:
        raise ValueError(f'테마 파싱 비정상 — {len(themes)}개 (20개 미만)')
    return themes


def _fetch_theme_stocks(theme_no: str) -> list:
    """테마 상세 페이지 크롤링 — 시총 5000억 이상 종목만 최대 5개 반환."""
    res = requests.get(
        THEME_DETAIL_URL, headers=_HEADERS,
        params={'type': 'theme', 'no': theme_no}, timeout=10
    )
    res.raise_for_status()
    res.encoding = 'euc-kr'
    soup = BeautifulSoup(res.text, 'html.parser')

    stocks = []
    for row in soup.select('table tr'):
        a_tag = row.select_one('td a[href*="code="]')
        if not a_tag:
            continue
        code = a_tag['href'].split('code=')[-1].split('&')[0]
        if not code.isdigit() or len(code) != 6:
            continue
        name = a_tag.text.strip()

        # 시총 파싱 — td 중 가장 큰 순수 숫자값 (억원 단위)
        mktcap = 0
        for td in reversed(row.select('td')):
            text = td.text.strip().replace(',', '')
            if text.isdigit() and len(text) >= 4:
                mktcap = int(text)
                break

        if mktcap >= MIN_MKTCAP_BIL:
            stocks.append({'code': code, 'name': name, 'mktcap': mktcap})

    stocks.sort(key=lambda x: -x['mktcap'])
    return [(s['code'], s['name']) for s in stocks[:MAX_STOCKS_PER_THEME]]


def _save_cache(themes: dict):
    os.makedirs('config', exist_ok=True)
    with open(THEME_CACHE, 'w', encoding='utf-8') as f:
        json.dump(
            {'date': datetime.now().strftime('%Y-%m-%d'), 'themes': themes},
            f, ensure_ascii=False, indent=2
        )


def _load_cache() -> dict | None:
    if not os.path.exists(THEME_CACHE):
        return None
    with open(THEME_CACHE, 'r', encoding='utf-8') as f:
        return json.load(f).get('themes')


def _notify(msg: str):
    try:
        from telegram_bot import send_message
        send_message(msg)
    except Exception:
        pass


def get_top_themes(n: int = 12) -> dict:
    """
    3단계 방어로 상위 n개 테마와 종목 반환.
    반환값: {테마명: [(code, name), ...], ...}

    1단계: 네이버 크롤링 (3회 재시도)
    2단계: 어제 캐시
    3단계: 하드코딩 폴백 10개 테마
    """
    global _crawl_source

    # 1단계: 크롤링
    for attempt in range(3):
        try:
            all_themes = _fetch_theme_list()
            candidates = sorted(all_themes, key=lambda x: -x['change_rate'])[:n * 3]
            result = {}
            for t in candidates:
                if len(result) >= n:
                    break
                try:
                    stocks = _fetch_theme_stocks(t['no'])
                    if len(stocks) >= 2:
                        result[t['name']] = stocks
                    time.sleep(0.5)
                except Exception:
                    time.sleep(0.5)

            if len(result) >= max(n // 2, 5):
                _save_cache(result)
                _crawl_source = 'live'
                print(f'[테마] 크롤링 성공 — {len(result)}개 테마')
                return result
        except Exception as e:
            print(f'[테마] 크롤링 시도 {attempt + 1}/3 실패: {e}')
            if attempt < 2:
                time.sleep(2 ** attempt)

    # 2단계: 캐시
    cached = _load_cache()
    if cached:
        _crawl_source = 'cache'
        _notify('⚠️ 테마 크롤링 실패 — 어제 캐시 데이터로 대체합니다.')
        print('[테마] 캐시 사용')
        return cached

    # 3단계: 하드코딩
    _crawl_source = 'fallback'
    _notify('⚠️ 테마 크롤링 + 캐시 모두 실패 — 기본 10개 테마로 대체합니다.')
    print('[테마] 하드코딩 폴백 사용')
    return FALLBACK_THEMES


if __name__ == '__main__':
    themes = get_top_themes(n=12)
    for name, stocks in themes.items():
        print(f'{name}: {[s[1] for s in stocks]}')
