# OPERATION.md — 운영 절차 (배포 · 데이터 전송 · 브랜치 정책)

> 이 문서 하나로 새 세션에서도 서버 배포·데이터 수신이 가능하다.
> 새 Claude 세션을 시작했다면 먼저 아래 0번을 읽을 것.

## 0. 새 세션 / 새 브랜치 시작 시 (필수 확인)

매 Claude 세션은 새 브랜치(claude/xxxx)에서 작업하지만, **서버와 데이터 워크플로우는 브랜치와 무관하게 동일하다.** 아래만 지키면 끊기지 않는다.

### 0-1. 새 세션의 Claude가 할 일

1. 이 저장소에 `OPERATION.md`, `PLAN.md`, `PROGRESS.md`, `TASKS.md`, `scripts/deploy.sh`, `scripts/export_data.sh`가 있는지 확인한다.
   - **없다면** (main에서 갓 분기한 경우), 직전 작업 브랜치에서 가져온다.
     ```bash
     # 최신 작업 내용이 있는 브랜치를 찾아 운영 파일을 현재 브랜치로 가져온다
     git fetch origin
     git ls-remote --heads origin            # 가장 최근 claude/* 브랜치 확인
     git checkout origin/<직전_작업_브랜치> -- OPERATION.md PLAN.md PROGRESS.md TASKS.md scripts/
     ```
   - 또는 data-export 브랜치가 아닌, 가장 최근 claude/* 브랜치를 기준으로 작업을 이어간다.
2. `PROGRESS.md` 최상단을 읽어 직전 세션이 어디까지 했는지 파악한다.
3. 작업·커밋·푸시 후, **현재 브랜치명을 사용자에게 알려준다.** (사용자가 그 이름으로 서버에 배포)

### 0-2. 사용자가 할 일 (요약 — 상세는 아래 2·3번)

```bash
# 서버 접속 후
cd /home/ubuntu/stock-bot
./scripts/deploy.sh <Claude가 알려준 브랜치명>   # 코드 배포
./scripts/export_data.sh                          # 데이터 보내기 (분석 받을 때)
```

서버에는 이미 GitHub 인증(PAT)과 deploy 브랜치가 설정돼 있으므로, 위 두 명령만 반복하면 된다.

### 0-3. 가장 안전한 방식 (권장)

운영 파일(OPERATION/PLAN/PROGRESS/TASKS/scripts)을 `main` 브랜치에도 반영해 두면, 새 세션이 main에서 분기해도 항상 이 파일들을 갖고 시작한다. (반영은 사용자 승인 필요 — 0-1의 "없다면" 절차가 불필요해짐.)

## 1. 브랜치 정책 — 브랜치가 바뀌어도 서버 연동이 깨지지 않게

문제. Claude 세션마다 새 브랜치(claude/xxxx)가 생기는데, 기존 배포 절차(reference.md)는
옛 브랜치명 `claude/file-modifications-main-ykk5n`이 하드코딩되어 있어 브랜치가 바뀔 때마다 끊어졌다.

해결. 서버는 더 이상 특정 브랜치명을 기억하지 않는다.

- 서버 로컬은 항상 `deploy`라는 고정 이름의 브랜치에서 실행된다.
- 배포할 때 `scripts/deploy.sh <브랜치명>`으로 원격 브랜치를 지정하면, 그 내용을 `deploy` 브랜치로 받아온다.
- 마지막으로 배포한 브랜치명은 서버의 `.deploy_branch` 파일에 자동 저장되어, 같은 브랜치 재배포는 인자 없이 `./scripts/deploy.sh`만 치면 된다.
- 운영 데이터(루트의 *.csv, error.log, config/token_cache.json, .env)는 git이 덮어쓰지 않으므로 배포해도 안전하다.

Claude 세션 쪽 규칙.

- Claude는 세션 브랜치에서 작업하고 푸시한 뒤, 채팅으로 브랜치명을 알려준다.
- 사용자는 검토 후 그 브랜치명으로 서버에서 deploy.sh를 실행하면 끝이다.

## 2. 배포 절차 (EC2에서 실행)

```bash
# 접속
ssh -i "C:\project_list\stock_auto\key\AWS\stock-bot.pem" ubuntu@서버IP주소
cd /home/ubuntu/stock-bot

# 첫 1회만: 배포 스크립트가 포함된 브랜치를 수동으로 받는다
git fetch origin <브랜치명>
git checkout -B deploy origin/<브랜치명>
chmod +x scripts/*.sh

# 이후 배포는 항상 이 한 줄
./scripts/deploy.sh <브랜치명>     # 새 브랜치 배포
./scripts/deploy.sh                # 직전 브랜치 재배포

# 상태 확인
sudo systemctl status stock-bot
```

deploy.sh가 하는 일. 지정 브랜치 fetch → `deploy` 브랜치로 강제 체크아웃 → 브랜치명 기억 → stock-bot 재시작 → 상태 출력.

## 3. 데이터 전송 절차 (EC2 → 분석 세션)

방법 A — 스크립트 (권장).

```bash
# EC2에서
cd /home/ubuntu/stock-bot
./scripts/export_data.sh
```

푸시에는 GitHub 인증이 필요하다. 최초 1회만 아래로 PAT(Personal Access Token)를 저장해 두면 이후엔 묻지 않는다.

```bash
git config credential.helper store
# 다음 push 때 Username: johnsonelectricoperations-ux / Password: <PAT> 입력 → ~/.git-credentials에 저장됨
```

운영 CSV/JSON을 `data_export/`로 복사해 원격 `data-export` 브랜치로 푸시한다.
이후 Claude 세션에서 "data-export 브랜치의 데이터를 분석해줘"라고 요청하면 된다.
운영 중인 deploy 브랜치 상태는 건드리지 않는다 (커밋은 data-export 브랜치에만 쌓임).

방법 B — 수동.

파일을 직접 채팅에 업로드하거나 붙여넣어도 된다. 대상 파일 목록.
`trades.csv, signal_log.csv, basis_log.csv, timing_log.csv, followup_log.csv, config/followup_pending.json, error.log`

## 4. 서비스 명령어 요약

```bash
sudo systemctl status stock-bot    # 상태
sudo systemctl restart stock-bot   # 재시작
sudo journalctl -u stock-bot -n 100 --no-pager   # 최근 로그
```

기타 트러블슈팅은 reference.md 참고.

## 5. 주의 사항

- 서버의 `.env`, `config/token_cache.json`은 git 관리 대상이 아니다. 배포로 사라지지 않지만, 백업은 별도로.
- `deploy.sh`는 git에 추적되는 파일만 원격 상태로 덮어쓴다. 서버에서 코드를 직접 수정했다면 배포 전에 커밋하거나 포기 여부를 결정할 것.
- reference.md의 기존 배포 명령(브랜치명 하드코딩)은 이 문서로 대체된다.
- 서버 정보: 경로 `/home/ubuntu/stock-bot`, 서비스 `stock-bot.service`, 서버 로컬 git 브랜치 `deploy` (고정).
- 2026-06-13 기준 최신 작업 브랜치: `claude/quirky-euler-eq5shu`. 새 세션은 이 브랜치(또는 이후 최신 claude/* 브랜치)에서 운영 파일을 가져오면 된다.
