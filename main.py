# 자동매매 메인 루프 - 신호 생성, 주문 실행, 리스크 관리 통합
import csv
import os
import time
import schedule
import threading
from datetime import datetime
from kis_data import get_current_price, get_minute_candles
from kis_sector import get_leading_sector_signals
from kis_indicator import check_market_trend
from kis_order import buy_stock, sell_stock, calc_quantity
from telegram_bot import send_message, is_paused, build_app
from config.settings import (
    STOP_LOSS_RATE, TRAIL_STOP_RATE, MAX_STOCK_COUNT, TOTAL_BUDGET,
    BREAK_EVEN_TRIGGER, BREAK_EVEN_FLOOR,
    PARTIAL_SELL_TRIGGER, TIME_STOP_DAYS, TIME_STOP_MIN_RATE,
    EMERGENCY_STOP_RATE, MOMENTUM_EXIT_RATE,
)
from performance import log_trade, add_followup_pending
from error_monitor import setup_logging, log_error, log_info, log_warning

# 보유 종목 저장소: {code: {name, sector, qty, entry_price, entry_date, peak_price}}
positions = {}

# 실현 손익 누적 (복리 재투자 기준금 계산용)
realized_pnl = 0

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
    """실제 매수 가능한 가용 현금 (보유 포지션 투자금 차감)."""
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
    kospi_trend = True
    try:
        kospi_trend = check_market_trend()
        if not kospi_trend:
            send_message('⚠️ KOSPI 하락장 감지 (MA60 하향). 오늘 매수를 보류합니다.')
            log_warning('morning_routine', 'KOSPI 하락장 감지 — 매수 보류')
            return
    except Exception as e:
        log_error('morning_routine:check_market_trend', e)
        send_message(f'⚠️ 시장 추세 확인 실패: {e}. 매수 진행합니다.')

    # 09:20 이후 주문 (장 초반 변동성 진정 후 진입)
    now_time = datetime.now()
    target = now_time.replace(hour=9, minute=10, second=0, microsecond=0)
    wait_seconds = max(0, (target - now_time).total_seconds())
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    _last_heartbeat = time.time()  # 워치독 오경보 방지

    # 신규 매수 가능 슬롯 및 가용 현금 계산
    new_slots = MAX_STOCK_COUNT - len(positions)
    available_cash = get_available_cash()

    if new_slots <= 0:
        send_message(f'포지션이 가득 찼습니다 ({len(positions)}/{MAX_STOCK_COUNT}종목). 매수 보류.')
        return
    if available_cash < 500_000:
        send_message(f'가용 현금 부족 ({available_cash:,}원). 매수 보류.')
        return

    try:
        signals = get_leading_sector_signals(top_sectors=3, max_stocks=new_slots, save_log=True)
    except Exception as e:
        log_error('morning_routine:get_leading_sector_signals', e, critical=True)
        send_message(f'⚠️ 신호 생성 실패: {e}')
        return

    # 이미 보유 중인 종목 제외
    signals = [s for s in signals if s['code'] not in positions]

    if not signals:
        send_message('오늘 매수 신호 없음. 매매 보류.')
        return

    total_signals = len(signals)
    per_stock_budget = available_cash // total_signals
    msg_lines = [
        f'확인 매수 신호 {total_signals}종목 — 눌림목 진입 대기',
        f'가용현금: {available_cash:,}원 | 종목당: {per_stock_budget:,}원',
        f'(총자산: {get_effective_budget():,}원 | 투자중: {get_invested_capital():,}원)'
    ]

    # 09:10~09:30 눌림목 진입 루프 (1분 주기, 전 종목 동시 체크)
    deadline = datetime.now().replace(hour=9, minute=30, second=0, microsecond=0)
    pending = list(signals)  # 아직 매수 안 된 종목

    while pending:
        _last_heartbeat = time.time()  # 워치독 오경보 방지
        still_pending = []
        for s in list(pending):
            code = s['code']
            try:
                if _check_dip_entry(code):
                    msg_lines.append(_execute_buy(
                        s, available_cash, total_signals,
                        kospi_trend=kospi_trend, dip_entry_used=True,
                    ))
                else:
                    still_pending.append(s)
                    log_info('morning_routine', f"{s['name']} 눌림목 조건 미충족 — 다음 분 재확인")
                time.sleep(0.3)
            except Exception as e:
                log_error(f'morning_routine:buy_stock:{code}', e, critical=True)
                s['_attempts'] = s.get('_attempts', 0) + 1
                if s['_attempts'] < 3:
                    still_pending.append(s)  # 1분 뒤 재시도
                    log_info('morning_routine', f"{s['name']} 매수 실패 ({s['_attempts']}회) — 재시도 예정")
                else:
                    msg_lines.append(f"⚠️ {s['name']} 매수 3회 실패, 포기: {e}")

        pending = still_pending
        if pending:
            if datetime.now() >= deadline:
                # 09:30 초과 — 남은 종목 강제 시장가 매수 (최대 3회 시도)
                log_info('morning_routine', f'09:30 초과 — {len(pending)}종목 강제 매수')
                for s in pending:
                    for attempt in range(3):
                        try:
                            msg_lines.append(_execute_buy(
                                s, available_cash, total_signals,
                                kospi_trend=kospi_trend, dip_entry_used=False,
                            ))
                            break
                        except Exception as e:
                            if attempt < 2:
                                log_info('morning_routine',
                                         f"{s['name']} 강제매수 실패({attempt+1}회) — {5}초 후 재시도")
                                time.sleep(5)
                            else:
                                log_error(f'morning_routine:force_buy:{s["code"]}', e, critical=True)
                                msg_lines.append(f"⚠️ {s['name']} 강제 매수 최종 실패: {e}")
                    time.sleep(0.3)
                break
            time.sleep(60)  # 1분 대기 후 재확인

    send_message('\n\n'.join(msg_lines))

def _check_dip_entry(code: str) -> bool:
    """눌림목 진입 조건 확인.
    조건: 현재가 > 직전 1분봉 고가 (상승 전환) AND 현재가 > 최근 5분 종가 평균
    데이터 부족 or API 실패 시 True 반환 (즉시 진입)
    """
    try:
        candles = get_minute_candles(code, count=10)
        if len(candles) < 6:
            return True
        current   = candles[0]['close']
        prev_high = candles[1]['high']
        ma5       = sum(c['close'] for c in candles[1:6]) / 5
        result = current > prev_high and current > ma5
        return result
    except Exception:
        return True  # 조회 실패 시 즉시 진입


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


def _execute_buy(s: dict, available_cash: int, total_signals: int,
                 kospi_trend: bool = True, dip_entry_used: bool = True) -> str:
    """단일 종목 매수 실행. 성공 메시지 또는 에러 메시지 반환."""
    code = s['code']
    info = get_current_price(code)
    qty = calc_quantity(info['price'], total_signals, effective_budget=available_cash)
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
    profit = (price - entry) * qty
    profit_rate = (price - entry) / entry * 100
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
    )
    add_followup_pending(code, pos['name'], exit_date, price, reason)
    log_info('sell', f"{pos['name']}({code}) {reason} {price:,}원 수익률 {profit_rate:+.2f}%")
    send_message(
        f'[매도 체결] {pos["name"]} {price:,}원\n'
        f'사유: {reason} | 수익률: {profit_rate:+.2f}% ({profit:+,}원)\n'
        f'누적 실현손익: {realized_pnl:+,}원'
    )


def monitor_positions():
    global _last_heartbeat
    if not is_market_open():
        return
    if is_paused() or not positions:
        _last_heartbeat = time.time()
        return

    for code in list(positions.keys()):
        try:
            pos = positions[code]
            info = get_current_price(code)
            price = info['price']
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

            # ── 매도 트리거 계산
            stop_loss_price  = entry * (1 - STOP_LOSS_RATE)
            trail_stop_price = peak  * (1 - TRAIL_STOP_RATE)
            floor_price      = pos.get('floor_price', 0)
            sell_trigger     = max(stop_loss_price, trail_stop_price, floor_price)

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
            log_error(f'monitor_positions:{code}', e)

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

    send_message('\n'.join(lines))
    log_info('daily_report', '장 마감 결산 전송 완료')


def _heartbeat_watchdog():
    """스케줄러 스레드가 멈췄는지 30분 주기로 감시 (장 중에만 동작)."""
    WATCHDOG_TIMEOUT = 1800  # 30분
    while True:
        time.sleep(WATCHDOG_TIMEOUT)
        if not is_market_open():
            continue  # 장 외 시간에는 검사하지 않음
        elapsed = time.time() - _last_heartbeat
        if elapsed > WATCHDOG_TIMEOUT:
            log_error('heartbeat_watchdog', critical=True,
                      exc=Exception(f'스케줄러 응답 없음 — {int(elapsed//60)}분 경과'))


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

def main():
    global realized_pnl
    setup_logging()
    realized_pnl = _load_realized_pnl()
    log_info('main', f'시스템 시작. 실현손익={realized_pnl:+,}원')
    send_message(
        f'자동매매 시스템 시작. /help 로 명령어 확인.\n'
        f'누적 실현손익: {realized_pnl:+,}원 | 운용 기준금: {get_effective_budget():,}원'
    )

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    watchdog_thread = threading.Thread(target=_heartbeat_watchdog, daemon=True)
    watchdog_thread.start()

    print('시스템 동작 중... Ctrl+C 로 종료')
    app = build_app()
    app.run_polling(stop_signals=None)

if __name__ == '__main__':
    main()
