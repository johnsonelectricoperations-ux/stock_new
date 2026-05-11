# 환경변수 로드 및 전역 설정값을 관리하는 모듈
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

KIS_APP_KEY = os.getenv('KIS_APP_KEY')
KIS_APP_SECRET = os.getenv('KIS_APP_SECRET')
KIS_IS_MOCK = os.getenv('KIS_IS_MOCK', 'true').lower() == 'true'

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

KIS_BASE_URL = 'https://openapivts.koreainvestment.com:9443' if KIS_IS_MOCK else 'https://openapi.koreainvestment.com:9443'

_account = os.getenv('KIS_ACCOUNT_NO', '').replace('-', '')
KIS_CANO = _account[:8]
KIS_ACNT_PRDT_CD = _account[8:] if len(_account) > 8 else os.getenv('KIS_ACNT_PRDT_CD', '01')

# 운용 설정
TOTAL_BUDGET = int(os.getenv('TOTAL_BUDGET', '10000000'))
MAX_STOCK_COUNT = int(os.getenv('MAX_STOCK_COUNT', '4'))      # 전체 통과 종목 중 모멘텀 상위 4종목
STOP_LOSS_RATE = float(os.getenv('STOP_LOSS_RATE', '0.10'))
TRAIL_STOP_RATE = float(os.getenv('TRAIL_STOP_RATE', '0.12'))

# 단계별 매도 조건
BREAK_EVEN_TRIGGER = float(os.getenv('BREAK_EVEN_TRIGGER', '0.07'))   # +7% 달성 시 본전 보호 발동
BREAK_EVEN_FLOOR   = float(os.getenv('BREAK_EVEN_FLOOR',   '0.02'))   # 본전 보호 후 스탑 = 진입가 +2%
PARTIAL_SELL_TRIGGER = float(os.getenv('PARTIAL_SELL_TRIGGER', '0.20'))  # +20% 달성 시 50% 부분 익절
TIME_STOP_DAYS     = int(os.getenv('TIME_STOP_DAYS', '20'))            # 시간 손절 기준 거래일
TIME_STOP_MIN_RATE = float(os.getenv('TIME_STOP_MIN_RATE', '0.05'))   # 시간 손절 최소 수익률

# 외국인 5일 누적 순매수 임계값 (백만원 단위, 0 = 순매수면 통과)
FOREIGN_BUY_THRESHOLD = int(os.getenv('FOREIGN_BUY_THRESHOLD', '0'))
