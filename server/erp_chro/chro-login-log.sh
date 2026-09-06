#!/bin/sh
# 서버의 /etc/profile.d/chro-login-log.sh — 로그인 셸에서 한 줄 남긴다(배1093 · 접속 기록).
# sshd 자체 로그는 journalctl -u sshd 로도 보이지만, 계정 전용 기록을 /srv/erp/chro 아래에도 남겨 둔다.
if [ "$(id -un 2>/dev/null)" = "chro" ]; then
    echo "$(date -Iseconds) login ${SSH_CONNECTION:-local}" >> /srv/erp/chro/last_login.log 2>/dev/null
fi
