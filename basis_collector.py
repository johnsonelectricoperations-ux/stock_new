# KOSPI 200 베이시스(선물가 - 현물지수) 수집 모듈 (임계값 튜닝용 데이터 축적)
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from kis_data import get_current_price

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://finance.naver.com/',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}


def _front_month_code() -> str:
    """
    KOSPI 200 선물 근월물 KRX 코드 반환.
    형식: 101W + YY + MM (예: 2026년 6월 → 101W2606)
    만기일(매월 둘째 목요일) 당일 이후면 다음 달 코드 반환.
    """
    today = datetime.now().date()

    def second_thu(year, month):
        first = datetime(year, month, 1).date()
        return first + timedelta(days=(3 - first.weekday()) % 7 + 7)

    expiry = second_thu(today.year, today.month)
    if today >= expiry:
        m = today.month % 12 + 1
        y = today.year + (1 if today.month == 12 else 0)
    else:
        y, m = today.year, today.month
    return f'101W{str(y)[2:]}{m:02d}'


def _get_kospi200_spot() -> float | None:
    """KODEX 200(069500) 현재가 × 10 으로 KOSPI 200 지수 근사값 계산."""
    try:
        return get_current_price('069500')['price'] * 10
    except Exception:
        return None


def _get_kospi200_futures() -> float | None:
    """
    네이버 증권 종목 페이지에서 KOSPI 200 근월물 현재가 스크래핑.
    코드 예시: 101W2606 (2026년 6월물)
    """
    code = _front_month_code()
    url = f'https://finance.naver.com/item/main.naver?code={code}'
    try:
        res = requests.get(url, headers=_HEADERS, timeout=10)
        res.raise_for_status()
        res.encoding = 'euc-kr'
        soup = BeautifulSoup(res.text, 'html.parser')

        # 네이버 종목 현재가 영역 — 주식과 동일한 구조
        for selector in ['#_nowVal', 'strong#nowVal', 'p.no_today em']:
            tag = soup.select_one(selector)
            if tag:
                text = tag.get_text(strip=True).replace(',', '')
                try:
                    val = float(text)
                    if val > 50:   # KOSPI 200 선물은 200~500 범위
                        return val
                except ValueError:
                    continue
        return None
    except Exception:
        return None


def get_basis() -> dict | None:
    """
    KOSPI 200 베이시스 계산.
    - 선물 수집 성공: {spot, futures, basis, basis_pct}
    - 선물 수집 실패: {spot, futures=None, basis=None, basis_pct=None}
    - 현물도 실패: None
    basis > 0 → 콘탱고(정상), basis < 0 → 백워데이션(프로그램 매도 압력)
    """
    spot = _get_kospi200_spot()
    if spot is None:
        return None
    futures = _get_kospi200_futures()
    if futures is not None:
        basis = round(futures - spot, 2)
        basis_pct = round(basis / spot * 100, 4)
    else:
        basis = basis_pct = None
    return {
        'spot': spot,
        'futures': futures,
        'basis': basis,
        'basis_pct': basis_pct,
        'futures_code': _front_month_code(),
    }
