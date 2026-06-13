# OPERATION.md — 운영 절차 (배포 · 데이터 전송 · 브랜치 정책)

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
