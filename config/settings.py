# 환경변수 로드 및 전역 설정값을 관리하는 모듈
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

KIS_APP_KEY = os.getenv('KIS_APP_KEY')
KIS_APP_SECRET = os.getenv('KIS_APP_SECRET')
KIS_ACCOUNT_NO = os.getenv('KIS_ACCOUNT_NO')
KIS_IS_MOCK = os.getenv('KIS_IS_MOCK', 'true').lower() == 'true'

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

KIS_BASE_URL = 'https://openapivts.koreainvestment.com:9443' if KIS_IS_MOCK else 'https://openapi.koreainvestment.com:9443'
