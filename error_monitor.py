# 시스템 에러를 파일에 기록하고 심각 에러를 텔레그램으로 알림하는 모듈
import logging
import traceback
import time
from logging.handlers import RotatingFileHandler
from datetime import datetime

# 에러 유형별 마지막 텔레그램 알림 시각 (스팸 방지)
_last_alert: dict[str, float] = {}
ALERT_COOLDOWN = 1800  # 같은 에러는 30분에 1번만 알림

# 심각 에러로 분류해 즉시 알림할 키워드
_CRITICAL_KEYWORDS = (
    'KIS API', '인증', 'access_token', '매수 실패', '매도 실패',
    'SchedulerError', 'ConnectionError', 'Timeout',
)

logger = logging.getLogger('stock')


def setup_logging():
    """애플리케이션 시작 시 1회 호출. error.log에 회전 저장."""
    logger.setLevel(logging.DEBUG)

    # 파일 핸들러: 1 MB × 5파일 회전
    fh = RotatingFileHandler(
        'error.log', maxBytes=1_000_000, backupCount=5, encoding='utf-8'
    )
    fh.setLevel(logging.WARNING)
    fh.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

    # 콘솔 핸들러: INFO 이상
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S'))

    logger.addHandler(fh)
    logger.addHandler(ch)


def log_error(context: str, exc: Exception | None = None, *, critical: bool = False):
    """에러를 파일에 기록하고, 필요 시 텔레그램으로 알림.

    context: 어느 함수/구간에서 발생했는지 설명
    exc    : 잡힌 예외 객체 (없으면 None)
    critical: True 이면 쿨다운 무시하고 즉시 알림
    """
    tb = traceback.format_exc() if exc else ''
    msg = f'[{context}] {exc}' if exc else f'[{context}]'
    logger.error('%s\n%s', msg, tb.strip())

    # 텔레그램 알림 여부 결정
    is_critical = critical or any(kw in context for kw in _CRITICAL_KEYWORDS)
    if exc:
        is_critical = is_critical or any(kw in str(exc) for kw in _CRITICAL_KEYWORDS)

    key = context.split(':')[0]  # 함수명 기준으로 쿨다운 관리
    now = time.time()
    last = _last_alert.get(key, 0)

    if is_critical or (now - last) >= ALERT_COOLDOWN:
        _last_alert[key] = now
        _send_error_alert(context, exc, is_critical)


def _send_error_alert(context: str, exc: Exception | None, is_critical: bool):
    try:
        from telegram_bot import send_message
        icon = '🚨' if is_critical else '⚠️'
        lines = [
            f'{icon} 시스템 에러 알림',
            f'시각: {datetime.now().strftime("%H:%M:%S")}',
            f'위치: {context}',
        ]
        if exc:
            lines.append(f'내용: {type(exc).__name__}: {str(exc)[:200]}')
        send_message('\n'.join(lines))
    except Exception:
        pass  # 알림 실패는 무시


def log_warning(context: str, msg: str):
    """경고 수준 기록 (텔레그램 알림 없음)."""
    logger.warning('[%s] %s', context, msg)


def log_info(context: str, msg: str):
    logger.info('[%s] %s', context, msg)


def get_recent_errors(n: int = 10) -> str:
    """error.log 마지막 n개 에러 라인 반환 (텔레그램 /errors 명령용)."""
    try:
        lines = []
        with open('error.log', 'r', encoding='utf-8') as f:
            for line in f:
                if '[ERROR]' in line or '[WARNING]' in line:
                    lines.append(line.rstrip())
        if not lines:
            return '기록된 에러 없음.'
        recent = lines[-n:]
        return '\n'.join(recent)
    except FileNotFoundError:
        return '에러 로그 파일 없음 (아직 에러 발생 안 함).'
    except Exception as e:
        return f'로그 조회 실패: {e}'
