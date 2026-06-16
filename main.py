# 자동매매 메인 루프 - 신호 생성, 주문 실행, 리스크 관리 통합
import csv
import os
import sys
import time
import schedule
import threading
from datetime import datetime
from kis_data import get_current_price, get_minute_candles
from kis_sector import get_leading_sector_signals
from kis_indicator import check_market_trend
from kis_order import buy_stock, sell_stock, calc_quantity, InsufficientFundsError
from telegram_bot import send_message, is_paused, build_app
from config.settings import (
    STOP_LOSS_RATE, TRAIL_STOP_RATE, MAX_STOCK_COUNT, TOTAL_BUDGET,
    BREAK_EVEN_TRIGGER, BREAK_EVEN_FLOOR,
    PARTIAL_SELL_TRIGGER, TIME_STOP_DAYS, TIME_STOP_MIN_RATE,
    EMERGENCY_STOP_RATE, MOMENTUM_EXIT_RATE,
    KIS_IS_MOCK, SELL_TAX_RATE, COMMISSION_RATE,
)
from performance import log_trade, add_followup_pending, log_basis, log_timing
from basis_collector import get_basis
from error_monitor import setup_logging, log_error, log_info, log_warning

# 보유 종목 저장소: {code: {name, sector, qty, entry_price, entry_date, peak_price}}
positions = {}

# 실현 손익 누적 (복리 재투자 기준금 계산용)
realized_pnl = 0

# 오전 시장 추세 (비대칭 손절용 — morning_routine에서 갱신)
_kospi_bullish: bool = True

# 스케줄러 마지막 정상 동작 시각 (헬스체크용)
_last_heartbeat: float = 0.0


def _load_realized_pnl() -> int:
    """서버 재시작 시 trades.csv에서 실현 손익 합계 복원."""
    if not os.path.exists('trades.csv'):
        return 0
    total = 0
    with open('trades.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                total += int(row['profit'])
            except Exception:
                pass
    return total


def add_realized_pnl(amount: int):
    global realized_pnl
    realized_pnl += amount


def get_invested_capital() -> int:
    """현재 보유 포지션에 묶인 투자금."""
    return sum(pos['entry_price'] * pos['qty'] for pos in positions.values())


def get_available_cash() -> int:
    """실제 매수 가능한 가용 현금 — KIS 예수금 우선, 실패 시 메모리 계산 폴백."""
    try:
        from kis_balance import get_balance
        bal = get_balance()
        return bal['cash']
    except Exception:
        return max(0, TOTAL_BUDGET + realized_pnl - get_invested_capital())


def get_effective_budget() -> int:
    """총 운용 자산 (초기자금 + 실현손익)."""
    return max(TOTAL_BUDGET + realized_pnl, 1_000_000)


KOREAN_HOLIDAYS_2026 = {
    '20260101', '20260127', '20260128', '20260129', '20260130',
    '20260301', '20260505', '20260506', '20260525',
    '20260606', '20260815', '20260930', '20261001', '20261002',
    '20261003', '20261009', '20261225'
}

def is_trading_day():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    if now.strftime('%Y%m%d') in KOREAN_HOLIDAYS_2026:
        return False
    return True

def is_market_open():
    if not is_trading_day():
        return False
    now = datetime.now()
    market_open  = now.replace(hour=9,  minute=0,  second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close

def morning_routine():
    global _last_heartbeat
    if not is_trading_day():
        return
    if is_paused():
        return

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    send_message(f'[장 시작] {now}\n테마 수집 및 신호 분석 시작합니다...')
    log_info('morning_routine', f'장 시작 루틴 실행 {now}')

    # 코스피 MA60 필터 — 하락장이면 매수 중단
    global _kospi_bullish
    kospi_trend = True
    try:
        kospi_trend = check_market_trend()
        _kospi_bullish = kospi_trend
        if not kospi_trend:
            send_message('⚠️ KOSPI 하락장 감지 (MA60 하향). 오늘 매수를 보류합니다.')
            log_warning('morning_routine', 'KOSPI 하락장 감지 — 매수 보류')
            return
    except Exception as e:
        log_error('morning_routine:check_market_trend', e)
        send_message(f'⚠️ 시장 추세 확인 실패: {e}. 매수 진행합니다.')

    # 09:20 이후 주문 (장 초반 변동성 진정 후 진입)
    now_time = datetime.now()
    target = now_time.replace(hour=9, minute=15, second=0, microsecond=0)
    wait_seconds = max(0, (target - now_time).total_seconds())
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    _last_heartbeat = time.time()  # 워치독 오경보 방지

    # 베이시스 수집 (임계값 튜닝용 데이터 축적, 매매 조건으로는 미사용)
    try:
        basis_data = get_basis()
        if basis_data:
            log_basis(basis_data)
            if basis_data['basis'] is not None:
                slope_str = f" slope {basis_data['basis_slope']:+.4f}" if basis_data.get('basis_slope') is not None else ''
                log_info('morning_routine',
                         f"베이시스 {basis_data['basis']:+.2f}pt "
                         f"(선물 {basis_data['futures']:,.2f} / 현물 {basis_data['spot']:,.0f}){slope_str}")
            else:
                log_warning('morning_routine',
                            f"현물 {basis_data['spot']:,.0f} 기록 완료 — 선물 수집 실패")
        else:
            log_warning('morning_routine', '베이시스 수집 실패 — KODEX 200 조회 불가')
    except Exception as e:
        log_error('morning_routine:basis_collector', e)

    # 신규 매수 가능 슬롯 및 가용 현금 계산
    new_slots = MAX_STOCK_COUNT - len(positions)
    # 시장가 매수 슬리피지·수수료 감안해 가용현금의 95%만 사용
    available_cash = int(get_available_cash() * 0.95)

    if new_slots <= 0:
        send_message(f'포지션이 가득 찼습니다 ({len(positions)}/{MAX_STOCK_COUNT}종목). 매수 보류.')
        return
    if available_cash < 500_000:
        send_message(f'가용 현금 부족 ({available_cash:,}원). 매수 보류.')
        return

    try:
        # 차선 후보(reserve_count)도 함께 받아 고가주로 슬롯이 비면 대체 매수
        signals = get_leading_sector_signals(top_sectors=5, max_stocks=new_slots,
                                             save_log=True, reserve_count=new_slots)
    except Exception as e:
        log_error('morning_routine:get_leading_sector_signals', e, critical=True)
        send_message(f'⚠️ 신호 생성 실패: {e}')
        return

    # 본선/차선 분리 후 이미 보유 중인 종목 제외
    primary  = [s for s in signals if not s.get('is_reserve') and s['code'] not in positions]
    reserves = [s for s in signals if s.get('is_reserve') and s['code'] not in positions]

    if not primary:
        send_message('오늘 매수 신호 없음. 매매 보류.')
        return

    # 종목당 예산 배분 기준은 본선 종목 수 고정 — 차선 대체 시에도 같은 슬롯 예산 유지
    total_signals = len(primary)
    per_stock_budget = available_cash // total_signals
    msg_lines = [
        f'확인 매수 신호 {total_signals}종목 — 눌림목 진입 대기 (차선 후보 {len(reserves)}종목 대기)',
        f'가용현금: {available_cash:,}원 | 종목당: {per_stock_budget:,}원',
        f'(총자산: {get_effective_budget():,}원 | 투자중: {get_invested_capital():,}원)'
    ]

    # 09:15~10:00 분봉 조건부 진입 루프
    # - 09:15~09:30: 눌림목 조건 (현재가 > 직전 1분봉 고가 AND > 5분 MA)
    # - 09:30~10:00: 완화 조건 (현재가 > 5분 MA만 확인, 고가 돌파 제외)
    # - 10:00 도달: 조건 미충족 종목 매수 포기 (강제 매수 없음)
    strict_deadline   = datetime.now().replace(hour=9,  minute=30, second=0, microsecond=0)
    extended_deadline = datetime.now().replace(hour=10, minute=0,  second=0, microsecond=0)
    pending = list(primary)

    while pending:
        _last_heartbeat = time.time()
        now = datetime.now()

        if now >= extended_deadline:
            # 10:00 초과 — 조건 미충족 종목 매수 포기
            for s in pending:
                log_timing(s['code'], s['name'], False, 'skipped_timeout')
                msg_lines.append(f"⏱ {s['name']} 10:00까지 진입 조건 미충족 — 오늘 매수 포기")
            break

        relaxed = now >= strict_deadline  # 09:30 이후면 완화 조건 사용
        still_pending = []

        for s in list(pending):
            code = s['code']
            try:
                dip_met = _check_dip_entry(code, relaxed=relaxed)
                if dip_met:
                    msg_lines.append(_execute_buy(
                        s, available_cash, total_signals,
                        kospi_trend=kospi_trend, dip_entry_used=not relaxed,
                    ))
                    action = 'bought_reserve' if s.get('is_reserve') else (
                        'bought_relaxed' if relaxed else 'bought_dip')
                    log_timing(code, s['name'], True, action)
                else:
                    still_pending.append(s)
                    log_timing(code, s['name'], False, 'waiting')
                    log_info('morning_routine',
                             f"{s['name']} {'완화' if relaxed else '눌림목'} 조건 미충족 — 다음 분 재확인")
                time.sleep(0.3)
            except (InsufficientBudgetError, InsufficientFundsError) as e:
                # 고가주(1주>슬롯예산) 또는 증권사 주문가능금액 부족 — 시스템 오류 아님.
                # 🚨·재시도 없이 차선 후보로 슬롯 대체 (차선도 없으면 슬롯 미사용).
                reason = '자금부족' if isinstance(e, InsufficientFundsError) else '고가'
                log_timing(code, s['name'], False, 'skipped_unaffordable')
                log_info('morning_routine', f"{s['name']} {reason} 스킵 — {e}")
                msg_lines.append(f"⏭ {s['name']} {reason} 스킵 — {e}")
                if reserves:
                    r = reserves.pop(0)
                    still_pending.append(r)  # 다음 분 사이클에서 눌림목 조건 확인 후 매수
                    msg_lines.append(f"↪ 차선 후보 전환: {r['name']}({r['code']}) 모멘텀 {r['momentum']:+.2f}%")
                    log_info('morning_routine', f"차선 후보 전환 투입: {r['name']}({r['code']})")
                else:
                    msg_lines.append(f"   (차선 후보 소진 — {s['name']} 슬롯 미사용)")
                time.sleep(0.3)
            except Exception as e:
                log_error(f'morning_routine:buy_stock:{code}', e, critical=True)
                # 주문 접수 후 예외 가능성(유령 포지션) — 잔고에서 실제 체결 여부 확인
                if _verify_filled_position(s, kospi_trend=kospi_trend, dip_entry_used=not relaxed):
                    log_timing(code, s['name'], True, 'bought_verified')
                    msg_lines.append(
                        f"[매수 체결 확인] {s['name']} — 주문 중 오류 발생했으나 잔고에서 체결 확인됨"
                    )
                    time.sleep(0.3)
                    continue
                log_timing(code, s['name'], True, 'buy_failed')
                s['_attempts'] = s.get('_attempts', 0) + 1
                if s['_attempts'] < 3:
                    still_pending.append(s)
                    log_info('morning_routine',
                             f"{s['name']} 매수 실패 ({s['_attempts']}회) — 재시도 예정")
                else:
                    msg_lines.append(f"⚠️ {s['name']} 매수 3회 실패, 포기: {e}")

        pending = still_pending
        if pending:
            time.sleep(60)

    send_message('\n\n'.join(msg_lines))

def _verify_filled_position(s: dict, kospi_trend: bool, dip_entry_used: bool) -> bool:
    """매수 주문 예외 발생 시 잔고를 조회해 실제 체결 여부 확인.
    체결됐으면 신호 메타데이터를 보존한 채 포지션 등록 (유령 포지션 방지).
    """
    code = s['code']
    try:
        from kis_balance import get_balance
        bal = get_balance()
    except Exception:
        return False
    for b in bal['stocks']:
        if b['code'] == code and b['qty'] > 0:
            now = datetime.now()
            positions[code] = {
                'name': s['name'],
                'sector': s['sector'],
                'qty': b['qty'],
                'entry_price': b['avg_price'],
                'entry_date': now.strftime('%Y-%m-%d'),
                'entry_time': now.strftime('%H:%M:%S'),
                'peak_price': b['avg_price'],
                'min_price': b['avg_price'],
                'break_even_set': False,
                'floor_price': 0,
                'partial_sold': False,
                'momentum': s.get('momentum'),
                'foreign_net_buy_mil': s.get('foreign_net_buy_mil'),
                'ma20_at_entry': s.get('ma20'),
                'ma60_at_entry': s.get('ma60'),
                'volume_ratio': s.get('volume_ratio'),
                'kospi_trend': kospi_trend,
                'dip_entry_used': dip_entry_used,
                'atr': s.get('atr'),
                'bb_pct_at_entry': s.get('bb_pct'),
                'avg_tr_pbmn_mil': s.get('avg_tr_pbmn_mil'),
            }
            log_info('morning_routine',
                     f"매수 체결 잔고 확인: {s['name']}({code}) {b['avg_price']:,}원 × {b['qty']}주")
            return True
    return False


def _check_dip_entry(code: str, relaxed: bool = False) -> bool:
    """분봉 진입 조건 확인.
    - 일반(09:30 이전): 현재가 > 직전 1분봉 고가 AND > 5분 MA (눌림목 돌파)
    - 완화(09:30 이후): 현재가 > 5분 MA만 확인 (고가 돌파 조건 제외)
    데이터 부족 or API 실패 시 True 반환 (즉시 진입)
    """
    try:
        candles = get_minute_candles(code, count=10)
        if len(candles) < 6:
            return True
        current   = candles[0]['close']
        prev_high = candles[1]['high']
        ma5       = sum(c['close'] for c in candles[1:6]) / 5
        if relaxed:
            return current > ma5          # 09:30 이후: MA5 위에 있으면 진입
        return current > prev_high and current > ma5
    except Exception:
        return True


def _get_candle_sell_info(code: str) -> dict | None:
    """매도 판단용 1분봉 정보. 실패 시 None 반환 (None이면 현재가 기준으로 폴백)."""
    try:
        candles = get_minute_candles(code, count=10)
        if len(candles) < 6:
            return None
        return {
            'prev_close': candles[1]['close'],                          # 직전 완성봉 종가
            'prev_low':   candles[1]['low'],                            # 직전 완성봉 저가
            'ma5':        sum(c['close'] for c in candles[1:6]) / 5,   # 5분 MA
        }
    except Exception:
        return None


class InsufficientBudgetError(Exception):
    """종목당 배분 예산으로 1주도 살 수 없는 고가주 — 시스템 오류가 아닌 정상 스킵 사유."""


def _execute_buy(s: dict, available_cash: int, total_signals: int,
                 kospi_trend: bool = True, dip_entry_used: bool = True) -> str:
    """단일 종목 매수 실행. 성공 메시지 또는 에러 메시지 반환."""
    code = s['code']
    info = get_current_price(code)
    price = info['price']
    qty = calc_quantity(price, total_signals, effective_budget=available_cash)
    # 증권사 실제 주문가능금액으로 상한 (예수금≠주문가능, T+2 미결제 거부 방지). 조회 실패 시 미적용.
    try:
        from kis_balance import get_orderable_cash
        orderable = get_orderable_cash(code, price)
        if orderable is not None and orderable < price * qty:
            qty = orderable // price
    except Exception:
        pass
    if qty <= 0:
        raise InsufficientBudgetError(
            f"종목당 {available_cash // total_signals:,}원으로 {price:,}원짜리 1주 매수 불가"
        )
    buy_stock(code, qty)
    now = datetime.now()
    positions[code] = {
        'name': s['name'],
        'sector': s['sector'],
        'qty': qty,
        'entry_price': info['price'],
        'entry_date': now.strftime('%Y-%m-%d'),
        'entry_time': now.strftime('%H:%M:%S'),
        'peak_price': info['price'],
        'min_price': info['price'],
        'break_even_set': False,
        'floor_price': 0,
        'partial_sold': False,
        'momentum': s.get('momentum'),
        'foreign_net_buy_mil': s.get('foreign_net_buy_mil'),
        'ma20_at_entry': s.get('ma20'),
        'ma60_at_entry': s.get('ma60'),
        'volume_ratio': s.get('volume_ratio'),
        'kospi_trend': kospi_trend,
        'dip_entry_used': dip_entry_used,
        'atr': s.get('atr'),
        'bb_pct_at_entry': s.get('bb_pct'),
        'avg_tr_pbmn_mil': s.get('avg_tr_pbmn_mil'),
    }
    log_info('morning_routine', f"매수 체결: {s['name']}({code}) {info['price']:,}원 × {qty}주")
    return (
        f"[매수 체결] {s['name']} {info['price']:,}원 × {qty}주"
        f"\n테마: {s['sector']} | 모멘텀: {s['momentum']:+.2f}%"
    )


def _trading_days_held(entry_date_str: str) -> int:
    """진입일 기준 경과 거래일 수 (달력일 × 5/7 근사)."""
    try:
        entry = datetime.strptime(entry_date_str, '%Y-%m-%d')
        delta = (datetime.now() - entry).days
        return max(0, int(delta * 5 / 7))
    except Exception:
        return 0


def _do_sell(code: str, qty: int, price: int, reason: str, trigger_price: int = None):
    """매도 실행 + PnL/로그/텔레그램 처리."""
    pos = positions[code]
    entry = pos['entry_price']
    gross_profit = (price - entry) * qty
    # 실전 거래 비용 반영 (모의투자는 체결가 그대로이므로 미적용)
    if not KIS_IS_MOCK:
        cost = (entry * qty * COMMISSION_RATE
                + price * qty * (COMMISSION_RATE + SELL_TAX_RATE))
        profit = int(gross_profit - cost)
    else:
        profit = gross_profit
    profit_rate = profit / (entry * qty) * 100
    sell_stock(code, qty)
    add_realized_pnl(profit)
    now = datetime.now()
    exit_date = now.strftime('%Y-%m-%d')
    log_trade(
        code=code, name=pos['name'],
        sector=pos.get('sector', ''),
        entry_date=pos.get('entry_date', exit_date),
        entry_time=pos.get('entry_time', ''),
        entry_price=entry, exit_price=price,
        qty=qty, reason=reason,
        peak_price=pos.get('peak_price'),
        min_price=pos.get('min_price'),
        trigger_price=trigger_price,
        momentum=pos.get('momentum'),
        foreign_net_buy_mil=pos.get('foreign_net_buy_mil'),
        ma20_at_entry=pos.get('ma20_at_entry'),
        ma60_at_entry=pos.get('ma60_at_entry'),
        volume_ratio=pos.get('volume_ratio'),
        kospi_trend=pos.get('kospi_trend'),
        dip_entry_used=pos.get('dip_entry_used'),
        atr_at_entry=pos.get('atr'),
        bb_pct_at_entry=pos.get('bb_pct_at_entry'),
        avg_tr_pbmn_mil=pos.get('avg_tr_pbmn_mil'),
    )
    add_followup_pending(code, pos['name'], exit_date, price, reason)
    log_info('sell', f"{pos['name']}({code}) {reason} {price:,}원 수익률 {profit_rate:+.2f}%")
    send_message(
        f'[매도 체결] {pos["name"]} {price:,}원\n'
        f'사유: {reason} | 수익률: {profit_rate:+.2f}% ({profit:+,}원)\n'
        f'누적 실현손익: {realized_pnl:+,}원'
    )


_monitor_fail_streak = 0  # 모니터링 사이클 전체 실패(시세조회 불능) 연속 횟수
_pos_fail_streak: dict = {}  # 종목별 연속 시세조회 실패 횟수 (단발성 타임아웃 알림 억제용)
_POS_FAIL_ALERT = 3  # 한 종목이 연속 3회(약 6분) 실패하면 알림 — 그 전엔 파일 기록만


def monitor_positions():
    global _last_heartbeat, _monitor_fail_streak
    if not is_market_open():
        return
    if is_paused() or not positions:
        _monitor_fail_streak = 0
        _last_heartbeat = time.time()
        return

    cycle_fail_count = 0
    cycle_total = len(positions)
    for code in list(positions.keys()):
        try:
            pos = positions[code]
            info = get_current_price(code)
            price = info['price']
            _pos_fail_streak.pop(code, None)  # 조회 성공 — 실패 카운트 리셋
            entry = pos['entry_price']
            rate  = (price - entry) / entry

            # 고점/저점 갱신
            if price > pos['peak_price']:
                positions[code]['peak_price'] = price
            if price < pos.get('min_price', price):
                positions[code]['min_price'] = price
            peak = positions[code]['peak_price']

            # ── 긴급 손절: -15% 이상 → 캔들 확인 없이 즉시 매도
            if rate <= -EMERGENCY_STOP_RATE:
                _do_sell(code, pos['qty'], price, f'긴급손절({rate*100:+.1f}%)',
                         trigger_price=int(entry * (1 - EMERGENCY_STOP_RATE)))
                del positions[code]
                time.sleep(0.3)
                continue

            # ── 1분봉 정보 조회 (없으면 현재가로 폴백)
            candle = _get_candle_sell_info(code)
            prev_close = candle['prev_close'] if candle else price
            prev_low   = candle['prev_low']   if candle else price
            ma5        = candle['ma5']         if candle else price

            # ── 모멘텀 약화 조기 익절: +10% 이상 + 1분봉 하락 전환
            if rate >= MOMENTUM_EXIT_RATE and price < prev_low and price < ma5:
                _do_sell(code, pos['qty'], price, f'모멘텀약화({rate*100:+.1f}%)')
                del positions[code]
                time.sleep(0.3)
                continue

            # ── 부분 익절: +20% → 50% 매도 (1회)
            if not pos.get('partial_sold') and rate >= PARTIAL_SELL_TRIGGER:
                half_qty = max(1, pos['qty'] // 2)
                _do_sell(code, half_qty, price, f'부분익절(+{rate*100:.1f}%)')
                positions[code]['qty'] -= half_qty
                positions[code]['partial_sold'] = True
                positions[code]['peak_price'] = price
                if positions[code]['qty'] <= 0:
                    del positions[code]
                time.sleep(0.3)
                continue

            # ── 본전 보호 스탑 발동
            if not pos.get('break_even_set') and rate >= BREAK_EVEN_TRIGGER:
                positions[code]['break_even_set'] = True
                positions[code]['floor_price'] = entry * (1 + BREAK_EVEN_FLOOR)

            # ── 매도 트리거 계산 (비대칭 손절: 하락장 국면이면 손절 폭 타이트하게)
            effective_stop_rate = STOP_LOSS_RATE * 0.6 if not _kospi_bullish else STOP_LOSS_RATE
            stop_loss_price  = entry * (1 - effective_stop_rate)

            # ATR 기반 동적 트레일링: +7% 이상 구간에서 peak - 1.5*ATR 적용
            # 변동성 작은 종목은 짧게, 주도주(변동성 큰 종목)는 길게 가져가는 효과
            atr = pos.get('atr')
            if atr and rate >= BREAK_EVEN_TRIGGER:
                atr_trail = peak - 1.5 * atr
                fixed_trail = peak * (1 - TRAIL_STOP_RATE)
                trail_stop_price = max(atr_trail, fixed_trail)  # 둘 중 높은 쪽(더 타이트한 쪽)
            else:
                trail_stop_price = peak * (1 - TRAIL_STOP_RATE)

            floor_price  = pos.get('floor_price', 0)
            sell_trigger = max(stop_loss_price, trail_stop_price, floor_price)

            # ── 시간 손절
            days_held = _trading_days_held(pos.get('entry_date', ''))
            time_stop = days_held >= TIME_STOP_DAYS and rate < TIME_STOP_MIN_RATE

            # ── 캔들 종가 확인 매도 (whipsaw 방지)
            candle_confirmed = prev_close <= sell_trigger

            if candle_confirmed or time_stop:
                if time_stop and not candle_confirmed:
                    reason = f'시간손절({days_held}거래일, {rate*100:+.1f}%)'
                    trig = None
                elif prev_close <= stop_loss_price:
                    reason = '손절(캔들확인)'
                    trig = int(stop_loss_price)
                elif floor_price and prev_close <= floor_price:
                    reason = '본전보호(캔들확인)'
                    trig = int(floor_price)
                else:
                    reason = '트레일링스탑(캔들확인)'
                    trig = int(trail_stop_price)
                _do_sell(code, pos['qty'], price, reason, trigger_price=trig)
                del positions[code]

            time.sleep(0.3)
        except Exception as e:
            cycle_fail_count += 1
            n = _pos_fail_streak.get(code, 0) + 1
            _pos_fail_streak[code] = n
            # 단발성 타임아웃은 다음 2분 사이클에서 재조회되므로 파일 기록만.
            # 연속 N회(약 6분) 실패한 종목만 알림 — 그 종목이 사실상 미감시 상태이므로.
            if n >= _POS_FAIL_ALERT:
                log_error(f'monitor_positions:{code}', e)
            else:
                log_warning('monitor_positions',
                            f'{code} {type(e).__name__} (연속 {n}회) — 파일기록만, 다음 사이클 재조회')

    # 사라진 종목(매도 완료)의 실패 카운트 정리
    for c in list(_pos_fail_streak):
        if c not in positions:
            del _pos_fail_streak[c]

    # API 장애 연속 감지: 전 종목 조회 실패가 이어지면 손절 모니터링 마비 상태 → 긴급 알림
    # (2분 주기 × 5회 = 약 10분 지속 시 1차 경보, 이후 30분마다 재경보)
    if cycle_total > 0 and cycle_fail_count >= cycle_total:
        _monitor_fail_streak += 1
        if _monitor_fail_streak == 5 or (_monitor_fail_streak > 5 and _monitor_fail_streak % 15 == 0):
            log_error(
                'monitor_positions',
                Exception(f'시세 조회 연속 {_monitor_fail_streak}회({_monitor_fail_streak*2}분) 전체 실패 — '
                          f'보유 {cycle_total}종목 손절 모니터링 마비 상태'),
                critical=True,
            )
    else:
        _monitor_fail_streak = 0

    _last_heartbeat = time.time()


def followup_checker():
    """매도 이후 사후 추적 가격 기록 — 매일 15:35 실행."""
    if not is_trading_day():
        return
    from performance import get_followup_due, record_followup_price
    today_str = datetime.now().strftime('%Y-%m-%d')
    due = get_followup_due(today_str)
    if not due:
        return
    for item, day_key in due:
        try:
            info = get_current_price(item['code'])
            record_followup_price(item['code'], item['exit_date'], day_key, info['price'])
            log_info('followup_checker',
                     f"{item['name']} {day_key} 추적 완료: {info['price']:,}원")
        except Exception as e:
            log_error(f"followup_checker:{item['code']}", e)


def daily_report():
    if not is_trading_day():
        return

    total_unrealized = 0
    lines = [f'장 마감 결산 ({datetime.now().strftime("%Y-%m-%d")})']

    # 보유 종목 현황
    if positions:
        lines.append('\n[보유 종목]')
        for code, pos in positions.items():
            try:
                info = get_current_price(code)
                profit = (info['price'] - pos['entry_price']) * pos['qty']
                rate   = (info['price'] - pos['entry_price']) / pos['entry_price'] * 100
                total_unrealized += profit
                lines.append(f"  {pos['name']}: {rate:+.2f}% ({profit:+,}원)")
            except Exception as e:
                log_error(f'daily_report:get_current_price:{code}', e)
                lines.append(f"  {pos['name']}: 조회 실패")
        lines.append(f'  미실현 손익 합계: {total_unrealized:+,}원')
    else:
        lines.append('\n보유 종목 없음.')

    # 자산 현황
    invested = get_invested_capital()
    available = get_available_cash()
    total_asset = get_effective_budget()
    lines.append(
        f'\n[자산 현황]\n'
        f'  총 운용자산: {total_asset:,}원\n'
        f'  투자 중: {invested:,}원\n'
        f'  가용 현금: {available:,}원\n'
        f'  누적 실현손익: {realized_pnl:+,}원'
    )

    # 내일 매수 계획
    new_slots = MAX_STOCK_COUNT - len(positions)
    if new_slots > 0 and available >= 500_000:
        per_stock = available // new_slots
        lines.append(
            f'\n[내일 매수 계획]\n'
            f'  신규 매수 가능: {new_slots}종목\n'
            f'  종목당 투자금: {per_stock:,}원\n'
            f'  (가용현금 {available:,}원 ÷ {new_slots}종목)'
        )
    elif new_slots <= 0:
        lines.append(f'\n[내일 매수 계획]\n  포지션 가득 ({MAX_STOCK_COUNT}/{MAX_STOCK_COUNT}). 신규 매수 없음.')
    else:
        lines.append(f'\n[내일 매수 계획]\n  가용 현금 부족 ({available:,}원). 신규 매수 보류.')

    # 오늘 시스템 동작 검증
    lines.append('\n' + _build_daily_check())

    # 실전 전환 조건 점검
    transition_msg = _check_real_trading_ready()
    if transition_msg:
        lines.append('\n' + transition_msg)

    send_message('\n'.join(lines))
    log_info('daily_report', '장 마감 결산 전송 완료')


def _check_real_trading_ready() -> str | None:
    """실전 전환 4가지 조건 모두 충족 시 안내 문구 반환, 미충족 시 None."""
    import csv as _csv
    results = []

    # 1. 거래 30건 이상
    try:
        with open('trades.csv', 'r', encoding='utf-8') as f:
            total = sum(1 for _ in _csv.DictReader(f))
        results.append(('거래 건수', total >= 30, f'{total}건'))
    except FileNotFoundError:
        results.append(('거래 건수', False, '0건'))

    # 2. 승률 45% 이상 + 손익비 1.5 이상
    try:
        with open('trades.csv', 'r', encoding='utf-8') as f:
            trades = list(_csv.DictReader(f))
        profits = [float(t['profit_rate']) for t in trades]
        wins    = [p for p in profits if p > 0]
        losses  = [p for p in profits if p <= 0]
        win_rate = len(wins) / len(profits) * 100 if profits else 0
        avg_win  = sum(wins) / len(wins) if wins else 0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 1
        pl_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        results.append(('승률', win_rate >= 45, f'{win_rate:.0f}%'))
        results.append(('손익비', pl_ratio >= 1.5, f'{pl_ratio:.2f}'))
    except FileNotFoundError:
        results.append(('승률', False, '0%'))
        results.append(('손익비', False, '0'))

    # 3. 최근 14일 에러 없음
    try:
        from error_monitor import get_recent_errors
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
        err_text = get_recent_errors(50)
        recent_errors = [line for line in err_text.splitlines()
                         if line.strip() and line[:10] >= cutoff and line[:4].isdigit()]
        results.append(('2주 안정 운영', len(recent_errors) == 0, f'에러 {len(recent_errors)}건'))
    except Exception:
        results.append(('2주 안정 운영', False, '확인 불가'))

    if all(ok for _, ok, _ in results):
        detail = ' | '.join(f'{name} {val}' for name, _, val in results)
        return f'🎉 실전 전환 조건 모두 충족 ({detail})\n이제 실전 거래로 전환해보시겠어요?'

    return None


def _build_daily_check() -> str:
    """오늘 시스템 동작 검증 요약 — daily_report 및 /check 명령 공용."""
    today = datetime.now().strftime('%Y-%m-%d')
    items = []

    # 1. 베이시스 / VKOSPI 수집
    try:
        with open('basis_log.csv', 'r', encoding='utf-8') as f:
            rows = [r for r in csv.DictReader(f) if r.get('date') == today]
        if rows:
            r = rows[-1]
            basis_ok  = '✅' if r.get('basis') else '⚠️ 선물 없음'
            vkospi_ok = f'✅ {float(r["vkospi"]):.2f}' if r.get('vkospi') else '⚠️ 장 중 미수집'
            items.append(f'베이시스 수집: {basis_ok} | VKOSPI: {vkospi_ok}')
        else:
            items.append('베이시스 수집: ❌ 오늘 기록 없음')
    except FileNotFoundError:
        items.append('베이시스 수집: ❌ basis_log.csv 없음')

    # 2. 신호 스캔 (signal_log)
    try:
        with open('signal_log.csv', 'r', encoding='utf-8') as f:
            rows = [r for r in csv.DictReader(f) if r.get('date') == today]
        if rows:
            has_bb  = any(r.get('bb_pct') for r in rows)
            has_atr = any(r.get('atr') for r in rows)
            selected = sum(1 for r in rows if r.get('selected') == 'True')
            passed   = sum(1 for r in rows if r.get('passed_all_filters') == 'True')
            items.append(
                f'신호 스캔: ✅ {len(rows)}종목 분석 | 필터통과 {passed} | 선정 {selected} | '
                f'BB%B {"✅" if has_bb else "❌"} | ATR {"✅" if has_atr else "❌"}'
            )
        else:
            items.append('신호 스캔: ❌ 오늘 기록 없음 (매수 신호 없거나 하락장 중단)')
    except FileNotFoundError:
        items.append('신호 스캔: ❌ signal_log.csv 없음')

    # 3. 오늘 거래 (trades)
    try:
        with open('trades.csv', 'r', encoding='utf-8') as f:
            trades = [r for r in csv.DictReader(f) if r.get('exit_date') == today]
        if trades:
            total_profit = sum(int(t['profit']) for t in trades)
            items.append(f'오늘 거래: {len(trades)}건 완료 | 손익 {total_profit:+,}원')
        else:
            items.append('오늘 거래: 없음')
    except FileNotFoundError:
        items.append('오늘 거래: 없음')

    # 4. 에러 현황
    try:
        from error_monitor import get_recent_errors
        err_text = get_recent_errors(5)
        today_errors = err_text.count(today)
        items.append(f'오늘 에러: {"⚠️ " + str(today_errors) + "건" if today_errors else "✅ 없음"}')
    except Exception:
        items.append('에러 현황: 확인 불가')

    # 5. 네이버 테마 크롤링 상태
    try:
        from naver_theme import get_crawl_source
        src = get_crawl_source()
        label = {'live': '✅ 정상 크롤링', 'cache': '⚠️ 캐시 사용 (크롤링 실패)', 'fallback': '❌ 하드코딩 폴백 (크롤링+캐시 모두 실패)'}.get(src, '— 오늘 미실행')
        items.append(f'테마 크롤링: {label}')
    except Exception:
        items.append('테마 크롤링: 확인 불가')

    return '[오늘 시스템 검증]\n' + '\n'.join(f'  {i}' for i in items)


def _heartbeat_watchdog():
    """스케줄러 스레드가 멈췄는지 30분 주기로 감시 (장 중에만 동작)."""
    WATCHDOG_TIMEOUT = 5400  # 90분 (08:00 스캔 시작 → 09:15 진입까지 75분 소요)
    while True:
        time.sleep(WATCHDOG_TIMEOUT)
        if not is_market_open():
            continue  # 장 외 시간에는 검사하지 않음
        elapsed = time.time() - _last_heartbeat
        if elapsed > WATCHDOG_TIMEOUT:
            log_error('heartbeat_watchdog', critical=True,
                      exc=Exception(f'스케줄러 응답 없음 — {int(elapsed//60)}분 경과'))


def _run_dashboard():
    """Flask 대시보드를 별도 스레드에서 실행."""
    try:
        from dashboard import app
        import logging as _logging
        _logging.getLogger('werkzeug').setLevel(_logging.ERROR)
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    except Exception as e:
        log_error('dashboard', e)


def run_scheduler():
    global _last_heartbeat
    _last_heartbeat = time.time()
    schedule.every().day.at('08:00').do(morning_routine)
    schedule.every(2).minutes.do(monitor_positions)
    schedule.every().day.at('15:35').do(followup_checker)
    schedule.every().day.at('15:35').do(daily_report)
    while True:
        try:
            schedule.run_pending()
            _last_heartbeat = time.time()  # 스케줄러 정상 동작 확인
        except Exception as e:
            log_error('run_scheduler', e, critical=True)
        time.sleep(30)

def _restore_positions_from_balance():
    """시작 시 KIS 잔고 조회로 보유 종목 자동 복구."""
    try:
        from kis_balance import get_balance
        bal = get_balance()
        for s in bal['stocks']:
            code = s['code']
            if code in positions:
                continue
            positions[code] = {
                'name': s['name'], 'sector': '', 'qty': s['qty'],
                'entry_price': s['avg_price'],
                'entry_date': datetime.now().strftime('%Y-%m-%d'),
                'entry_time': '',
                'peak_price': s['avg_price'],
                'min_price': s['avg_price'],
                'break_even_set': False, 'floor_price': 0, 'partial_sold': False,
            }
        if positions:
            names = ', '.join(p['name'] for p in positions.values())
            log_info('main', f'잔고 자동 복구: {names}')
            return f'보유 종목 자동 복구: {names}'
        return None
    except Exception as e:
        log_error('restore_positions', e)
        return None


def main():
    global realized_pnl
    setup_logging()
    realized_pnl = _load_realized_pnl()
    restored = _restore_positions_from_balance()
    log_info('main', f'시스템 시작. 실현손익={realized_pnl:+,}원')
    msg = (
        f'자동매매 시스템 시작. /help 로 명령어 확인.\n'
        f'누적 실현손익: {realized_pnl:+,}원 | 운용 기준금: {get_effective_budget():,}원'
    )
    if restored:
        msg += f'\n{restored}'
    send_message(msg)

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    watchdog_thread = threading.Thread(target=_heartbeat_watchdog, daemon=True)
    watchdog_thread.start()

    dashboard_thread = threading.Thread(target=_run_dashboard, daemon=True)
    dashboard_thread.start()

    print('시스템 동작 중... Ctrl+C 로 종료')
    app = build_app()
    app.run_polling(stop_signals=None)

if __name__ == '__main__':
    # telegram_bot.py의 'from main import positions' 가
    # __main__ 모듈과 동일한 객체를 참조하도록 등록
    sys.modules['main'] = sys.modules['__main__']
    main()
