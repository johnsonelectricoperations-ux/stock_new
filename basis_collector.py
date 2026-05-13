# KOSPI 200 베이시스(선물가 - 현물지수) 수집 모듈 (임계값 튜닝용 데이터 축적)
import requests
from bs4 import BeautifulSoup
from kis_data import get_current_price

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://finance.naver.com/',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}

# 네이버 증권 KOSPI 200 선물 시세 페이지
_FUTURES_URL = 'https://finance.naver.com/sise/futureSise.naver?symbol=K2'


def _get_kospi200_spot() -> float | None:
    """KODEX 200(069500) 현재가 × 10 으로 KOSPI 200 지수 근사값 계산."""
    try:
        return get_current_price('069500')['price'] * 10
    except Exception:
        return None


def _get_kospi200_futures() -> float | None:
    """네이버 증권에서 KOSPI 200 선물 근월물 현재가 스크래핑."""
    try:
        res = requests.get(_FUTURES_URL, headers=_HEADERS, timeout=10)
        res.raise_for_status()
        res.encoding = 'euc-kr'
        soup = BeautifulSoup(res.text, 'html.parser')

        # 현재가 — 페이지 상단 종목 현재가 영역
        price_tag = soup.select_one('strong#nowVal')
        if price_tag:
            text = price_tag.get_text(strip=True).replace(',', '')
            return float(text)

        # 폴백: 시세 테이블 첫 번째 행 현재가
        table = soup.select_one('table.type_1')
        if table:
            rows = table.select('tbody tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 2:
                    text = cells[1].get_text(strip=True).replace(',', '')
                    if text:
                        return float(text)
        return None
    except Exception:
        return None


def get_basis() -> dict | None:
    """
    KOSPI 200 베이시스 계산.
    반환: {spot, futures, basis, basis_pct} 또는 None (수집 실패 시)
    basis > 0: 콘탱고(정상), basis < 0: 백워데이션(프로그램 매도 압력)
    """
    spot = _get_kospi200_spot()
    futures = _get_kospi200_futures()
    if spot is None or futures is None:
        return None
    basis = round(futures - spot, 2)
    basis_pct = round(basis / spot * 100, 4)
    return {
        'spot': spot,
        'futures': futures,
        'basis': basis,
        'basis_pct': basis_pct,
    }
