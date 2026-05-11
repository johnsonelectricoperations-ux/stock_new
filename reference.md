# 주식 자동매매 시스템 — 빠른 참조

## 주요 사이트

| 서비스 | 주소 |
|--------|------|
| AWS 콘솔 (서버 관리) | https://console.aws.amazon.com |
| 한국투자증권 KIS Developers | https://apiportal.koreainvestment.com |
| GitHub 저장소 | https://github.com/johnsonelectricoperations-ux/stock_new |

---

## 서버 접속 방법 (PowerShell)

PowerShell을 열고 아래 명령어 입력.

```powershell
ssh -i "C:\project_list\stock_auto\key\AWS\stock-bot.pem" ubuntu@서버IP주소
```

- **서버 IP 확인**: AWS 콘솔 → EC2 → 인스턴스 → 퍼블릭 IPv4 주소
- 접속 후 프롬프트가 `ubuntu@ip-...` 로 바뀌면 접속 성공.

---

## 서버 접속 후 상태 확인

```bash
# 봇 실행 상태 확인
sudo systemctl status stock-bot

# 실시간 로그 확인 (Ctrl+C로 종료)
sudo journalctl -u stock-bot -f

# 오늘 로그만 확인
sudo journalctl -u stock-bot --since today
```

---

## 프로그램 제어

```bash
# 봇 중지
sudo systemctl stop stock-bot

# 봇 시작
sudo systemctl start stock-bot

# 봇 재시작
sudo systemctl restart stock-bot

# 서버 부팅 시 자동시작 활성화 확인
sudo systemctl is-enabled stock-bot
```

---

## GitHub에서 최신 코드 서버에 반영

서버에 접속한 후 아래 명령어 입력.

```bash
cd ~/stock_auto
git fetch origin claude/file-modifications-main-ykk5n
git reset --hard origin/claude/file-modifications-main-ykk5n
sudo systemctl restart stock-bot
```

---

## 텔레그램 봇 명령어 요약

| 명령어 | 기능 |
|--------|------|
| `/status` | 보유 종목 및 수익률 확인 |
| `/balance` | 투자 현황 (현금 + 평가금액) |
| `/signal` | 오늘 매수 신호 종목 조회 |
| `/buy 종목코드 수량` | 즉시 매수 (예: `/buy 005930 1`) |
| `/sell 종목코드 수량` | 즉시 매도 |
| `/sellall 종목코드` | 해당 종목 전량 매도 |
| `/pause` | 자동매매 일시 중지 |
| `/resume` | 자동매매 재개 |
| `/stop` | 전체 시스템 종료 |

---

## 파일 위치 (서버 기준)

| 항목 | 경로 |
|------|------|
| 프로젝트 루트 | `~/stock_auto/` |
| 환경변수 설정 | `~/stock_auto/.env` |
| 토큰 캐시 | `~/stock_auto/config/token_cache.json` |
| 메인 프로그램 | `~/stock_auto/main.py` |
| systemd 서비스 파일 | `/etc/systemd/system/stock-bot.service` |
