# .deploy-voc — VOC 통합접수처 GAS 배포 (clasp)

웰리가 VOC GAS를 직접 배포하기 위한 clasp 연동 폴더. (이전엔 미연동이라 GM 수동배포였음 — 2026-06-17 연동)

- **단일 소스(편집은 여기만):** `3. 웰페리온 가이드/coo/voc/apps_script_voc.js`
- **GAS 프로젝트:** "VOC" (scriptId = `.clasp.json`)
- **폼이 쓰는 /exec 배포ID(고정·URL 보존):** `AKfycbwk2XS1FND9V2xtXlWgsXzgA5p0FG7jVm6YKD74JK_ME_ZvHsNUUfGE5A_8p0X8VcF3gQ`
- `VOC_배포.js` = 배포 직전 소스에서 복사하는 산출물(.gitignore — 절대 직접 편집·커밋 금지, 디코이 함정 방지)

## 배포 (소스 수정 후)
```bash
cp "3. 웰페리온 가이드/coo/voc/apps_script_voc.js" .deploy-voc/VOC_배포.js
cd .deploy-voc && clasp push -f && \
  clasp deploy -i AKfycbwk2XS1FND9V2xtXlWgsXzgA5p0FG7jVm6YKD74JK_ME_ZvHsNUUfGE5A_8p0X8VcF3gQ
```
배포ID를 `-i`로 재사용해야 폼 VOC_API의 /exec URL이 보존된다(새 배포 만들면 URL 바뀜).

## 게이트 활성화(보안)는 별도
TOKEN_ENFORCE / ACCESS_TOKEN 활성화는 문의·VOC 전 시스템 함께 켜는 시토 작업(CTO-2026-06-17-GAS-PII-ACCESS-GATE)과 묶어 진행. 여기선 끄지도 켜지도 않는다(무중단).
