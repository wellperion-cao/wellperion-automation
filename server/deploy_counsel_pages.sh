#!/usr/bin/env bash
# 상담봇 고객 페이지 배포(배1036) — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105.
#   bash server/deploy_counsel_pages.sh
# 하는 일: counsel/index.html(공통 템플릿) 을 다캠·고척 QA골프 폴더에 올리고(1_wellperion 은 ERP 루트 자체가 git
# 5분 동기화라 scp 안 함 — 커밋·푸시만 하면 뜬다), 공개 nginx location(counsel-public)을 넣고 reload. 고척 QA골프는 이미 있는 /gocheokgolf/ 라인(deploy_gocheokgolf.sh)을 그대로 쓴다.
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."
PAGE="3. 웰페리온 가이드/counsel/index.html"

$S "sudo mkdir -p /srv/www/3_gocheokgolf && sudo chown ec2-user:ec2-user /srv/www/3_gocheokgolf && mkdir -p /srv/www/2_dietcamp/counsel /srv/www/3_gocheokgolf/counsel"
# 사본은 템플릿 그대로가 아니라 각 테넌트 머리글로 갈아 끼워 올린다(배1002 AEO · 2026-09-09).
# 템플릿에 박힌 것은 웰페리온 값이다 — 그대로 올리면 다캠 페이지 제목이 「웰페리온 상담」이 된다.
# 프로필에 seo 가 없으면 렌더러가 중립문을 넣는다(값이 없을 때 남의 이름을 다는 쪽이 훨씬 나쁘다).
TMP=$(mktemp -d)
for t in 2_dietcamp 3_gocheokgolf; do
  C:/Python314/python.exe server/counselbot/render_counsel_page.py "$PAGE" "server/counselbot/tenants/$t.json" "$TMP/$t.html"
done
$SCP "$TMP/2_dietcamp.html" "$HOST:/srv/www/2_dietcamp/counsel/index.html"
$SCP "$TMP/3_gocheokgolf.html" "$HOST:/srv/www/3_gocheokgolf/counsel/index.html"
rm -rf "$TMP"
$SCP server/erp_api/counsel-public.nginx.conf $HOST:/tmp/counsel-public.conf
$S "sudo mv /tmp/counsel-public.conf /etc/nginx/conf.d/erp-locations/counsel-public.conf \
    && sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx"

echo "--- 다캠·고척 QA골프(즉시) ---"
for p in "dietcamp/counsel/" "gocheokgolf/counsel/"; do
  printf '%s = ' "$p"; curl -s -o /dev/null -w '%{http_code}\n' "https://erp.wellperion.com/$p"
done

# ★파트너사 섞임 방지 대조 (GM 지시 2026-09-10) — 올린 사본이 자기 자리에 있는지 라이브에서 확인한다.
# 2026-09-09 에 개명 뒤 표를 안 고쳐 고척 손님이 웰페리온 답을 받았다. 화면 안에 박힌 업체와 그 주소가
# 가리키는 업체가 어긋나면 페이지가 스스로 안 열리게 만들어 뒀고, 여기서는 그 어긋남을 배포 즉시 잡는다.
echo "--- 업체 박힘 대조 ---"
MISMATCH=0
check_baked () {   # $1 = 주소경로, $2 = 그 자리에 있어야 하는 업체
  got=$(curl -s "https://erp.wellperion.com/$1" | grep -o 'var BAKED_TENANT = "[^"]*"' | head -1 | sed 's/.*"\(.*\)"/\1/')
  got=${got//<!--TENANT-->/}; got=${got//<!--\/TENANT-->/}
  if [ "$got" = "$2" ]; then printf '  %-24s %s ✔\n' "$1" "$got"
  else printf '  %-24s 박힌업체=%s 인데 이 자리는 %s 여야 한다 ✘\n' "$1" "${got:-없음}" "$2"; MISMATCH=1; fi
}
check_baked "dietcamp/counsel/"    "2_dietcamp"
check_baked "gocheokgolf/counsel/" "3_gocheokgolf"
if [ "$MISMATCH" = "1" ]; then
  echo "!! 업체가 어긋난 사본이 올라갔다 — 그 페이지는 손님에게 안 열린다. 바로 다시 올려라." >&2
  exit 1
fi
echo "--- 웰페리온(git 5분 동기화 뒤 200 — 지금은 404 가 정상일 수 있다) ---"
curl -s -o /dev/null -w 'counsel/ = %{http_code}\n' "https://erp.wellperion.com/counsel/"
