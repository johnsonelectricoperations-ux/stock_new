#!/bin/bash
# EC2 서버에서 실행하는 배포 스크립트. 지정한 원격 브랜치를 고정 로컬 브랜치(deploy)로 받아 서비스를 재시작한다.
set -e
cd "$(dirname "$0")/.."

BRANCH_FILE=".deploy_branch"
BRANCH="${1:-$(cat "$BRANCH_FILE" 2>/dev/null)}"

if [ -z "$BRANCH" ]; then
    echo "사용법: ./scripts/deploy.sh <원격 브랜치명>"
    echo "(한 번 배포하면 브랜치명이 기억되어 이후엔 인자 없이 재배포 가능)"
    exit 1
fi

echo "==> origin/$BRANCH 배포 시작"
git fetch origin "$BRANCH"
# -f: 추적 파일의 로컬 변경 폐기. 운영 데이터(미추적 CSV, .env 등)는 영향 없음.
git checkout -f -B deploy "origin/$BRANCH"
echo "$BRANCH" > "$BRANCH_FILE"

sudo systemctl restart stock-bot
sleep 3
sudo systemctl status stock-bot --no-pager | head -10
echo "==> 배포 완료: $BRANCH ($(git log -1 --format='%h %s'))"
