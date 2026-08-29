#!/usr/bin/env node
/**
 * 웰페리온 statusline (2026-07-24 시토 · GM 지시).
 *
 * ━━ 소유권 · 편집 규칙 (웰리 결정 2026-07-25) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *  ① 표시 항목·문구·순서  = 웰리 단독 소유 — 변경 전 반드시 웰리에게 배로 올릴 것.
 *  ② 기술 배선            = 시토 (ensure_statusline.py·잘림·성능·자가복구).
 *  ③ 변경 전 필수         : 5역할 창 폭 실측 — 잘림 0 확인 후 커밋.
 *  ④ 동시 편집 금지       : 고칠 게 있으면 소유자(①또는②)에게 배로, 직접 수정 금지.
 *     (배경: 2026-07-24 63분·3역할·6커밋 — INC-034 '조용한 덮어쓰기' 재발 방지)
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 * 왜: 기존 statusline(OMC HUD)은 비용·모델·컨텍스트만 보여줘 GM 이 "지금 일이 돌고 있는지"를
 *     알 수 없었다("작업을 하는건지 마는건지 모르겠는데" — GM 2026-07-24).
 *
 * ★맨 앞 칸 = '지금 무슨 일을 하는 중인가' (GM 지시 2026-07-27 — 07-24 에 이어 같은 지적 2회):
 *     시토▶81 「작업하는 중이야? /statusline에…」 ·🟢고치는중 wellperion_hud.mjs 6분49초
 *     └역할 └잡은 배  └지금 받은 지시            └하는 동작 └대상        └지시 시작 후 경과
 *   세 가지 상태만 있다: 🟢<동작>(일하는 중) · 💬GM대기(내 차례 끝) · ⏸멎음(15분+ 무반응·빨강).
 *   ★시간 표기가 상태마다 다른 이유(GM 2026-07-27 "GM 대기 2초에서 멈춘거 아냐?"):
 *     상태줄은 **스스로 초를 세지 못한다.** Claude 가 무슨 일을 할 때만 이 스크립트를 다시 부른다.
 *     일하는 중 = 도구를 부를 때마다 다시 그려짐 → 경과 초가 실제로 움직인다(6분49초).
 *     대기·멎음 = 다시 그릴 일이 없음 → 경과 초는 그 자리에 얼어붙어 거짓이 된다.
 *     그래서 멈춘 상태는 '몇 시부터'로 적는다(10:14부터) — 얼어붙어도 언제 봐도 참인 값.
 *   ※형태는 GM 이 지목한 Claude 자체 작업표시(`… 구현  1m 18s`)를 따랐다.
 *   ※제목은 일하는 중일 때 **받은 지시**를, 대기 중일 때 **잡은 배 제목**을 쓴다 — 잡은 배와
 *     실제로 하는 일이 다를 때 배 제목만 보여주면 GM 이 여전히 뭘 하는지 모른다(실측 재현).
 *   ※신호 출처 = 세션 기록(transcript). 진행 한 줄·커밋은 **내가 보고해야** 움직여서 일하는
 *     동안 멎어 보였다 — 그게 같은 지적이 두 번 나온 이유다(약속 L02 문서 말고 코드로).
 *
 * 무엇을 보여주나 (웰리 결정 · GM 승인 D안 2026-07-25 — 배107):
 *     시토▶107 상태줄 재설계 — 한 줄에…·✅단계3분전 🆕2 · 항로🚢8⚓43·44·27+34 · 오늘🏁11 · ⏸시모▸10 16일 +7
 *     └역할 └잡은 배+제목(12자 상한 폐지 — 폭 가변·최소 20자) └새 지시 └대기 배 번호(무거운 순) └오늘 입항 └전사 '막힌 것 우선'
 *
 *   ★전사 가동 점(●●●●)은 삭제 — GM 판단 "정보량 0". 살아있음은 커밋 시각으로 이미 보이고,
 *     정작 안 보이던 건 "무엇이 멈춰 있나"였다(결재 60일·검수대기 8건). 그 자리를 이렇게 채운다:
 *     ① N일 정지 배(⏸ 역할▸번호 N일) ② 남는 폭에 정상 진행 배.
 *   ★⚠️ GM 결재 대기 칸은 2026-07-28 GM 판정으로 삭제 — 낱말 스캔이라 오탐(제목·next 텍스트를
 *     낱말로 잡다 보니 실제 결재 대기가 아닌 배까지 걸렸다). 결재 대기는 셸 보고·AI진행현황방
 *     두 곳에서 이미 간다.
 *   ★폭 반응형: 터미널 폭을 읽어 **뒤에서부터 접는다**(전사→오늘→대기목록→🆕 → 마지막까지 내 배).
 *     상태줄은 비대화형이라 토글이 없다 — 창을 넓히면 저절로 더 보이는 것이 토글의 대체다.
 *
 * ★7역할 공통 — 역할별 설정이 필요 없다.
 *     세션이 자기 transcript 첫머리의 부팅 프롬프트(`ai-cto.md` 등)를 읽어 **스스로 역할을 안다.**
 *     그래서 웰리·시뽀·시로·시모·시우·시포·시토 어느 창이든 같은 설정 한 줄로 동작한다.
 *
 * 위치: **저장소 안**에 둔다. ~/.claude 아래에만 두면 PC 가 바뀔 때 조용히 사라진다
 *       (배9889 에서 예약 런처로 똑같이 당했다). 설정 자가복구 = scripts/ensure_statusline.py.
 * 원칙: OMC HUD 파일은 건드리지 않는다(업데이트 때 덮어써진다). 이 래퍼가 감싼다.
 *       무슨 일이 생겨도 statusline 이 비지 않게 — 실패하면 OMC 출력만이라도 낸다.
 */
import { spawn, spawnSync } from 'node:child_process';
import { readFileSync, statSync, writeFileSync, mkdirSync, openSync, readSync, closeSync, fstatSync, readdirSync, unlinkSync } from 'node:fs';
import path from 'node:path';
import tty from 'node:tty';
import os from 'node:os';

const OMC_HUD = 'C:/Users/jjky0/.claude/hud/omc-hud-cost.mjs';
const NODE = process.execPath;

// 역할 기억함 — 한 번 알아낸 역할을 세션별로 적어둔다(2026-07-25 GM 지시).
//   왜: roleOf 는 transcript **첫 60,000자**에서 부팅 문구(ai-<role>.md)를 찾는다. 대화가
//   길어져 앞머리가 잘리거나 이어받은 창이면 그 문구가 사라져 역할을 못 찾고, 그러면 상태줄에서
//   내 줄이 **통째로 사라진다**(GM 2026-07-25 "나올 때도 있고 안 나올 때도 있는데"). 한 번
//   알아냈으면 기억해 두면 그 뒤로는 안 사라진다. 기억함이 없어도 동작은 같다(그냥 다시 찾는다).
const ROLE_CACHE = 'tmp/hud_role_cache.json';   // .gitignore 대상(tmp/) — 커밋 오염 없음
// 창을 띄운 Start-AI *.bat 이 알려준 역할. 대화기록이 아직 비어 있는 **부팅 직후**와
// 기록 저장이 꺼진 창에서 역할이 null 로 떨어져 상태줄이 회색 한 줄로 죽던 것을 받친다
// (GM 2026-08-04 "statusline에 색상이 다 없어진 것 같네"). 대화기록이 읽히면 그쪽이 이긴다.
const ENV_ROLE = /^(ceo|cfo|chro|cmo|coo|cpo|cto)$/.test(String(process.env.WELLPERION_ROLE || '').toLowerCase())
  ? String(process.env.WELLPERION_ROLE).toLowerCase()
  : null;
const ROLE_CACHE_MAX = 50;                       // 오래된 세션부터 버린다(무한 증식 방지)

const NICK = { ceo: '웰리', cfo: '시뽀', chro: '시로', cmo: '시모', coo: '시우', cpo: '시포', cto: '시토' };

const D = '\x1b[2m', C = '\x1b[36m', G = '\x1b[32m', Y = '\x1b[33m', R = '\x1b[31m';
const B = '\x1b[1m', X = '\x1b[0m';

function readStdin() { try { return readFileSync(0, 'utf8'); } catch { return '{}'; } }

// OMC HUD(비용·사용량 표시) 캐시 — 상태줄이 '나왔다 안 나왔다' 하던 진짜 원인 (2026-07-25 GM 지적).
//   실측: 상태줄 1회 = 평균 845ms. 그중 이 중첩 spawnSync 하나가 616~769ms(전체의 75%).
//   나머지는 node 기동 101ms · git 107ms · 큐 파싱 39ms 로 전부 합쳐도 250ms 남짓이다.
//   상태줄 갱신에는 시간 상한이 있어서, PC가 바쁘면(작업이 많을수록!) 이 회차가 통째로
//   건너뛰어져 화면이 비거나 옛 내용이 남는다 — 볼 게 제일 많을 때 안 보이는 역설.
//   → 비용·사용량은 초 단위로 급변하는 값이 아니다. 짧게 캐시해 재사용한다.
//     캐시가 살아있으면 프로세스를 아예 안 띄우므로 상태줄이 상한 안에 안정적으로 들어온다.
//   ※ OMC HUD 파일 자체는 여전히 건드리지 않는다(업데이트 시 덮어써짐 — 이 파일 상단 원칙).
const OMC_CACHE_TTL_MS = 15000;               // 15초 — 비용 표시가 최대 15초 늦을 뿐, 값은 정확
// ★2026-08-29 웰리 — OMC HUD 5.0.2 가 usage-api 네트워크 호출 때문에 느려졌다(실측 10~49초,
//   예전 2.5초 블로킹 spawnSync 로는 절대 못 끝낸다). 빈 결과를 짧은 TTL 로 캐시해 재시도하던
//   옛 방식은 "매번 2.5초를 블로킹하고도 영원히 빈손"이 돼 토큰·ctx 줄이 통째로 사라졌다
//   (GM 신고 2026-08-29). 그래서 블로킹 재시도를 버리고 아래 omcHud() 에서 백그라운드 새로고침
//   (느긋하게 최대 60초) + 마지막 성공값 즉시 표시로 바꿨다.
// 캐시 위치는 이 스크립트 위치에서 잡는다(<repo>/scripts/ → <repo>/tmp/).
// 상태줄은 cwd 가 매번 다를 수 있어 상대경로로 두면 캐시가 흩어진다.
const REPO_ROOT = path.dirname(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')));
const OMC_CACHE = path.join(REPO_ROOT, 'tmp', 'hud_omc_cache.json');   // .gitignore 대상(tmp/)
const SELF_PATH = new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');   // 백그라운드 새로고침에서 이 파일 자신을 재실행할 때 씀
const OMC_REFRESH_TMP_DIR = path.join(REPO_ROOT, 'tmp', 'hud_omc_refresh');   // 백그라운드 새로고침용 입력 임시파일(.gitignore 대상)
const OMC_REFRESH_COOLDOWN_MS = 30000;   // 이 안에 이미 새로고침을 띄웠으면 또 안 띄운다(중복 프로세스 방지)

// OMC 4.15.7 이 settings.json 의 statusLine 이 자기 스크립트를 안 가리키면(우리는 의도적으로
// wellperion_hud.mjs 를 가리킨다) 정상 출력(branch/모델/한도/ctx — 원래도 여러 줄이다) 대신
// 이 안내 배너를 낸다 — 우리 상태줄엔 소음이다(배417, 2026-08-06). 배너는 "[OMC] HUD"(공백,
// 정상 출력의 "[OMC#4.15.7L]"과 다름)·"NOT configured"·"HUD script:" 문구로만 정확히 가려낸다.
function isOmcBanner(s) {
  return !s || /\[OMC\]\s+HUD/.test(s) || /NOT configured/.test(s) || /HUD script:/.test(s);
}

// ★캐시를 **세션별로** 나눈다 (GM 지적 2026-08-13 "ctx 가 파워셸마다 통합되는거야? 예전엔 각각이었는데").
//   원인: 캐시 파일이 저장소당 한 개(<repo>/tmp/hud_omc_cache.json)였다. OMC 줄에는 그 세션의
//   맥락 사용률(ctx)·토큰 수가 들어 있는데, 창 5개가 같은 파일을 나눠 쓰니 **먼저 그린 창의 값**을
//   나머지 창이 15초 동안 그대로 보여 준다 — 그래서 전부 같은 숫자로 보였다.
//   고침: 한 파일 안에서 **세션 id 별로 칸을 나눈다**(파일 개수는 그대로 1개 · 새 파일 0).
//   오래된 칸은 지운다(창을 닫으면 그 칸은 더 안 쓰인다 — 무한 증식 방지).
const OMC_CACHE_MAX_SESSIONS = 12;
const OMC_CACHE_STALE_MS = 10 * 60 * 1000;   // 10분 넘게 안 쓰인 세션 칸은 버린다

function _sessionKey(input) {
  try {
    const j = JSON.parse(input);
    return String(j?.session_id || j?.transcript_path || 'unknown').slice(-40);
  } catch { return 'unknown'; }
}

function omcHud(input) {
  const cachePath = OMC_CACHE;
  const key = _sessionKey(input);
  let store = null;
  try { store = JSON.parse(readFileSync(cachePath, 'utf8')); } catch { /* 캐시 없음·깨짐 — 새로 계산 */ }
  if (!store || typeof store !== 'object' || Array.isArray(store)) store = {};
  // 옛 형식({at,out} 한 벌)이 남아 있으면 버린다 — 세션 구분이 없던 값이라 남의 값일 수 있다.
  if (Object.prototype.hasOwnProperty.call(store, 'out')) store = {};
  const cached = store[key] || null;
  const now = Date.now();

  // 1) 살아있는 성공값이면 그대로 쓴다 — 새로고침도 안 띄운다.
  if (cached && typeof cached.out === 'string' && cached.out && (now - (cached.at || 0)) < OMC_CACHE_TTL_MS) {
    return cached.out;
  }

  // 2) 캐시가 없거나 낡았으면 백그라운드로 새로고침한다 — 메인 렌더는 절대 안 기다린다(위 주석
  //    참고, OMC HUD 가 10~49초 걸릴 수 있다). 이미 진행 중인 새로고침이 있으면 쿨다운 안엔
  //    또 안 띄운다(렌더될 때마다 프로세스가 쌓이는 것 방지).
  const refreshing = cached && cached.refreshing && (now - cached.refreshing) < OMC_REFRESH_COOLDOWN_MS;
  if (!refreshing) {
    try {
      mkdirSync(OMC_REFRESH_TMP_DIR, { recursive: true });
      const tmpFile = path.join(OMC_REFRESH_TMP_DIR, `${key.replace(/[^a-zA-Z0-9_-]/g, '_')}.json`);
      writeFileSync(tmpFile, input, 'utf8');
      const child = spawn(NODE, [SELF_PATH, '--bg-refresh-omc', key, tmpFile], {
        detached: true, stdio: 'ignore', windowsHide: true,
      });
      child.unref();
      store[key] = { ...(cached || {}), refreshing: now };
      const stale = Date.now();
      for (const k of Object.keys(store)) {
        if (stale - (store[k]?.at || store[k]?.refreshing || 0) > OMC_CACHE_STALE_MS) delete store[k];
      }
      const keys = Object.keys(store).sort((a, b) => (store[a].at || 0) - (store[b].at || 0));
      for (const k of keys.slice(0, Math.max(0, keys.length - OMC_CACHE_MAX_SESSIONS))) delete store[k];
      mkdirSync(path.dirname(cachePath), { recursive: true });
      writeFileSync(cachePath, JSON.stringify(store), 'utf8');
    } catch { /* 새로고침을 못 띄워도 표시는 마지막 값으로 정상 */ }
  }

  // 3) 지금 화면엔 마지막으로 성공한 값을 낸다(늦더라도 빈 화면보다 낫다). 한 번도 없었으면 빈 문자열.
  return cached && typeof cached.out === 'string' ? cached.out : '';
}

// ── OMC HUD 백그라운드 새로고침 진입점 (2026-08-29 웰리) ───────────────────
// omcHud() 가 spawn(detached)으로 이 파일을 재실행할 때 쓰는 경로. 메인 렌더 경로와 분리해
// 여유 있게(60초) 기다린 뒤 캐시만 갱신하고 조용히 끝난다 — 화면에는 아무것도 안 낸다.
function runBgRefreshOmc(key, tmpFile) {
  let out = '';
  try {
    const input = readFileSync(tmpFile, 'utf8');
    const r = spawnSync(NODE, [OMC_HUD], { input, encoding: 'utf8', timeout: 60000 });
    out = (r.stdout || '').replace(/\s+$/, '');
    if (isOmcBanner(out)) out = '';
  } catch { /* out = '' 유지 — 다음 새로고침이 다시 시도 */ }
  try {
    let store = {};
    try { store = JSON.parse(readFileSync(OMC_CACHE, 'utf8')); } catch { /* 없으면 새로 */ }
    if (!store || typeof store !== 'object' || Array.isArray(store)) store = {};
    store[key] = { at: Date.now(), out };
    mkdirSync(path.dirname(OMC_CACHE), { recursive: true });
    writeFileSync(OMC_CACHE, JSON.stringify(store), 'utf8');
  } catch { /* 캐시 못 쓰면 다음 새로고침이 다시 시도 */ }
  try { unlinkSync(tmpFile); } catch { /* 이미 없거나 못 지워도 무해 */ }
}

function git(cwd, args) {
  try {
    const r = spawnSync('git', args, { cwd, encoding: 'utf8', timeout: 4000 });
    return r.status === 0 ? (r.stdout || '').trim() : '';
  } catch { return ''; }
}

/** 세션 역할 — transcript 첫머리 부팅 프롬프트의 `ai-<role>.md` 를 읽는다. */
function roleOf(transcript) {
  if (!transcript) return null;
  try {
    const raw = readFileSync(transcript, 'utf8');
    const RE = /ai-(ceo|cfo|chro|cmo|coo|cpo|cto)\.md/;
    const m = raw.slice(0, 60000).match(RE);
    if (m) return m[1];
    // ★꼬리도 본다 (2026-08-13 시토 · GM "시토 statusline 아래에 왜 저장소만 나와?").
    //   앞머리 6만 자만 보던 탓에 **이어받은 창·앞이 잘린 긴 대화**에서 역할을 못 찾았고,
    //   그러면 상태줄이 회색 한 줄("역할 확인중 · 작업표시 대기")로 죽어 GM 화면엔 저장소 줄만
    //   남는다(실측 재현). 부팅 문구는 앞에 있지만, 역할 이름은 대화 중에도 계속 스친다.
    //   전체를 훑지 않고 꼬리 6만 자만 더 본다 — 렌더마다 도는 자리라 비용을 늘리지 않는다.
    const tail = raw.length > 60000 ? raw.slice(-60000) : '';
    const t = tail && tail.match(RE);
    return t ? t[1] : null;
  } catch { return null; }
}

/** 역할 — 찾아보고, 못 찾으면 기억함에서 꺼낸다. 찾았으면 기억함에 적어둔다.
 *  기억함을 못 읽거나 못 쓰더라도 roleOf 결과 그대로 동작한다(기억함은 덤이지 의존이 아니다). */
function resolveRole(cwd, transcript) {
  const found = roleOf(transcript);
  if (!transcript) return found || ENV_ROLE;
  // 기억함 열쇠는 경로 표기를 통일한다 — 같은 파일이 `C:\..\a.jsonl` 과 `C:/../a.jsonl` 로
  // 들어오면 다른 세션으로 오인해 기억이 헛돈다(윈도우는 둘 다 유효한 표기다).
  const key = String(transcript).replace(/\\/g, '/').toLowerCase();
  const cachePath = path.join(cwd, ROLE_CACHE);

  let cache = {};
  try { cache = JSON.parse(readFileSync(cachePath, 'utf8')) || {}; } catch { /* 없으면 빈 것 */ }
  if (typeof cache !== 'object' || Array.isArray(cache)) cache = {};

  if (!found) return cache[key] || ENV_ROLE || null;   // 기억함 → 창이 알려준 역할 순으로 버틴다
  if (cache[key] === found) return found;  // 이미 같은 값 — 쓰지 않는다(디스크 낭비 방지)

  cache[key] = found;
  const keys = Object.keys(cache);
  if (keys.length > ROLE_CACHE_MAX) for (const k of keys.slice(0, keys.length - ROLE_CACHE_MAX)) delete cache[k];
  try {
    mkdirSync(path.dirname(cachePath), { recursive: true });
    writeFileSync(cachePath, JSON.stringify(cache), 'utf8');
  } catch { /* 못 써도 이번 판정은 이미 나왔다 */ }
  return found;
}

/** 내가 방금 넘긴 단계 — AI 진행현황방으로 보낸 마지막 한 줄(status/progress_report_log.jsonl).
 *  왜: 상태줄이 보던 건 '할 일 목록'과 '커밋'뿐이라 **일하는 동안에는 아무것도 안 움직였다**
 *  (GM 2026-07-25 "나도 감이 안 잡히네"). 진행 한 줄은 단계를 넘길 때마다 쓰이므로 실제로 움직인다.
 *  ship 칸이 "시토 81" 꼴이라 닉네임으로 내 것만 고른다. */
function lastProgress(cwd, role) {
  const nick = NICK[role];
  if (!nick) return null;
  try {
    const p = path.join(cwd, 'status', 'progress_report_log.jsonl');
    if (statSync(p).size > 2_000_000) return null;   // 비정상 비대 — 상태줄이 느려지면 안 된다
    const lines = readFileSync(p, 'utf8').split('\n');
    for (let i = lines.length - 1; i >= 0; i--) {
      const raw = lines[i].trim();
      if (!raw) continue;
      let rec;
      try { rec = JSON.parse(raw); } catch { continue; }
      if (!rec || !rec.sent) continue;                       // 실제로 나간 것만
      if (!String(rec.ship || '').startsWith(nick)) continue; // 내 배만
      const ts = Date.parse(rec.ts);
      if (!Number.isFinite(ts)) continue;
      return {
        mins: Math.max(0, Math.round((Date.now() - ts) / 60000)),
        step: shortTitle(rec.step, 6),   // 단계 이름은 짧게 — 제목 칸에 폭을 양보한다
        state: String(rec.state || 'done'),
      };
    }
  } catch { /* 없으면 커밋 시각으로 폴백 */ }
  return null;
}

// ── 지금 돌고 있나 · 무엇을 하는 중인가 (GM 지시 2026-07-27) ──────────────────────
//  왜: 기존 '움직임' 신호 둘(진행 한 줄 lastProgress · 커밋 myLastCommit)은 **사람이 보고해야
//  움직인다.** 보고를 잊거나 한 배가 길어지면 일하는 중에도 상태줄이 멎어 보였다 —
//  GM 이 07-24 에 이어 07-27 에 똑같이 물으셨다("작업하는 중이야? 뭘 작업하는지 모르겠어").
//  같은 지적 2회 = 문서·습관으로 못 막는다는 뜻이므로, **잊을 수가 없는 신호**로 바꾼다(약속 L02).
//  세션 기록(transcript)은 도구를 부를 때마다 자동으로 쌓인다 — 보고와 무관하게 항상 진실이다.
//  형태는 GM 이 지목한 Claude 자체 표시(`… 자율 착수 기준 개선 구현  1m 18s`)를 따른다:
//  **무엇을 하는 중 + 이번 지시 시작 후 경과시간.**
//  성능: 파일 끝 256KB 만 훑고, 필요한 줄만 JSON 파싱한다(수 MB 기록이어도 렌더 200ms 계약 안).
const TAIL_BYTES = 1_500_000;   // 표식 검색만 하므로 창을 넓게 잡아도 렌더 시간이 늘지 않는다
const ACT = {
  Read: '읽는중', NotebookRead: '읽는중',
  Edit: '고치는중', Write: '고치는중', NotebookEdit: '고치는중', MultiEdit: '고치는중',
  Bash: '실행중', PowerShell: '실행중', BashOutput: '실행중',
  Grep: '찾는중', Glob: '찾는중',
  Task: '위임중', Agent: '위임중', Workflow: '위임중',
  WebFetch: '조회중', WebSearch: '조회중',
  Skill: '스킬', Artifact: '발행중', SendUserFile: '보내는중',
};

function actTarget(tu) {
  const inp = (tu && tu.input) || {};
  const f = inp.file_path || inp.path || inp.notebook_path;
  if (f) return String(f).split(/[\\/]/).pop();
  // ★명령문보다 설명을 먼저 쓴다 — 명령 앞머리는 변수 대입·경로라서 GM 에게 아무 뜻이 없다
  //   (실측: 'W="C:/Users/…' 가 떴다). 설명은 사람이 읽으라고 쓴 한 줄이라 그대로 쓸 수 있다.
  if (inp.description) return String(inp.description);
  if (inp.command) return String(inp.command).trim().split(/\s+/).slice(0, 2).join(' ');
  if (inp.pattern) return String(inp.pattern);
  if (inp.skill) return String(inp.skill);
  if (inp.subagent_type) return String(inp.subagent_type);
  return '';
}
function toolUseOf(r) {
  const c = r && r.message && r.message.content;
  if (!Array.isArray(c)) return null;
  for (let i = c.length - 1; i >= 0; i--) if (c[i] && c[i].type === 'tool_use') return c[i];
  return null;
}
/** 도구 결과가 아니라 **사람이 실제로 친 지시**인 기록인가 — 경과시간의 기준점. */
function isHumanTurn(r) {
  if (!r || r.type !== 'user') return false;
  const c = r.message && r.message.content;
  if (typeof c === 'string') return c.trim().length > 0;
  if (!Array.isArray(c)) return false;
  return !c.some(b => b && b.type === 'tool_result');
}
/** 지금 받은 지시의 첫 줄 — '무슨 일을 하는 중인가'의 가장 정직한 답.
 *  왜 큐의 배 제목을 안 쓰나: 잡아둔 배와 지금 실제로 하는 일이 다를 수 있다(실측 — 배81을
 *  잡은 채 상태줄을 고치고 있었고, 상태줄엔 "텔레그램 방 재편"이 떠 있었다). 그러면 GM 이
 *  화면을 봐도 여전히 뭘 하는지 모른다. 받은 지시는 언제나 지금 하는 일과 같다. */
function askText(r) {
  const c = r && r.message && r.message.content;
  let t = '';
  if (typeof c === 'string') t = c;
  else if (Array.isArray(c)) t = c.filter(b => b && b.type === 'text').map(b => b.text || '').join(' ');
  for (const raw of String(t).split('\n')) {
    const s = raw.trim();
    if (!s || s.startsWith('<')) continue;   // 시스템이 덧붙인 안내 블록은 지시가 아니다
    return s.replace(/\s+/g, ' ');
  }
  return '';
}

/** 지금 돌고 있는 백그라운드 에이전트 — 몇 척 · 가장 오래 돈 것의 시작 시각(GM 지시 2026-07-27 18:30).
 *  왜: "말만 하고 끝낸 응답이 마지막 = 내 차례 끝"(위 working 판정)은 배경 에이전트를 띄워놓고
 *  말을 마친 경우를 못 가린다 — 그러면 일이 도는데 상태줄은 '대기'라고 GM 께 거짓말을 한다
 *  (GM 2026-07-27 "또 아래 대기 18:30부터 뜨네" — 그 시각 웰리는 에이전트 3척을 띄운 상태였다).
 *  새 상태 파일은 만들지 않는다(약속 L21) — transcript 안에 이미 두 표식이 있다:
 *   ① 에이전트를 띄운 직후 tool_result 에 "Async agent launched successfully … agentId: X" 가
 *      찍힌다(비동기 시작 확인일 뿐 — 완료 여부와 무관하게 **항상** 바로 나타난다. 그래서 이
 *      tool_result 유무만으로는 '아직 도는 중'을 못 가린다).
 *   ② 그 에이전트가 끝나면(성공·실패 가리지 않고) 같은 transcript 뒤쪽에
 *      `<task-notification><task-id>X</task-id>…<status>completed</status>…` 블록이 나타난다
 *      (큐 enqueue/remove + attachment 로 최대 3벌 중복 — Set 으로 중복 제거).
 *  판정: ①은 있는데 ②가 아직 없는 agentId = 아직 도는 중. (실측: 이 세션 자체로 검증 — 07-27
 *  18:32 시점 배경 에이전트 4척이 떠 있었고 이 로직이 정확히 4를 셌다.) */
function runningAgents(str) {
  const launched = new Map();   // agentId → 시작 시각(ms)
  const done = new Set();       // 완료 통보가 온 agentId
  for (const line of str.split('\n')) {
    if (!line) continue;
    if (line.includes('Async agent launched successfully')) {
      const m = line.match(/agentId:\s*([A-Za-z0-9]+)/);
      if (m) {
        let ts = null;
        try { ts = Date.parse(JSON.parse(line).timestamp || ''); } catch { /* 파싱 실패 — 무시 */ }
        if (Number.isFinite(ts)) launched.set(m[1], ts);
      }
    }
    if (line.includes('<status>completed</status>')) {
      const re = /<task-id>([^<]+)<\/task-id>/g;
      let mm; while ((mm = re.exec(line))) done.add(mm[1]);
    }
  }
  let count = 0, since = null;
  for (const [id, ts] of launched) {
    if (done.has(id)) continue;   // 이미 끝난 것까지 '도는 중'으로 세면 그게 더 나쁜 거짓말이다
    count++;
    if (since === null || ts < since) since = ts;
  }
  return count > 0 ? { count, since } : null;
}

/** 배경 에이전트 — transcript 파싱(위 runningAgents) 대신 **실측**으로 가린다(GM 지적 2026-07-28
 *  15:15 "대기 15:15부터 이것 좀 처리가 안 되나" — 그 순간에도 에이전트 3척이 돌고 있었다).
 *  뿌리: transcript 꼬리 파싱은 표식 문구가 창 밖으로 밀려나거나 형식이 바뀌면 놓친다 — 추측이다.
 *  각 배경 에이전트는 실행 중 자기 출력 파일을 갱신한다:
 *    <tmp>/claude/<cwd 슬러그>/<session_id>/tasks/*.output
 *  이 파일들 중 최근 BG_WINDOW_MS 안에 갱신된 것이 있으면 → 실제로 돌고 있다(추정이 아니라 실측).
 *  ★내용은 읽지 않는다(대용량일 수 있음 · GM 지시) — statSync 로 mtime 만 본다. */
const BG_WINDOW_MS = 90_000;   // GM 지시 — 최근 90초 안에 갱신되면 '일하는 중'
function slugifyCwd(cwd) {
  return String(cwd).replace(/\\/g, '/').replace(/^([A-Za-z]):/, '$1-').replace(/\//g, '-');
}
function backgroundAgents(cwd, sessionId) {
  if (!sessionId) return null;
  try {
    const dir = path.join(os.tmpdir(), 'claude', slugifyCwd(cwd), sessionId, 'tasks');
    // ★.output 은 에이전트만 쓰는 게 아니다 — 일반 명령(Bash 등) 출력도 같은 폴더에 쌓인다.
    //   그래서 파일 이름으로 가린다: 에이전트 id 는 'a'+16자리 16진수(예 a8abf02a21406b615),
    //   명령 출력은 짧은 임의 문자열(예 bvxrj2da4). 안 가리면 명령 하나만 돌려도 '위임중'이 뜬다
    //   (GM 지적 2026-07-28 "202 위임중 27분18초? 어떤 내용을 위임하는거지" — 그때 도는 건 없었다).
    const AGENT_ID = /^a[0-9a-f]{16}\.output$/;
    const files = readdirSync(dir).filter((f) => AGENT_ID.test(f));
    const now = Date.now();
    let count = 0, since = null;
    for (const f of files) {
      try {
        const st = statSync(path.join(dir, f));
        if (now - st.mtimeMs >= BG_WINDOW_MS) continue;
        count++;
        // 경과는 이 파일이 처음 생긴 시각으로 잰다 — transcript 에서 주워온 값은 이미 끝난
        // 에이전트의 시작시각이라 계속 늘어나며 거짓이 된다(같은 GM 지적).
        const born = st.birthtimeMs || st.mtimeMs;
        if (since === null || born < since) since = born;
      } catch { /* 파일 하나 못 읽어도 나머지는 센다 */ }
    }
    const sub = mySubagents(cwd, sessionId);
    if (sub) {
      count += sub.count;
      if (since === null || (sub.since && sub.since < since)) since = sub.since;
    }
    return count > 0 ? { count, since } : null;
  } catch {
    // tasks 폴더가 없어도(이름 붙인 에이전트는 여기 안 쓴다) 서브에이전트는 따로 세야 한다.
    try { return mySubagents(cwd, sessionId); } catch { return null; }
  }
}

/** 내가 띄운 서브에이전트 — 이름 붙인 에이전트는 위 tasks/*.output 이 아니라
 *  <projects>/<내 세션id>/subagents/*.jsonl 에 기록을 쌓는다(2026-07-29 실측).
 *  그래서 tasks 폴더만 보던 기존 판정은 6척이 돌아도 0으로 셌다. */
function mySubagents(cwd, sessionId) {
  if (!sessionId) return null;
  try {
    const cache = JSON.parse(readFileSync(path.join(cwd, ROLE_CACHE), 'utf8'));
    const anyKey = Object.keys(cache)[0];
    if (!anyKey) return null;
    const dir = path.join(path.dirname(String(anyKey)), String(sessionId), 'subagents');
    const now = Date.now();
    let count = 0, since = null;
    for (const f of readdirSync(dir)) {
      if (!f.toLowerCase().endsWith('.jsonl')) continue;
      let st;
      try { st = statSync(path.join(dir, f)); } catch { continue; }
      if (now - st.mtimeMs >= SUBAGENT_LIVE_MS) continue;
      count++;
      const born = st.birthtimeMs || st.mtimeMs;
      if (since === null || born < since) since = born;
    }
    return count > 0 ? { count, since } : null;
  } catch { return null; }
}

/** 위임해서 돌고 있는 일 — **서브에이전트 대화기록**을 실측한다 (GM 지적 2026-07-29
 *  "병렬로 가동 중인데 /statusline 에는 다 쉼 07-28 23:43 으로 되어있는데?").
 *
 *  뿌리: 상태줄의 C레벨 줄은 '그 역할의 **창**이 움직였나'만 봤다. 그런데 2026-07-29 GM 지시로
 *  시토가 창을 안 열고 **대신 돌리는 방식**으로 바뀌었다 — 그 순간 6척이 실제로 돌고 있는데
 *  화면은 전부 '쉼'이었다. 일이 도는데 안 돈다고 말하는 거짓 표시다.
 *
 *  신호: 위임한 에이전트는 각자 자기 대화기록을 쌓는다 —
 *    <projects>/<세션id>/subagents/agent-a<이름>-<해시>.jsonl
 *  파일 **이름에 내가 붙인 이름**(예 siwoo-9678)이 그대로 들어 있고, 수정시각이 곧 '지금 움직임'이다.
 *  ★내용은 읽지 않는다(수 MB) — 이름과 mtime 만 본다.
 *  ★역할 판정: ①이름에 닉네임이 들어 있으면 그 역할 ②없으면 그 에이전트를 띄운 **창의 역할**
 *    (경로의 세션id ↔ 역할 기억함). 둘 다 안 되면 세지 않는다(모르는 걸 지어내지 않는다). */
// 10분 — 창(2분)보다 넉넉히 잡는다. 위임한 에이전트는 오래 걸리는 도구 하나(라이브 조회·큰 파일
// 검색)에 몇 분씩 조용해진다. 2분으로 재면 실제로 일하는 중인데 '쉼'으로 보인다 — GM 이 지적한 바로
// 그 증상이다(2026-07-29 실측: 시우 두 척이 273·285초 침묵 중이었고 둘 다 살아 있었다).
// 대가: 이미 끝난 에이전트가 최대 10분간 남아 보일 수 있다. '돌고 있는데 안 돈다고 하는 것'보다 낫다.
const SUBAGENT_LIVE_MS = 600_000;
const NAME_ROLE = [
  [/welly|웰리/i, 'ceo'], [/sito|시토/i, 'cto'], [/simo|시모/i, 'cmo'],
  [/siwoo|시우/i, 'coo'], [/sipo|시포/i, 'cpo'],
];
function delegatedAgents(cwd) {
  const out = {};
  try {
    const cache = JSON.parse(readFileSync(path.join(cwd, ROLE_CACHE), 'utf8'));
    const sessRole = {};
    let projDir = null;
    for (const [file, r] of Object.entries(cache)) {
      if (typeof r !== 'string') continue;
      const base = path.basename(String(file));
      if (!base.toLowerCase().endsWith('.jsonl')) continue;
      sessRole[base.slice(0, -6).toLowerCase()] = r;
      if (!projDir) projDir = path.dirname(String(file));
    }
    if (!projDir) return out;
    const now = Date.now();
    // ★훑을 대상 = **역할 기억함이 아는 창**뿐이다(최대 50개). 폴더 전체를 훑으면 지난 몇 주치
    //   죽은 세션 수백 개를 먼저 세다가 정작 지금 도는 창에 닿기도 전에 상한에 걸린다
    //   — 실측으로 그래서 6척이 돌아도 0으로 셌다(2026-07-29).
    for (const sess of Object.keys(sessRole)) {
      let files;
      try { files = readdirSync(path.join(projDir, sess, 'subagents')); } catch { continue; }
      let scanned = 0;
      for (const f of files) {
        if (++scanned > 200) break;                       // 폴더당 상한 — 렌더 200ms 계약
        if (!f.toLowerCase().endsWith('.jsonl')) continue;
        let st;
        try { st = statSync(path.join(projDir, sess, 'subagents', f)); } catch { continue; }
        if (now - st.mtimeMs >= SUBAGENT_LIVE_MS) continue;
        // 파일명 = agent-a<내가 붙인 이름>-<16자리 해시>.jsonl
        // ★해시를 먼저 떼어낸다 — 안 떼면 해시 속 숫자가 배 번호로 둔갑한다
        //   (실측: agent-aa598695f4782f2c3 → '배598695', sipo-product-54f3afb1890… → '배1890').
        const nm = f.replace(/^agent-a?/i, '').replace(/-?[0-9a-f]{16}\.jsonl$/i, '').replace(/\.jsonl$/i, '');
        let role = null;
        for (const [re, r] of NAME_ROLE) if (re.test(nm)) { role = r; break; }
        if (!role) role = sessRole[String(sess).toLowerCase()] || null;
        if (!role) continue;
        const e = out[role] || (out[role] = { count: 0, ships: [], since: null });
        e.count++;
        // ★끝자락 숫자만 배 번호로 본다 — 하이픈 유무 안 가린다('simo-9457'도 'ship293'도 잡아야
        //   한다). 기존엔 하이픈 앞뒤로 떨어진 숫자만 찾아 'ship293' 같은 이름을 놓쳤다(실측
        //   2026-08-04: 웰리 아래 살아있는 위임 2척이 'ship293'·'ship349' 인데 배 번호를 못 뽑아
        //   화면엔 며칠 전 커밋의 배10521 이 대신 떴다 — GM 지적 "배편도 이상한 걸로"의 뿌리).
        const m = nm.match(/(\d{3,6})$/);

        if (m && !e.ships.includes(m[1])) e.ships.push(m[1]);
        const born = st.birthtimeMs || st.mtimeMs;
        if (e.since === null || born < e.since) e.since = born;
      }
    }
  } catch { /* 기억함 없음·폴더 없음 — 위임 표시만 빠진다 */ }
  return out;
}

function liveAction(transcript) {
  if (!transcript) return null;
  let fd = null;
  try {
    fd = openSync(transcript, 'r');
    const size = fstatSync(fd).size;
    const len = Math.min(TAIL_BYTES, size);
    const buf = Buffer.allocUnsafe(len);
    readSync(fd, buf, 0, len, size - len);
    let str = buf.toString('utf8');
    if (size > len) str = str.slice(str.indexOf('\n') + 1);   // 잘린 첫 줄은 버린다

    // ★줄 단위로 전부 파싱하지 않는다 — 표식을 뒤에서부터 찾아 **그 줄만** 떼어 파싱한다.
    //   기록이 수 MB 로 자라도 파싱은 서너 번뿐이라 렌더 시간이 늘지 않는다.
    const lineAt = (i) => {
      const a = str.lastIndexOf('\n', i) + 1;
      const b = str.indexOf('\n', i);
      return str.slice(a, b === -1 ? undefined : b);
    };
    const parseBack = (needle, from, test) => {
      let i = from;
      for (let n = 0; n < 40 && i > 0; n++) {          // 헛짚음 대비 40줄까지만 되짚는다
        i = str.lastIndexOf(needle, i - 1);
        if (i < 0) return null;
        let r; try { r = JSON.parse(lineAt(i)); } catch { continue; }
        if (!test || test(r)) return r;
      }
      return null;
    };

    // ① 마지막 기록 — 지금 움직이고 있는지 / 내 차례가 끝났는지
    const last = parseBack('"type":"', str.length, r => r.type === 'user' || r.type === 'assistant');
    if (!last) return null;
    // ② 지금 부르고 있는 도구 — 무엇을 하는 중인가
    const tuRec = parseBack('"type":"tool_use"', str.length);
    const tu = tuRec ? toolUseOf(tuRec) : null;
    const act = tu ? { tool: tu.name, target: actTarget(tu) } : null;
    // ③ 이번 지시의 시작점 — 사람이 실제로 친 프롬프트에만 붙는 표식(promptSource)으로 찾는다.
    //    표식이 없는 버전이면 '도구 결과가 아닌 user 기록'으로 폴백한다.
    const human = parseBack('"promptSource"', str.length, isHumanTurn)
      || parseBack('"type":"user"', str.length, isHumanTurn);
    let turnAt = null, ask = '';
    if (human) {
      const t = Date.parse(human.timestamp || '');
      if (Number.isFinite(t)) { turnAt = t; ask = askText(human); }
    }
    const lastAt = Date.parse(last.timestamp || '');
    if (!Number.isFinite(lastAt)) return null;
    const now = Date.now();
    // 말만 하고 끝낸 응답이 마지막 = 내 차례가 끝났다는 뜻 → GM 입력 대기.
    // ★단, 배경 에이전트가 돌고 있으면 얘기가 다르다 — 아래 agents 로 buildLine 에서 따로 가린다.
    const working = !(last.type === 'assistant' && !toolUseOf(last));
    return {
      working,
      idle: Math.max(0, Math.round((now - lastAt) / 1000)),                    // 마지막 움직임 이후
      elapsed: turnAt ? Math.max(0, Math.round((now - turnAt) / 1000)) : null, // 이번 지시 시작 후
      at: lastAt,                                                              // 마지막 움직임의 실제 시각
      act: working ? act : null,
      ask,                                                                     // 지금 받은 지시 첫 줄
      agents: runningAgents(str),                                             // 지금 도는 배경 에이전트
    };
  } catch { return null; }
  finally { if (fd !== null) { try { closeSync(fd); } catch { /* 닫기 실패는 무해 */ } } }
}

/** 벽시계 시각(HH:MM) — ★얼어붙어도 거짓말이 안 되는 값.
 *  왜: 상태줄은 스스로 초를 세지 못한다. Claude 가 무슨 일을 할 때만 이 스크립트를 다시 부르는데,
 *  내 차례가 끝나면 다시 부를 일이 없어 화면이 마지막으로 그려진 순간의 숫자에 그대로 멎는다
 *  (GM 2026-07-27 "지금도 GM 대기 2초에서 멈춘거 아냐?" — 실제로 멎어 있었다).
 *  경과 초는 그 순간 이후로 전부 거짓이 되지만, **몇 시에 그랬는지**는 언제 봐도 참이다.
 *  → 일하는 중(도구 호출마다 다시 그려짐)에만 경과 초를 쓰고, 멈춰 있는 상태는 시각으로 적는다. */
function clockText(ms) {
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** 경과시간 — GM 이 지목한 표시(1m 18s)의 한국어판. */
function elapsedText(sec) {
  if (sec < 60) return `${sec}초`;
  const m = Math.floor(sec / 60);
  if (m < 60) return `${m}분${sec % 60}초`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h}시간${m % 60}분` : `${Math.floor(h / 24)}일`;
}

/** 큐 한 번 읽기 — ★렌더당 파싱 1회만(성능 상한 200ms 계약 · 배107).
 *  내 항로·🆕배지·전사 막힌 배가 전부 이 한 번의 파싱을 나눠 쓴다. 추가 전수 훑기 금지. */
let _queueCache;   // 렌더당 1회만 파싱 — 프로세스가 렌더 한 번마다 새로 뜨므로 오래된 값이 남지 않는다
function loadQueue(cwd) {
  if (_queueCache !== undefined) return _queueCache;
  try {
    const q = JSON.parse(readFileSync(path.join(cwd, 'status', '_queue.json'), 'utf8'));
    _queueCache = Array.isArray(q) ? q : null;
  } catch { _queueCache = null; }
  return _queueCache;
}

/** '내 배가 GM(또는 웰리) 답을 기다리는 중'인가 — 전사 '막힌 것 우선' 칸(2026-07-28 삭제된
 *  ⚠️ 결재 대기 칸)과는 다른 개념이라 따로 둔다.
 *  전사 칸 = 남의 배가 **결재**에 걸려 있나(삭제됨) / 이 칸 = 내 배가 **답을 못 받아** 못 나아가나.
 *
 *  ★설명글의 단어로 판정하지 않는다. next 앞머리의 ⏳ 표식 **하나만** 본다.
 *    왜: 단어로 잡으면 부정문에 걸린다 — 배9260 의 next 는 "시토(**GM 결정 불필요**·먼저 진행)"
 *    인데 'GM 결정'이 들어 있다는 이유로 '답 기다리는 중'으로 잡혔다(실측). 이건 배10024
 *    ('자율 선별기 오탐 — 설명글 단어로 배를 거르고 있음')와 **같은 뿌리**의 두 번째 사례다.
 *    ⏳ 는 사람이 일부러 붙이는 선언이라 부정문에 휘둘리지 않는다. 관례는 이미 쓰이고 있어
 *    새 칸을 만들 필요도 없다(약속 L21 — 장치를 늘리지 않는다).
 *  ▸규칙: GM·웰리 답이 있어야 진행되는 배는 next 를 ⏳ 로 시작한다. */
const GM_ANSWER = /^[\s·]*⏳/;

// ── 오늘 사람에게 닿은 것 (GM 지시 2026-08-05) ──────────────────────────────────
//  왜: 상태줄이 그동안 보여준 건 전부 'AI 내부 상태'였다 — GM 판단: "지금 뭐가 돌고 있고,
//  그래서 사람에게 뭐가 달라졌나" 하나만 있으면 된다. 이미 있는 기록만 쓴다(새 로그·새 캐시
//  없음). 못 세는 항목은 그 항목만 뺀다 — 지어내지 않는다(0 이면 0으로 보인다).
function todayYmd() {
  const t = new Date();
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
}
/** 오늘 카카오 발신 건수 — logs/kakao_sent-<오늘>.log 줄 수(실무진·회장님 방으로 나간 것). */
function todayKakaoSent(cwd) {
  try {
    const p = path.join(cwd, 'logs', `kakao_sent-${todayYmd()}.log`);
    if (statSync(p).size > 3_000_000) return null;   // 비정상 비대 — 상태줄이 느려지면 안 된다
    let n = 0;
    for (const line of readFileSync(p, 'utf8').split('\n')) if (line.trim()) n++;
    return n;
  } catch { return null; }   // 오늘치 로그 아직 없음 = '모름' — 항목을 뺀다(0 을 지어내지 않는다)
}
/** 오늘 실무진 신고 회신 — status/heartbeats/cpo-staff-feedback-watch.json 의 회신_완료
 *  (시포 하트비트가 매 회차 새로 쓰는 값을 그대로 읽는다 — 새 계산 없음). */
function feedbackReplied(cwd) {
  try {
    const j = JSON.parse(readFileSync(path.join(cwd, 'status', 'heartbeats', 'cpo-staff-feedback-watch.json'), 'utf8'));
    return Number.isFinite(j.회신_완료) ? j.회신_완료 : null;
  } catch { return null; }
}
/** GM 답이 필요한 배 — 전사. 이미 로드된 큐(q)를 재사용한다(추가 파일읽기 없음).
 *  myShips 의 GM_ANSWER(⏳) 판정을 전사로 넓힌 것뿐 — 판정 로직 복제가 아니라 같은 잣대. */
function companyGmWaiting(q) {
  if (!q) return null;
  // 시로(chro)·시뽀(cfo) 배제 해제(GM 재확정 2026-08-05 — ssot/kpi.json
  // _라인분담_2026_08_05_chro_cfo_queue_revival) — 배는 살아있고 화면에서도 보여야
  // "무엇이 밀렸는지" 안다. 실행만 계속 막힌다(welly_auto_runner 러너 전용 제외).
  const EXCLUDED = [];
  let n = 0;
  for (const s of q) {
    if (!s || EXCLUDED.includes(s.clevel)) continue;
    if (s.status === 'DONE' || s.status === '완료') continue;
    if (String(s.title || '').includes('[GM보좌 제안]')) continue;
    if (GM_ANSWER.test(String(s.next || ''))) n++;
  }
  return n;
}
function todaySignals(cwd, q) {
  const parts = [];
  const kakao = todayKakaoSent(cwd);
  if (kakao != null) parts.push(`발신${kakao}`);
  const fb = feedbackReplied(cwd);
  if (fb != null) parts.push(`신고${fb}`);
  const gm = companyGmWaiting(q);
  if (gm != null) parts.push(`GM대기${gm}`);
  return parts.length ? `${D}오늘${X} ${parts.join(`${D}·${X}`)}` : null;
}

// 배 무게 — 대기 목록을 무거운 순으로 늘어놓기 위한 값(항해 세계관 priority).
const WEIGHT = { '🛳️크루즈': 3, '⛴️여객선': 2, '⛵돛단배': 1 };
function weightOf(s) { return WEIGHT[String(s.priority || '')] || 0; }

// 배의 '마지막 움직임'이 며칠 전인가 — updated_at 이 있으면 그것, 없으면 enqueued_at.// 표시용 배 번호 — 짧은번호 우선.
function noOf(s) { return s.short_no != null ? s.short_no : s.ship_no; }

/** 한 역할의 대기 배 — 무게 무거운 순, 같은 무게면 오래 기다린 순(웰리 결정 D안 ④).
 *  내 항로(myShips)와 C-Level 현황 줄(buildRoleLines)이 **같은 순서**를 봐야 하므로 여기 한 곳에서만
 *  정한다(약속 L01 — 정렬 규칙을 두 곳에 적으면 같은 배가 화면마다 다른 순서로 뜬다). */
function waitingOf(q, role) {
  return q.filter((s) => s && s.clevel === role
      && (s.status === 'PENDING' || s.status === 'STANDBY'))
    .sort((a, b) => (weightOf(b) - weightOf(a))
      || String(a.enqueued_at || '').localeCompare(String(b.enqueued_at || '')));
}

/** 대기 목록 맨 앞 = 다음에 집을 배. 자동 생성된 잔소리 배는 '다음 할 일'로 권할 성질이 아니라 뺀다. */
function nextShipOf(waiting) {
  return waiting.find((s) => !String(s.title || '').includes('[GM보좌 제안]')) || null;
}

/** 내 항로 — 진행/대기/오늘 입항 + 대기 배 번호 목록 + 🆕(남이 띄웠는데 아직 안 잡은 배). */
function myShips(q, cwd, role) {
  try {
    const mine = q.filter((s) => s && s.clevel === role);
    const t = new Date();
    const ymd = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
    const run = mine.filter((s) => s.status === 'IN_PROGRESS').length;
    const waiting = waitingOf(q, role);
    const waitNos = waiting.map(noOf).filter((n) => n != null);
    // 🆕 = 남이 나에게 띄웠는데 아직 안 잡은 배(웰리 결정 D안 ③ — "다른 C레벨도 작업 지시 현황 바로").
    //   '남이' = from 이 있고 내가 아님. '안 잡은' = PENDING(STANDBY 는 잡았다가 정박한 배라 제외).
    const fresh = waiting.filter((s) => s.status === 'PENDING' && s.from && s.from !== role).length;
    // '오늘 입항'은 보관함까지 세야 한다(GM 2026-07-24 '오늘 🏁0이 틀렸다').
    //   완료한 배는 곧 _queue_archive.json 으로 옮겨진다 → 살아있는 큐만 보면 오늘 끝낸 배가
    //   보관되는 순간 사라져 이 칸이 사실상 항상 0이었다(죽은 칸).
    //   완료 날짜 칸은 배마다 제각각(processed_at·done_at·둘 다 없으면 enqueued_at)이라 셋 다 본다.
    // ★기계가 찍어낸 배는 뺀다(GM 2026-07-24 '오늘🏁31이 부풀려졌다').
    //   판별 규칙 정본 = scripts/kpi_collector.py `_is_machine_ship`
    //   (adhoc_commit 존재 AND 제목에 "자동 발행") — KPI 완결률과 같은 잣대를 쓴다.
    //   ※JS/파이썬이라 함수를 직접 못 쓴다. 규칙이 바뀌면 정본과 함께 여기도 고칠 것.
    const isMachineShip = (s) => !!s.adhoc_commit && String(s.title || '').includes('자동 발행');
    // ★updated_at 을 날짜 후보에 넣는다 (GM 2026-07-25 "작업이 안 잡힌다") — processed_at·done_at
    //   이 더 정확하므로 그 둘이 없을 때만 차선책으로 쓴다.
    const isDoneToday = (s) => (s.status === 'DONE' || s.status === '완료')
      && String(s.processed_at || s.done_at || s.updated_at || s.enqueued_at || '').startsWith(ymd)
      && !isMachineShip(s);
    let done = mine.filter(isDoneToday).length;
    // 보관함(2.4MB)은 읽는 값이 있을 때만 연다 — 오늘 아무것도 보관되지 않았으면 파일이
    // 오늘 바뀌지도 않았으므로 열 이유가 없다(실측: 열면 +100ms, 안 열면 0ms).
    try {
      const arcPath = path.join(cwd, 'status', '_queue_archive.json');
      const st = statSync(arcPath);
      if (!new Date(st.mtimeMs).toLocaleDateString('sv-SE').startsWith(ymd)) throw 0;  // 오늘 보관 없음
      const arc = JSON.parse(readFileSync(arcPath, 'utf8'));
      if (Array.isArray(arc)) {
        const seen = new Set(mine.map((s) => s.ship_no));
        done += arc.filter((s) => s && s.clevel === role && !seen.has(s.ship_no) && isDoneToday(s)).length;
      }
    } catch { /* 보관함 못 읽음 — 살아있는 큐 기준으로만 센다 */ }
    const shortOf = {};
    for (const s of q) if (s && s.ship_no != null) shortOf[s.ship_no] = s.short_no != null ? s.short_no : s.ship_no;
    // 지금 붙들고 있는 배 = 진행중 중 가장 최근에 움직인 것.
    // ★커밋 제목에서 뽑던 번호(myLastCommit)는 '방금 끝낸 배'를 가리킬 수 있다 — 큐의 IN_PROGRESS 가 진실이다.
    const running = mine.filter((s) => s.status === 'IN_PROGRESS')
      .sort((a, b) => String(b.updated_at || b.enqueued_at || '').localeCompare(String(a.updated_at || a.enqueued_at || '')));
    const cur = running[0] ? { no: running[0].ship_no, title: running[0].title } : null;
    // ★내가 GM 답을 기다리는 배 — "어떤 답을 기다리는건데?"(GM 2026-07-27)에 답하기 위한 값.
    //   답은 이미 큐에 적혀 있었다(열린 배 18척이 next 에 'GM 확인·결재 대기'를 적어둠).
    //   상태줄이 그걸 안 읽어서 '💬GM대기'라고만 하고 무엇인지는 말하지 못했다.
    //   진행중인 배를 먼저 본다 — 지금 붙들고 있는 일이 막힌 게 가장 급하다.
    //   ★판단 근거는 next(다음 한 걸음) 한 곳만 본다 — 거기가 '무엇을 기다리는지'를 적는 자리다.
    //     제목까지 보면 자동 생성된 잔소리 배([GM보좌 제안] '30일째 미착수')가 잡혀 GM 이 답할 게
    //     없는데도 답을 기다리는 것처럼 보인다(실측으로 걸러냄).
    const askShip = [...running, ...waiting]
      .filter((s) => !String(s.title || '').includes('[GM보좌 제안]'))
      .find((s) => GM_ANSWER.test(String(s.next || '')));
    const ask = askShip ? {
      no: (shortOf[askShip.ship_no] != null) ? shortOf[askShip.ship_no] : askShip.ship_no,
      // 무엇을 기다리는지 = next 의 알맹이. 관례가 '⏳GM 확인 1건 — <실제 내용>' 꼴이라
      // 앞머리('확인 1건')가 아니라 **줄표 뒤 실제 내용**을 보여줘야 GM 이 되묻지 않는다.
      gist: (() => {
        const raw = String(askShip.next || '').replace(/^[⏳👁⚓🚢·\s]*/, '');
        const parts = raw.split('—');
        const body = (parts.length > 1 ? parts.slice(1).join('—') : parts[0]);
        return body.split(/[\n|]/)[0].replace(/^[\s:·]*/, '').trim();
      })(),
    } : null;
    // ★다음에 잡을 배 — 손이 비었을 때 '대기'라고만 적지 않고 **무엇을 집으면 되는지**까지 적는다
    //   (GM 2026-08-05 "대기없이 계속 작업할 것을 찾는 내용이 있어서, 찾아서 진행하는 걸로").
    //   판정은 nextShipOf 단일 정의(위 참고) — C-Level 현황 줄도 같은 함수를 쓴다.
    const nextShip = nextShipOf(waiting);
    const next = nextShip ? {
      no: (shortOf[nextShip.ship_no] != null) ? shortOf[nextShip.ship_no] : nextShip.ship_no,
      title: String(nextShip.title || '').replace(/^\[[^\]]*\]\s*/, '').trim(),
    } : null;
    return { run, wait: waitNos.length, waitNos, fresh, done, shortOf, cur, ask, next };
  } catch { return null; }
}

/** 내 마지막 커밋 — 몇 분 전인지 + 내가 붙들고 있는 배 번호. */
/** 배 제목을 상태줄용으로 줄인다. 앞의 '[시포] ' 같은 역할 꼬리표는 이미 옆에 닉네임이 있어 군더더기라 뗀다.
 *  한글·이모지가 섞이므로 코드포인트 단위(Array.from)로 자른다 — UTF-16 slice 는 서로게이트 페어를 쪼갠다.
 *  ※내 배 제목의 12자 고정 상한은 폐지됐다(배107 — 폭 계산 기반 가변). 이 함수는 단계 이름·전사
 *    목록의 짧은 제목처럼 '몇 자'가 명확한 곳에만 쓴다. */
function shortTitle(t, max = 12) {
  const s = String(t || '').replace(/^\[[^\]]*\]\s*/, '').trim();
  if (!s) return '';
  const chars = Array.from(s);
  return chars.length > max ? chars.slice(0, max).join('') + '…' : s;
}

function myLastCommit(cwd, role) {
  const out = git(cwd, ['log', '-60', '--format=%ct%x09%s']);
  if (!out) return null;
  const head = new RegExp(`^[a-z]+\\(${role}[^)]*\\)`, 'i');
  let mins = null, ship = null;
  for (const line of out.split('\n')) {
    const [ctRaw, subj = ''] = line.split('\t');
    if (!head.test(subj)) continue;
    const ct = Number(ctRaw);
    if (!Number.isFinite(ct)) continue;
    if (mins === null) mins = Math.max(0, Math.round((Date.now() / 1000 - ct) / 60));
    const m = subj.match(/배\s?(\d{1,5})/);
    if (m) { ship = Number(m[1]); break; }
  }
  return mins === null ? null : { mins, ship };
}

function agoText(m) {
  if (m < 60) return `${m}분전`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h}시간전` : `${Math.floor(h / 24)}일전`;
}
function agoColor(m) { return m <= 10 ? G : m <= 30 ? Y : R; }

// ── 폭 계산 (배107 · 잘림 0 계약) ──────────────────────────────────────────────
// 애매폭 문자(도형·화살표·— 등)는 전부 2칸으로 **넓게** 친다 — 넓게 재면 폭을 조금 손해볼 뿐이지만
// 좁게 재면 줄 끝이 잘린다. 잘림 0 이 우선이다.
function charW(ch) {
  const c = ch.codePointAt(0);
  if (c === 0xFE0F || c === 0x200D) return 0;   // 이모지 변형선택자·결합자 — 폭 없음
  return ((c >= 0x1100 && c <= 0x115F) || c === 0x2014 || c === 0x2026
    || (c >= 0x2190 && c <= 0x2BFF)
    || (c >= 0x2E80 && c <= 0xA4CF) || (c >= 0xAC00 && c <= 0xD7A3)
    || (c >= 0xF900 && c <= 0xFAFF) || (c >= 0xFE30 && c <= 0xFE4F)
    || (c >= 0xFF00 && c <= 0xFF60) || (c >= 0xFFE0 && c <= 0xFFE6)
    || c >= 0x1F000) ? 2 : 1;
}
function dw(s) {   // 표시 폭 — ANSI 색은 폭 0
  let w = 0;
  for (const ch of String(s).replace(/\x1b\[[0-9;]*m/g, '')) w += charW(ch);
  return w;
}
/** 문자열을 표시 폭 cols 안으로 자른다(넘치면 … 붙임). */
function fitCols(s, cols) {
  const chars = Array.from(String(s));
  let w = 0;
  for (let i = 0; i < chars.length; i++) {
    const cw = charW(chars[i]);
    if (w + cw > cols) {
      let j = i, ww = w;
      while (j > 0 && ww + 2 > cols) { j--; ww -= charW(chars[j]); }   // '…'(2칸) 자리 확보
      return j > 0 ? chars.slice(0, j).join('') + '…' : '';
    }
    w += cw;
  }
  return chars.join('');
}
/** 터미널 폭 — 상태줄은 stdout 이 파이프라 columns 가 비어 있다. 콘솔 핸들(CONOUT$)로 직접 잰다.
 *  못 재면 80(좁게) — 넘겨 짚으면 잘린다. COLUMNS 환경변수는 테스트·수동 지정용. */
function termWidth() {
  if (process.stdout.columns > 0) return process.stdout.columns;
  const env = Number(process.env.COLUMNS || '');
  if (env > 0) return env;
  try {
    const fd = openSync('\\\\.\\CONOUT$', 'w');
    const ws = new tty.WriteStream(fd);
    const c = ws.columns;
    ws.destroy();
    if (c > 0) return c;
  } catch { /* 콘솔 없음(리다이렉트 등) — 아래 폴백 */ }
  return 80;
}

/** 상태줄 한 줄 조립 — 웰리 결정 D안. 폭이 모자라면 **뒤에서부터** 접는다:
 *  전사(제목→번호→+N) → 오늘🏁 → 대기 번호목록(→개수) → 🆕 → 마지막까지 내 배(①②)만. */
function buildLine(cwd, role, transcript, sessionId) {
  // ★여유 1칸→2칸(GM 2026-08-11 "2번째 줄이 조금 짤려서 보이긴 하는데" — 1칸으로는 실측 경계에서
  //   한 칸 모자랐다). CONOUT$ 폭 실측이 창 프레임·마진 오차로 1~2칸 어긋날 수 있어 여유를 더 둔다.
  const W = termWidth() - 2;

  const q = loadQueue(cwd);
  const s = q ? myShips(q, cwd, role) : null;
  const lv = liveAction(transcript);            // ★지금 하는 일 — 보고와 무관하게 항상 움직이는 신호
  const bg = backgroundAgents(cwd, sessionId);  // ★실측 배경 에이전트(transcript 추측보다 우선)
  // 커밋 조회(git 107ms)는 꼭 필요할 때만 — 잡은 배가 없어 '방금 끝낸 배'를 대신 보여줘야 하거나,
  // 세션 기록을 못 읽어 시각 칸을 폴백해야 할 때.
  const lc = (!(s && s.cur) || !lv) ? myLastCommit(cwd, role) : null;
  const pg = lv ? null : lastProgress(cwd, role);

  // ① 닉네임 + ② 현재 배 번호 — 접지 않는 고정부. 제목은 폭 따라 가변(최소 20자).
  let head = `${B}${C}${NICK[role]}${X}`;
  let title = '';
  const busy = !!(lv && lv.working);
  if (s && s.cur) {
    const n = (s.shortOf[s.cur.no] != null) ? s.shortOf[s.cur.no] : s.cur.no;
    // ★'진행'을 글자로 적는다(GM 2026-08-11 "▶39가 대기인지 진행인지 하나도 모르겠고").
    //   기호만으로는 옆의 ⚓(대기)와 구분이 안 됐다.
    head += ` ${G}진행${n}${X}`;
    title = String(s.cur.title || '').replace(/^\[[^\]]*\]\s*/, '').trim();
  } else if (lc && lc.ship != null) {
    const n = (s && s.shortOf[lc.ship] != null) ? s.shortOf[lc.ship] : lc.ship;
    head += `${D}✓${n}${X}`;   // 진행중 없음 = 방금 끝낸 배 표시(진행중과 헷갈리지 않게 다른 기호)
  } else if (!busy) {
    // ★잡은 배도 방금 끝낸 배도 없으면 **빈칸으로 두지 않는다** (GM 2026-07-25 "없으면 없다고").
    //   단 지금 실제로 돌고 있으면 '작업없음'은 거짓말이다 — 아래 제목·시각 칸이 진실을 말한다.
    head += `${D}·작업없음${X}`;
  }
  // ★일하는 중이면 제목은 '잡아둔 배'가 아니라 **지금 받은 지시**를 쓴다(GM 지시 2026-07-27).
  //   잡은 배와 실제로 하는 일이 다를 때 배 제목은 GM 을 오히려 헷갈리게 한다(실측 재현:
  //   배81 을 잡은 채 상태줄을 고치고 있었는데 화면엔 "텔레그램 방 재편"이 떠 있었다).
  if (busy && lv.ask) title = `「${lv.ask}」`;
  // ★멈춰 있을 때도 배 제목이 아니라 **방금 한 일**을 쓴다(GM 2026-08-11 "지금도 뭔 작업을
  //   하는지 모르겠어"). 잡아둔 배와 실제로 한 일이 다른 게 보통이다 — 오늘 시토는 배39 를
  //   손도 안 댔는데 화면엔 하루 종일 "시스템 단순화 이니셔티브"가 떠 있었다.
  else {
    const w = lastWork(cwd, role).trim();
    if (w) title = w;
  }
  // 시각 칸 — ★1순위는 세션 기록에서 읽은 '지금 하는 일 + 경과'(GM 지시 2026-07-27).
  //   커밋은 일이 **끝나야** 찍히고, 진행 한 줄은 내가 손으로 써야 움직인다. 둘 다 일하는
  //   동안에는 멎어 보였다. 세션 기록만이 보고와 무관하게 항상 움직인다 → 이걸 먼저 쓴다.
  let time = '';
  if (lv) {
    const when = `${clockText(lv.at)}부터`;
    // '진행N척'(idleLoad)·'▸다음 <배>'(nextUp) 삭제 — GM 2026-08-11 "진행7척 다음 25AWS
    // 멀티테넌트ERP … 이런건 의미가없고 답답하네". 숫자와 남의 배 제목이 정작 '지금 뭐 하나'를
    // 밀어냈다. 그 자리는 아래에서 **방금 한 일**(lastWork)이 받는다.
    if (lv.working && lv.idle <= 900) {
      // ① 돌고 있음 — 도구를 부를 때마다 다시 그려지므로 여기서만 경과 초가 실제로 움직인다.
      const name = lv.act ? (ACT[lv.act.tool] || lv.act.tool) : '작업중';
      const tgt = (lv.act && lv.act.target) ? ` ${D}${shortTitle(lv.act.target, 12)}${X}` : '';
      const sec = lv.elapsed != null ? lv.elapsed : lv.idle;   // 지시 시작점을 못 찾으면 마지막 움직임 기준
      time = `${D}·${X}${G}🟢${name}${X}${tgt} ${G}${elapsedText(sec)}${X}`;
    } else if (lv.agents || bg) {
      // ★배경 에이전트가 하나라도 돌고 있으면 무조건 이 칸(웰리 결정 2026-07-27 18:30) — 아래
      //   ②③④(GM답 대기·멎음·💤대기)는 전부 '내 차례가 끝났다'는 뜻인데, 에이전트가 도는 중이면
      //   그건 거짓말이다. 전부 끝나고 웰리 차례일 때만 아래 branch 로 내려간다.
      // ★척수는 bg(출력 파일 mtime 실측)를 우선한다 — transcript 꼬리 파싱(lv.agents)은 표식이
      //   창 밖으로 밀려나면 놓친다(GM 2026-07-28 15:15 오판의 뿌리). 실측이 있으면 실측을 믿는다.
      const count = bg ? bg.count : lv.agents.count;
      // ★경과도 실측(bg.since = 지금 도는 에이전트 파일이 생긴 시각) 우선. 실측이 없으면
      //   경과를 아예 적지 않는다 — 모르는 값을 그럴듯하게 적는 게 오늘 지적받은 문제다.
      const since = (bg && bg.since) ? bg.since : null;
      const elapsed = since ? ` ${G}${elapsedText(Math.max(0, Math.round((Date.now() - since) / 1000)))}${X}` : '';
      time = `${D}·${X}${G}🟢위임중 ${count}척${X}${elapsed}`;
    } else if (lv.idle > 1800) {
      // ② 30분 넘게 멈춤 = 문제다. 2시간 넘으면 빨강.
      time = `${D}·${X}${lv.idle > 7200 ? R : Y}⏸멈춤 ${when}${X}${lastWork(cwd, role)}`;
    } else {
      // ③ 방금 끝냄 — ★'GM답 기다림'이 아니라 **방금 무엇을 했는지**를 적는다
      //    (GM 2026-08-11 "GM답 기다림 11:56부터 · 진행7척 · 다음 25… 이런건 의미가없고 답답하네").
      //    GM 이 창을 볼 때 알고 싶은 건 '내 답을 기다린다'가 아니라 '방금 뭘 했나'다.
      time = `${D}·${X}${D}방금${X}${lastWork(cwd, role)} ${D}${when}${X}`;
    }
  } else if (bg) {
    // ★transcript 를 못 읽어도(유실 등) 배경 에이전트가 실측으로 살아있으면 대기로 보이면 안 된다.
    time = `${D}·${X}${G}🟢위임중 ${bg.count}척${X}`;
  } else if (pg) {
    const icon = { start: '🚀', doing: '⏳', done: '✅', blocked: '⚓' }[pg.state] || '✅';
    time = `${D}·${X}${icon}${pg.step ? `${D}${pg.step}${X}` : ''}${agoColor(pg.mins)}${agoText(pg.mins)}${X}`;
  } else if (lc) {
    time = `${D}·${X}${agoColor(lc.mins)}${agoText(lc.mins)}${X}`;
  }

  // 선택부(접히는 순서의 역순으로 정의) — ③🆕 ④대기 목록 ⑤오늘🏁 ⑥전사 막힌 것 우선.
  const segToday = todaySignals(cwd, q);   // 오늘 사람에게 닿은 것 — GM 지시 2026-08-05, 가장 늦게 접힘
  const segNew = (s && s.fresh > 0) ? `${Y}🆕${s.fresh}${X}` : null;
  let waitNums = null;
  if (s) {
    if (s.waitNos.length) {
      const shown = s.waitNos.slice(0, 3);                      // 번호는 3개까지, 나머지 +N
      const rest = s.waitNos.length - shown.length;
      waitNums = `${D}항로${X}🚢${s.run}${D}⚓${shown.join('·')}${rest > 0 ? `+${rest}` : ''}${X}`;
    } else {
      waitNums = `${D}항로${X}🚢${s.run}${D}⚓0${X}`;
    }
  }
  // 큐를 못 읽었을 때도 침묵하지 않는다 — '일이 0건'과 '못 읽었다'는 다른 말이다.
  const waitCount = s ? `${D}항로${X}🚢${s.run}${D}⚓${s.wait}${X}` : `${D}항로${X}${Y}읽기실패${X}`;
  const segDone = s ? `${D}오늘${X}🏁${s.done}` : null;

  // 제목 최소 폭(40자 확보 — 2026-08-15 GM 재지시 "작업 내용이 중요한데" — 배107 의 20자는
  //   전사·오늘 배지가 다 들어갈 때도 우선순위를 못 이겨 20자에서 잘렸다. 작업 내용(title)이
  //   배지보다 먼저다 — 보장폭을 넓혀 배지가 더 일찍 접히게 한다.
  const titleChars = Array.from(title);
  const minTitleW = titleChars.length
    ? dw(titleChars.slice(0, 40).join('')) + (titleChars.length > 40 ? 2 : 0) : 0;
  const fixedW = dw(head) + dw(time) + (title ? 2 : 0);   // 제목 앞뒤 한 칸씩
  const SEPW = 3;                                          // ' · '
  const segsW = (arr) => arr.reduce((a, g) => a + SEPW + dw(g), 0);

  // 사다리 — 위에서부터 처음 폭에 들어가는 단을 쓴다. 마지막 단 = 내 배만.
  // ★'today'(오늘 사람에게 닿은 것)는 GM 이 가장 느껴야 할 값이라 거의 모든 단에 남긴다 —
  //   가장 좁은 창(빈 사다리 직전 단)에서야 접힌다.
  const ladder = [
    ['today', 'new', 'waitN', 'done'],
    ['today', 'new', 'waitC', 'done'],
    ['today', 'new', 'waitC'],
    ['today', 'new'],
    ['today'],
    [],
  ];
  let chosen = [];
  for (const lv of ladder) {
    const segs = [];
    if (lv.includes('today') && segToday) segs.push(segToday);
    if (lv.includes('new') && segNew) segs.push(segNew);
    if (lv.includes('waitN') && waitNums) segs.push(waitNums);
    if (lv.includes('waitC') && waitCount) segs.push(waitCount);
    if (lv.includes('done') && segDone) segs.push(segDone);    if (fixedW + minTitleW + segsW(segs) <= W) { chosen = segs; break; }
  }
  // 남는 폭은 전부 제목에게 — 12자 상한 폐지의 실체. (좁으면 20자 밑으로도 줄여 잘림만은 막는다)
  const titleBudget = W - dw(head) - dw(time) - (title ? 2 : 0) - segsW(chosen);
  const titleFit = title ? fitCols(title, Math.max(titleBudget, 0)) : '';

  const first = head + (titleFit ? ` ${D}${titleFit}${X} ` : '') + time;
  return [first.replace(/ $/, ''), ...chosen].join(`${D} · ${X}`);
}

/** 나 빼고 6 C-Level 작업현황 — 역할마다 한 줄 (GM 지시 2026-07-28
 *  "웰리가 각 C레벨 작업현황을 다 보려면, 한 칸씩 작업 내용 기준으로 나열돼야 한다").
 *  데이터 = status/worklog.jsonl(safe_commit 마다 append) — ts·role·event·detail 이 이미 있다.
 *  ★뒤에서부터 필요한 만큼만 — 6역할을 다 찾으면 그 자리에서 멈춘다(전체 파싱 금지).
 *  ★정직 표기(GM 지시): ①토큰 수는 넣지 않는다 — 다른 세션 값은 알 수 없다(모르는 값을
 *    그럴듯하게 채우는 게 오늘 지적받은 문제다). ②시간은 '마지막 기록' 개념이다 — worklog 는
 *    커밋할 때만 쌓여 커밋 사이엔 조용해 보인다. '가동 중'이라고 쓰면 거짓말이 된다.
 *    ③값이 없으면 빈칸 대신 —. */
function roleActivity(cwd, role) {
  // 배제 해제(GM 재확정 2026-08-05 — ssot/kpi.json
  // _라인분담_2026_08_05_chro_cfo_queue_revival). 시로·시뽀는 여전히 AI 에이전트가
  // 안 뜬다(worklog 가 안 쌓여 그냥 '—'로 뜬다) — 그래도 줄 자체는 남아야 밀린 게 보인다.
  const EXCLUDED = [];
  // ★내 역할도 넣는다(GM 2026-08-11 "시토창인데 시토건은 안보이니 답답한거지").
  //   전에는 내 역할을 빼고 남의 역할만 줄에 냈다 — 내 줄에 배 번호가 있으니 충분하다고 봤는데,
  //   GM 은 그 번호가 진행인지 대기인지 모르겠다고 하셨다. 내 것이 목록 맨 앞에 보여야 한다.
  const others = [role, ...Object.keys(NICK).filter((r) => r !== role && !EXCLUDED.includes(r))];
  const found = new Map();
  try {
    const p = path.join(cwd, 'status', 'worklog.jsonl');
    if (statSync(p).size <= 5_000_000) {   // 비정상 비대 — 상태줄이 느려지면 안 된다
      const lines = readFileSync(p, 'utf8').split('\n');
      for (let i = lines.length - 1; i >= 0 && found.size < others.length; i--) {
        const raw = lines[i].trim();
        if (!raw) continue;
        let rec;
        try { rec = JSON.parse(raw); } catch { continue; }
        if (!rec || found.has(rec.role) || !others.includes(rec.role)) continue;
        // ★'GM지시' 접수 레코드는 건너뛴다(2026-08-11). 그걸 잡으면 GM 이 방금 친 문장이
        //   그 역할의 '한 일'로 떠서, 화면이 "지금도 뭔 작업을 하는지 모르겠어"를 작업명으로 보여줬다.
        //   여기서 알고 싶은 건 무엇을 **했나**이므로 실제 작업 기록만 본다.
        if (String(rec.area || '') === 'GM지시') continue;
        const ts = Date.parse(rec.ts || '');
        if (!Number.isFinite(ts)) continue;
        const m = String(rec.detail || '').match(/배\s?(\d{1,6})/);
        found.set(rec.role, {
          event: String(rec.event || '').trim(),   // ★여기서 자르지 않는다 — 폭을 아는 buildRoleLines 가 자른다
          mins: Math.max(0, Math.round((Date.now() - ts) / 60000)),
          ship: m ? m[1] : null,
        });
      }
    }
  } catch { /* worklog 없거나 깨짐 — 아래서 전부 빈 값(—)으로 채운다 */ }
  return others.map((r) => ({ role: r, ...(found.get(r) || {}) }));
}

/** 내가 **방금 무엇을 했나** — 멈춰 있을 때 'GM답 기다림' 대신 적는 값(GM 2026-08-11).
 *  새 데이터를 만들지 않는다 — roleActivity 가 이미 읽어 둔 그 역할의 마지막 작업 기록을 쓴다. */
function lastWork(cwd, role) {
  try {
    const me = roleActivity(cwd, role).find((a) => a.role === role);
    if (!me || !me.event) return '';
    return ` ${C}${shortTitle(me.event, 34)}${X}`;
  } catch { return ''; }
}

/** 표시 폭(dw 기준) 만큼 공백을 채운다 — 여러 줄이 세로로 대략 맞춰 보이게. */
function padDisp(s, width) {
  const w = dw(s);
  return w < width ? s + ' '.repeat(width - w) : s;
}

/** roleActivity 를 줄 배열로 조립 — 실패해도(❗) 빈 배열만 돌려준다(호출부에서 본 줄은 안 죽는다). */
/** 역할별 **지금 움직이는가** 실측 (GM 2026-07-28 "1분전·4분전 말고 진행중 녹색으로 직관적으로").
 *  worklog 는 '커밋했을 때'만 쌓여서 실시간이 아니다 — 커밋 사이엔 일해도 조용해 보인다.
 *  실제 신호 = 각 C-Level 창의 대화기록 파일이다. 그 창이 무언가 할 때마다 append 되므로
 *  파일 수정시각이 곧 '그 창이 마지막으로 움직인 시각'이다(추측 아니라 실측).
 *  역할↔세션 대응은 이미 있는 역할 기억함(ROLE_CACHE)이 갖고 있다 — 키가 대화기록 전체 경로다.
 *  ★내용은 읽지 않는다(수 MB) — statSync 로 mtime 만 본다. */
const PAUSE_MS = 1_800_000;   // 30분 안 움직였으면 '진행중'으로 본다
function roleLiveness(cwd) {
  const out = {};
  try {
    const cache = JSON.parse(readFileSync(path.join(cwd, ROLE_CACHE), 'utf8'));
    const now = Date.now();
    for (const [file, r] of Object.entries(cache)) {
      if (typeof r !== 'string') continue;
      let age;
      try { age = now - statSync(file).mtimeMs; } catch { continue; }
      // 같은 역할의 창이 여럿이면 가장 최근 것만 — 어제 창이 오늘을 가리면 안 된다.
      if (out[r] == null || age < out[r]) out[r] = age;
    }
  } catch { /* 기억함 없음 — 아래서 상태 없이(회색) 표시된다 */ }
  return out;
}

/** roleActivity + roleLiveness 를 줄 배열로 조립 — 상태는 사람 말 3가지뿐(GM 지시 2026-08-05):
 *  **진행중 / 대기 / 오늘 없음.** '자동 N분'·'쉼 HH:MM' 처럼 설명이 필요한 표시, 배 번호·내부
 *  작업 제목은 전부 뺀다 — 지웠을 때 GM 판단이 안 바뀌는 글자였다(진단 근거는 이 파일 상단 주석).
 *  실패해도(❗) 빈 배열만 돌려준다(호출부에서 본 줄은 안 죽는다). */
function buildRoleLines(cwd, role) {
  try {
    const acts = roleActivity(cwd, role);
    const live = roleLiveness(cwd);
    for (const a of acts) a.age = live[a.role];          // ms · 없으면 undefined
    // ★worklog 커밋(a.mins)도 '살아있음' 신호다 — roleLiveness 는 **이 statusline 을 그리는
    //   인터랙티브 세션 창**의 mtime 만 본다. 배치·서브에이전트 경유로 일하면(예: .bat 훅으로
    //   커밋만 하고 창은 안 열림) 세션 파일이 며칠째 안 갱신돼도 실제로는 방금 일했을 수 있다.
    //   커밋은 이미 roleActivity() 가 읽어와 a.mins 에 갖고 있다 — 새로 읽지 않고 둘 중
    //   더 최근 것만 취한다(약속 L01 — 판정 계산 복제 금지, 있는 신호를 합칠 뿐).
    for (const a of acts) {
      const commitAge = (a.mins != null) ? a.mins * 60000 : null;
      if (commitAge != null && (a.age == null || commitAge < a.age)) a.age = commitAge;
    }
    // ★위임해서 도는 일이 최우선 신호 — 창이 닫혀 있어도 그 역할의 일은 돌고 있다(GM 2026-07-29).
    const deleg = delegatedAgents(cwd);
    for (const a of acts) a.deleg = deleg[a.role] || null;
    // 위임 중인 역할을 맨 위로. 그 다음이 최근에 움직인 역할.
    acts.sort((a, b) => (b.deleg ? 1 : 0) - (a.deleg ? 1 : 0)
      || (a.age ?? Infinity) - (b.age ?? Infinity) || (a.mins ?? Infinity) - (b.mins ?? Infinity));
    const now = new Date();
    const isToday = (ms) => {
      const d = new Date(Date.now() - ms);
      return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
    };
    // ★일하는 줄만 무슨 일인지 붙인다(GM 선택 2026-08-06). 2026-08-05 단순화로 6줄이
    //   '진행중/대기/오늘 없음'만 반복해 "회사가 뭘 하고 있나"가 안 보였다(GM "색감이 다 사라졌다").
    //   진행중 = 마지막으로 한 일 / 대기 = 다음에 집을 배. '오늘 없음'은 붙일 게 없어 그대로 짧게.
    //   큐는 여기서 한 번만 읽는다 — 역할마다 myShips 를 부르면 보관함까지 6번 읽어 상태줄이 느려진다.
    // ★역할당 한 줄이 아니라 **상태당 한 줄**로 묶는다(2026-08-06).
    //   왜: 공식 문서가 "여러 줄 + 이스케이프 코드 조합은 한 줄 평문보다 렌더링 문제가 잘 난다"고
    //   명시한다(code.claude.com/docs/en/statusline — Display glitches with escape sequences).
    //   실측 2026-08-06: 시토 창 9줄·이스케이프 90개는 색이 통째로 사라졌고, 웰리 창 3줄·78개는
    //   멀쩡했다. 같은 증상이 2026-08-04 에도 있었는데 그때는 역할 해석 실패로 잘못 짚어 재발했다.
    //   묶으면 6줄→최대 3줄, 이스케이프도 역할마다 3벌씩 붙던 것이 상태당 1벌로 준다.
    //   비어 있는 상태는 줄 자체를 안 낸다 — 줄 수를 더 줄이는 쪽이 항상 안전하다.
    const q = loadQueue(cwd);
    const run = [], wait = [];
    // ★내 것(이 창의 role)을 맨 앞에 둔다 (GM 2026-08-11 "시토CLI에서 웰리CLI 작업건을 더
    //   쉽게 알 수 있어" — 활동순 정렬(위 acts.sort)이 남을 앞세우면 정작 이 창 주인 줄이
    //   뒤로 밀려 폭 밖으로 잘려 나갔다). 활동순 정렬은 유지하되(위임중·최근 우선은 여전히
    //   유용) 내 역할만 각 줄 맨 앞으로 옮긴다 — 아래에서 절대 잘리지 않는 자리다.
    let ownRun = null, ownWait = null;
    for (const a of acts) {
      const nick = NICK[a.role];
      const mine = a.role === role;
      if (a.deleg || (a.age != null && a.age < PAUSE_MS)) {
        const item = a.event ? `${nick} ${shortTitle(a.event, 12)}` : nick;
        if (mine) ownRun = item; else run.push(item);
      } else if (a.age != null && isToday(a.age)) {
        const nx = q ? nextShipOf(waitingOf(q, a.role)) : null;
        const item = nx ? `${nick} ▸${shortTitle(nx.title, 12)}` : nick;
        if (mine) ownWait = item; else wait.push(item);
      }
      // 오늘 아무것도 안 한 역할은 줄에 안 낸다(GM 2026-08-11 "오늘 없는건 의미없고").
    }
    if (ownRun) run.unshift(ownRun);
    if (ownWait) wait.unshift(ownWait);
    const lines = [];
    const W = termWidth() - 1;
    if (run.length)  lines.push(foldRoleLine(`${G}● 진행중${X}`, run, W));
    if (wait.length) lines.push(foldRoleLine(`${Y}◐ 대기${X}`, wait, W));
    // '○ 오늘 없음' 줄 삭제(GM 2026-08-11 "오늘 없는건 의미없고").
    // 오늘 아무것도 안 한 역할을 나열해 봐야 GM 이 할 일이 생기지 않는다 — 줄만 먹었다.
    return lines;
  } catch { return []; }
}

/** 라벨 + 항목들을 터미널 폭 안으로 접는다 — buildLine 의 fitCols 는 문자 단위라 항목 중간이
 *  잘릴 수 있다(GM 이 이미 지적한 "어색한 중간 잘림"). 여기는 **항목째로만** 자른다 — 안 들어가는
 *  항목은 통째로 빼고 '+N'으로 남은 개수만 밝힌다. 맨 앞 항목(=buildRoleLines 가 넣어둔 내 역할)은
 *  폭을 넘어도 무조건 남긴다 — 없어지면 안 되는 자리다. */
function foldRoleLine(prefix, items, W) {
  const shown = [];
  let w = dw(prefix);
  for (const it of items) {
    const sep = shown.length ? ' · ' : ' ';
    w += dw(sep) + dw(it);
    if (shown.length > 0 && w > W) { w -= dw(sep) + dw(it); break; }
    shown.push(it);
  }
  const rest = items.length - shown.length;
  let out = prefix + (shown.length ? ' ' + shown.join(' · ') : '');
  if (rest > 0) out += ` ${D}+${rest}${X}`;
  return out;
}

// OMC 원문(ANSI 색 포함)에서 GM 이 지정한 5개만 지운다(2026-08-08 GM 지정). 구조·줄 수·순서·
// 색·구분자는 그대로 — 항목만 빠진다. ANSI 코드(\x1b[Nm)는 각 항목 안에 끼어 있어 와일드카드로
// 넘긴다(dw() 가 쓰는 것과 같은 패턴). omc-hud-cost.mjs 자체는 손대지 않는다(원칙 — 파일 상단).
const ANSI = '\\x1b\\[[0-9;]*m';
// [정규식, 치환문자열] 쌍 — 캡처그룹 없는 규칙은 '' 로 통째로 지우고, wk·ctx 는 라벨(그룹1)만 남긴다.
// ★String.replace 함정: 캡처그룹이 없는 정규식에 콜백을 쓰면 두 번째 인자가 매치 위치(숫자)로
//   온다 — 그걸 '치환값'으로 오인하면 지운 자리에 인덱스 숫자가 그대로 박힌다(실측: 144·208·235).
//   그래서 함수 콜백을 쓰지 않고 규칙마다 고정 치환 문자열을 쓴다.
const TRIM_RULES = [
  // ① 5시간 한도 통째로(막대+퍼센트+남은시간) + 뒤 공백 한 칸(wk 앞).
  [new RegExp(`5h:\\[(?:${ANSI}|[^\\]])*\\](?:${ANSI})*\\d+%(?:${ANSI})*\\([^)]*\\)(?:${ANSI})*\\s?`), ''],
  // ② session:NNNm 한 칸 — 앞 " | " 구분자까지 같이(자기완결 색 블록이라 안전).
  [new RegExp(`${ANSI} \\| ${ANSI}session:${ANSI}\\d+m${ANSI}`), ''],
  // ③④ wk·ctx 는 막대([...])만 지우고 퍼센트·남은시간은 남긴다.
  [new RegExp(`(wk:${ANSI})\\[(?:${ANSI}|[#-])*\\]`), '$1'],
  [new RegExp(`(ctx:)\\[(?:${ANSI}|[#-])*\\]`), '$1'],
  // ⑤ cost 줄(비용 + 코드 줄 증감) 통째로 — 색 없는 순수 텍스트.
  [/ \| cost:\$[\d.]+(?: \+\d+\/-\d+)?/, ''],
];
function trimOmcStats(raw) {
  let out = String(raw || '');
  for (const [re, rep] of TRIM_RULES) out = out.replace(re, rep);
  return out;
}

// OMC 원문(branch·모델·ctx 등 3줄) + 서브에이전트 목록(└─ 줄, 개수만큼 늘어남)을 합쳐
// 5줄이던 상태줄을 2줄로 접는다(GM 지시 2026-08-08 "5줄이나 잡아먹네"). 항목은 안 지운다 —
// └─ 목록만 빼는데, 같은 줄에 이미 'agents:N'(정확히 그 개수)이 있어 정보 손실이 없다.
// ★저장소 경로 단독 줄도 버린다(GM 재지시 2026-08-15 "● main 아래에 저장소 경로가 먼저 뜨네").
//   koreanizeBranchLine 은 branch: 와 **같은 줄**에 붙은 cwd 세그먼트만 잘라낸다 — OMC 가
//   cwd/repo 를 branch 줄과 **별도의 줄**로 내면 그 줄은 그대로 남아 다시 새 줄로 보인다.
//   실측 대신 일반 규칙으로 막는다: 아이콘·공백 말고는 드라이브 경로 토큰 하나뿐인 줄은
//   무조건 버린다(다른 값과 섞인 줄은 그대로 둔다 — 경로만 있는 줄만 노린다).
const PATH_ONLY_LINE = /^\W*[A-Za-z]:[\\/]\S*\s*$/;
function collapseOmcLines(raw) {
  const stripAnsi = (s) => String(s).replace(/\x1b\[[0-9;]*m/g, '');
  return String(raw || '').split('\n')
    .filter((l) => !stripAnsi(l).trimStart().startsWith('└'))
    .filter((l) => !PATH_ONLY_LINE.test(stripAnsi(l)))
    .join(`${D} | ${X}`);
}

/** 1번째 줄(git 상태 기호)을 한글 단어로 바꾼다(2026-08-08 GM 지시 — "기호 말고 한글로").
 *  +N(저장대기·staged) !N(미저장·modified — 실측 대부분 자동 산출물) ?N(새파일·untracked)
 *  ⇡N(미업로드·원격에 안 올라간 커밋 — GM 이 실제로 알아야 하는 값, 0 이면 OMC 가 아예 안 찍는다).
 *  ANSI 색 원문을 그대로 파싱하지 않는다 — 벗긴 평문에서 숫자만 뽑아 우리 팔레트로 다시 그린다
 *  (부호별 색 조합을 원문 그대로 보존하려는 시도는 깨지기 쉽다 — 벗기고 다시 칠하는 쪽이 안전).
 *  형식이 달라지면(OMC 업데이트 등) 원본 줄을 그대로 낸다 — 지어내지 않는다. */
function koreanizeBranchLine(raw) {
  const str = String(raw || '');
  const nl = str.indexOf('\n');
  let first = nl === -1 ? str : str.slice(0, nl);
  const restStr = nl === -1 ? '' : str.slice(nl);
  // ★branch: 앞에 낀 세그먼트(cwd 경로·repo:·hostname — 전부 '경로' 계열)는 통째로 버린다
  //   (GM 지시 2026-08-15 "브랜치 밑에 작업 경로를 또 찍어서 같은 정보가 두 번 나온다").
  //   세션은 항상 이 저장소 한 곳에서만 돌아 경로는 볼 이유가 없다. OMC 설정이 흔들려
  //   cwd·gitRepo 요소가 켜지는 순간에도 재발하지 않도록 파싱 단계에서 막는다(2026-08-13에
  //   이미 한 번 겪은 증상이라 재발 방지 = 표시 순서가 아니라 이 함수에 건다).
  //   branch: 를 아예 못 찾으면 첫 줄 전체가 경로류일 가능성이 높다 — 줄째로 버린다.
  const bIdx = first.indexOf('branch:');
  if (bIdx === -1) return restStr.replace(/^\n/, '');
  if (bIdx > 0) first = first.slice(bIdx);
  const plain = first.replace(/\x1b\[[0-9;]*m/g, '');
  const m = plain.match(/^branch:(\S+)(?:\s*\|\s*(.*))?$/);
  if (!m) return first + restStr;   // branch: 로 시작하는데 형식이 다르면 그대로(지어내지 않는다)
  const branch = m[1];
  const rest = m[2] || '';
  const staged = (rest.match(/\+(\d+)/) || [])[1];
  const modified = (rest.match(/!(\d+)/) || [])[1];
  const untracked = (rest.match(/\?(\d+)/) || [])[1];
  const ahead = (rest.match(/⇡(\d+)/) || [])[1];
  const parts = [];
  // ★커밋 안 된 파일 개수 — GM 재지시 2026-08-15. 저장대기·미저장·새파일 3종을 하나로 합쳐
  //   '변경 N'으로만 보여준다(3종 나열은 2026-08-13에 소음으로 판정돼 뺐던 것 — 이번엔 합산 1개
  //   배지라 그 판정과 부딪히지 않는다). 셋 다 없으면(=클린) 배지 자체가 없다.
  const uncommitted = [staged, modified, untracked].reduce((sum, v) => sum + (v ? Number(v) : 0), 0);
  if (uncommitted > 0) parts.push(`${D}변경 ${uncommitted}${X}`);
  // ★미업로드(⇡ ahead) — 가장 중요한 값(GM "커밋만 하고 푸시 안 하면 공용 화면이 옛것으로 남는다"
  //   가 실사고였다). 굵게 눈에 띄게. 0 이면 OMC 가 애초에 안 찍으므로 여기도 자연히 생략된다.
  if (ahead != null) parts.push(`${B}${Y}미업로드 ${ahead}${X}`);
  const newFirst = `${C}${branch}${X}` + (parts.length ? ` ${D}·${X} ${parts.join(`${D} · ${X}`)}` : '');
  return newFirst + restStr;
}

function main() {
  const input = readStdin();
  const base = collapseOmcLines(koreanizeBranchLine(trimOmcStats(omcHud(input))));

  let cwd = process.cwd(), transcript = '', sessionId = '';
  try {
    const j = JSON.parse(input);
    cwd = j?.workspace?.current_dir || j?.cwd || cwd;
    transcript = j?.transcript_path || '';
    sessionId = j?.session_id || '';
  } catch { /* 기본값 사용 */ }

  const role = resolveRole(cwd, transcript);
  // ★역할을 못 찾은 경우 — 사라지는 대신 왜 안 보이는지를 적는다(GM 2026-07-25).
  //   역할 기억함(ROLE_CACHE)이 채워지면 저절로 복구된다.
  const line = role ? buildLine(cwd, role, transcript, sessionId) : `${D}역할 확인중 · 작업표시 대기${X}`;

  // 6 C-Level 작업현황 — ★시토(cto) 창에서만 보인다 (GM 지시 2026-07-29).
  //   같은 PC 의 셸 5개가 이 스크립트 하나를 공유하므로, 막지 않으면 모든 창에 똑같이 뜬다
  //   (GM 지적 2026-07-28). 그래서 한 역할 창에만 남긴다 — 문제는 '어느 역할이냐'였다.
  //   2026-07-28 까지는 웰리(ceo) 창이었다. 2026-07-29 GM 지시로 시토(cto) 창으로 옮긴다:
  //   "시토는 AI 관련된 배편 진행 / 웰리는 실무 관련 내용 체크 및 지시사항 정리해서 전달 /
  //    시토가 statusline 에 AI C레벨들 작업들 나오게 셋팅하면 최고일듯."
  //   근거 정합: 2026-07-27 GM 확정 역할분담(ssot/kpi.json `_역할분담_2026_07_27`) —
  //   시토=전사 AI 업무 총괄 / 웰리=실무진의 현실 업무. 전 역할의 AI 창이 지금 무엇을 하고
  //   있는지는 **총괄하는 쪽**이 봐야 하는 화면이다. 웰리 창은 본 줄(자기 항로)만 남는다.
  //   ※표시 항목 소유(이 파일 상단 ①웰리 단독)는 GM 직접 지시가 상위라 그대로 반영했다 —
  //     경위는 배10341(전사 AI 업무 총괄) note 에 기록.
  // 폭이 좁으면(작은 창) 이 블록부터 접는다. worklog 가 없거나 깨져도 본 줄(line)은 절대 죽지 않게 try/catch.
  let roleBlock = '';
  if (role === 'cto') {
    try {
      if (termWidth() - 1 >= 40) {
        const rl = buildRoleLines(cwd, role);
        if (rl.length) roleBlock = '\n' + rl.join('\n');
      }
    } catch { /* 이 블록만 빠진다 */ }
  }

  // ★OMC 줄에 이어 붙이지 않고 **줄을 따로 뺀다** (GM 2026-07-24 '시모·시우·시포는 잘리는데?').
  //   같은 줄이면 폭 경쟁으로 끝에 붙은 우리 부분부터 잘린다.
  // ★맨 위는 '지금 무슨 배로 뭘 하고 있나' (GM 지시 2026-08-13 — "웰페리온 저장소 경로 나오는데
  //   의미없는데, 배편이랑 작업내용, GM지시내용으로 변경"). 전에는 git 브랜치·변경파일 수가
  //   첫 줄이라 창을 흘깃 볼 때 저장소 상태만 보이고 일하는 내용은 아래로 밀려 있었다.
  //   순서만 바꾼다 — 지운 정보는 없다(모델·맥락·미업로드는 그대로 아래 줄에 있다).
  process.stdout.write((line ? line + '\n' : '') + base + roleBlock);
}

if (process.argv[2] === '--bg-refresh-omc') {
  runBgRefreshOmc(process.argv[3], process.argv[4]);
} else {
  main();
}
