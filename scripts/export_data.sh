#!/bin/bash
# EC2 서버에서 실행하는 데이터 전송 스크립트. 운영 CSV/JSON을 data_export/로 복사해 원격 data-export 브랜치로 푸시한다.
set -e
cd "$(dirname "$0")/.."

mkdir -p data_export
FILES="trades.csv signal_log.csv basis_log.csv timing_log.csv followup_log.csv market_log.csv error.log config/followup_pending.json"
COPIED=0
for f in $FILES; do
    if [ -f "$f" ]; then
        cp "$f" "data_export/$(basename "$f")"
        COPIED=$((COPIED + 1))
    fi
done

if [ "$COPIED" -eq 0 ]; then
    echo "복사할 데이터 파일이 없습니다."
    exit 1
fi

git add -f data_export
if git diff --cached --quiet; then
    echo "마지막 전송 이후 변경된 데이터가 없습니다."
    git reset >/dev/null
    exit 0
fi

git commit -m "data: 운영 데이터 스냅샷 $(date +%F_%H%M)" >/dev/null
git push --force origin HEAD:refs/heads/data-export
# 운영 브랜치(deploy)는 깨끗하게 유지 — 방금 커밋을 로컬에서만 되돌린다 (원격 data-export에는 보존됨)
git reset --hard HEAD~1 >/dev/null

echo "==> ${COPIED}개 파일을 data-export 브랜치로 전송 완료"
echo "    Claude 세션에서 'data-export 브랜치의 데이터를 분석해줘'라고 요청하세요."
