# wellperion.com DNS — Route53 레코드 표

- 호스팅 영역: `Z06764051TPW43YDJRQGF` (AWS 계정 476476092569 · 2026-09-19 · 배 2856)
- 등록기관: cafe24 (도메인 등록만 · 웹호스팅 「도메인 연결」은 유지 — 원본 WP 가 Host: wellperion.com 을 계속 받는다)
- 네임서버(cafe24 도메인 관리에 등록한 값):
  - ns-1177.awsdns-19.org
  - ns-746.awsdns-29.net
  - ns-26.awsdns-03.com
  - ns-1904.awsdns-46.co.uk

| 이름 | 종류 | TTL | 값 |
|---|---|---|---|
| wellperion.com | A | 300 | 15.164.151.105 (AWS 앞단 프록시 · 원본 183.111.138.230) |
| erp.wellperion.com | A | 300 | 15.164.151.105 |
| *.wellperion.com | CNAME | 300 | wellperion.com (www 포함) |
| wellperion.com | MX | 300 | 1 ASPMX.L.GOOGLE.COM |
| wellperion.com | MX | 300 | 5 ALT1.ASPMX.L.GOOGLE.COM |
| wellperion.com | MX | 300 | 6 ALT2.ASPMX.L.GOOGLE.COM |
| wellperion.com | MX | 300 | 10 ALT3.ASPMX.L.GOOGLE.COM |
| wellperion.com | MX | 300 | 11 ALT4.ASPMX.L.GOOGLE.COM |
| wellperion.com | TXT | 300 | "v=spf1 ip4:183.111.138.230 ~all" |

## 되돌림
1. cafe24 도메인 관리 › 네임서버 변경: `NS2.CAFE24.COM` / `NS1.CAFE24.COM` (옛 값 · 본인인증 필요). cafe24 DNS 의 A 는 183.111.138.230 로.
2. AWS 서버: `sudo mv /etc/nginx/conf.d/wellperion-site.conf /tmp/ && sudo nginx -t && sudo systemctl reload nginx`
3. Route53 영역은 레코드를 지운 뒤 `aws route53 delete-hosted-zone --id Z06764051TPW43YDJRQGF` (월 $0.50).
