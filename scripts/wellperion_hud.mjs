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
 * 무엇을 보여주나 (웰리 결정 · GM 승인 D안 2026-07-25 — 배107):
 *     시토▶107 상태줄 재설계 — 한 줄에…·✅단계3분전 🆕2 · 항로🚢8⚓43·44·27+34 · 오늘🏁11 · ⚠️시우▸35 결재4일 ⏸시모▸10 16일 +7
 *     └역할 └잡은 배+제목(12자 상한 폐지 — 폭 가변·최소 20자) └새 지시 └대기 배 번호(무거운 순) └오늘 입항 └전사 '막힌 것 우선'
 *
 *   ★전사 가동 점(●●●●)은 삭제 — GM 판단 "정보량 0". 살아있음은 커밋 시각으로 이미 보이고,
 *     정작 안 보이던 건 "무엇이 멈춰 있나"였다(결재 60일·검수대기 8건). 그 자리를 이렇게 채운다:
 *     ① GM 결재 대기 배(⚠️ 역할▸번호 결재N일) ② N일 정지 배(⏸ 역할▸번호 N일) ③ 남는 폭에 정상 진행 배.
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
import { spawnSync } from 'node:child_process';
import { readFileSync, statSync, writeFileSync, mkdirSync, openSync } from 'node:fs';
import path from 'node:path';
import tty from 'node:tty';

const OMC_HUD = 'C:/Users/jjky0/.claude/hud/omc-hud-cost.mjs';
const NODE = process.execPath;
const STALL_DAYS = 3;   // 진행중인데 이 날수 이상 안 움직인 배 = ⏸ 정지로 본다

// 역할 기억함 — 한 번 알아낸 역할을 세션별로 적어둔다(2026-07-25 GM 지시).
//   왜: roleOf 는 transcript **첫 60,000자**에서 부팅 문구(ai-<role>.md)를 찾는다. 대화가
//   길어져 앞머리가 잘리거나 이어받은 창이면 그 문구가 사라져 역할을 못 찾고, 그러면 상태줄에서
//   내 줄이 **통째로 사라진다**(GM 2026-07-25 "나올 때도 있고 안 나올 때도 있는데"). 한 번
//   알아냈으면 기억해 두면 그 뒤로는 안 사라진다. 기억함이 없어도 동작은 같다(그냥 다시 찾는다).
const ROLE_CACHE = 'tmp/hud_role_cache.json';   // .gitignore 대상(tmp/) — 커밋 오염 없음
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
// 캐시 위치는 이 스크립트 위치에서 잡는다(<repo>/scripts/ → <repo>/tmp/).
// 상태줄은 cwd 가 매번 다를 수 있어 상대경로로 두면 캐시가 흩어진다.
const REPO_ROOT = path.dirname(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')));
const OMC_CACHE = path.join(REPO_ROOT, 'tmp', 'hud_omc_cache.json');   // .gitignore 대상(tmp/)

function omcHud(input) {
  const cachePath = OMC_CACHE;
  // 1) 살아있는 캐시가 있으면 프로세스를 띄우지 않는다.
  try {
    const c = JSON.parse(readFileSync(cachePath, 'utf8'));
    if (c && typeof c.out === 'string' && (Date.now() - (c.at || 0)) < OMC_CACHE_TTL_MS) return c.out;
  } catch { /* 캐시 없음·깨짐 — 그냥 새로 계산한다 */ }

  // 2) 새로 계산. timeout 을 5s → 2.5s 로 줄인다 — 5초를 다 쓰면 어차피 상태줄 상한을 넘겨
  //    그 회차는 버려진다. 그럴 바엔 일찍 포기하고 직전 값이라도 내보내는 편이 화면이 안 빈다.
  let out = '';
  try {
    const r = spawnSync(NODE, [OMC_HUD], { input, encoding: 'utf8', timeout: 2500 });
    out = (r.stdout || '').replace(/\s+$/, '');
  } catch { out = ''; }

  // 3) 계산이 빈손이면 만료된 캐시라도 쓴다(빈 화면보다 조금 늦은 값이 낫다).
  if (!out) {
    try {
      const c = JSON.parse(readFileSync(cachePath, 'utf8'));
      if (c && typeof c.out === 'string') return c.out;
    } catch { /* 없으면 빈 문자열 그대로 */ }
    return out;
  }

  try {
    mkdirSync(path.dirname(cachePath), { recursive: true });
    writeFileSync(cachePath, JSON.stringify({ at: Date.now(), out }), 'utf8');
  } catch { /* 캐시 못 써도 표시는 정상 — 다음 회차에 다시 계산할 뿐 */ }
  return out;
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
    const head = readFileSync(transcript, 'utf8').slice(0, 60000);
    const m = head.match(/ai-(ceo|cfo|chro|cmo|coo|cpo|cto)\.md/);
    return m ? m[1] : null;
  } catch { return null; }
}

/** 역할 — 찾아보고, 못 찾으면 기억함에서 꺼낸다. 찾았으면 기억함에 적어둔다.
 *  기억함을 못 읽거나 못 쓰더라도 roleOf 결과 그대로 동작한다(기억함은 덤이지 의존이 아니다). */
function resolveRole(cwd, transcript) {
  const found = roleOf(transcript);
  if (!transcript) return found;
  // 기억함 열쇠는 경로 표기를 통일한다 — 같은 파일이 `C:\..\a.jsonl` 과 `C:/../a.jsonl` 로
  // 들어오면 다른 세션으로 오인해 기억이 헛돈다(윈도우는 둘 다 유효한 표기다).
  const key = String(transcript).replace(/\\/g, '/').toLowerCase();
  const cachePath = path.join(cwd, ROLE_CACHE);

  let cache = {};
  try { cache = JSON.parse(readFileSync(cachePath, 'utf8')) || {}; } catch { /* 없으면 빈 것 */ }
  if (typeof cache !== 'object' || Array.isArray(cache)) cache = {};

  if (!found) return cache[key] || null;   // 못 찾았으면 기억해 둔 것으로 버틴다
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

/** 큐 한 번 읽기 — ★렌더당 파싱 1회만(성능 상한 200ms 계약 · 배107).
 *  내 항로·🆕배지·전사 막힌 배가 전부 이 한 번의 파싱을 나눠 쓴다. 추가 전수 훑기 금지. */
function loadQueue(cwd) {
  try {
    const q = JSON.parse(readFileSync(path.join(cwd, 'status', '_queue.json'), 'utf8'));
    return Array.isArray(q) ? q : null;
  } catch { return null; }
}

// 배 무게 — 대기 목록을 무거운 순으로 늘어놓기 위한 값(항해 세계관 priority).
const WEIGHT = { '🛳️크루즈': 3, '⛴️여객선': 2, '⛵돛단배': 1 };
function weightOf(s) { return WEIGHT[String(s.priority || '')] || 0; }

// 배의 '마지막 움직임'이 며칠 전인가 — updated_at 이 있으면 그것, 없으면 enqueued_at.
function idleDays(s, now) {
  const t = Date.parse(String(s.updated_at || s.enqueued_at || ''));
  return Number.isFinite(t) ? Math.max(0, Math.floor((now - t) / 86400000)) : 0;
}
// 표시용 배 번호 — 짧은번호 우선.
function noOf(s) { return s.short_no != null ? s.short_no : s.ship_no; }

/** 내 항로 — 진행/대기/오늘 입항 + 대기 배 번호 목록 + 🆕(남이 띄웠는데 아직 안 잡은 배). */
function myShips(q, cwd, role) {
  try {
    const mine = q.filter((s) => s && s.clevel === role);
    const t = new Date();
    const ymd = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
    const run = mine.filter((s) => s.status === 'IN_PROGRESS').length;
    // 대기 배 — 번호를 무게 무거운 순으로 늘어놓는다(웰리 결정 D안 ④). 같은 무게면 오래 기다린 순.
    const waiting = mine.filter((s) => s.status === 'PENDING' || s.status === 'STANDBY')
      .sort((a, b) => (weightOf(b) - weightOf(a))
        || String(a.enqueued_at || '').localeCompare(String(b.enqueued_at || '')));
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
    return { run, wait: waitNos.length, waitNos, fresh, done, shortOf, cur };
  } catch { return null; }
}

/** 전사 '막힌 것 우선' 목록 (웰리 결정 D안 · GM 승인 2026-07-25 — 전사 가동 점 ●●●● 대체).
 *  ① ⚠️ GM 결재 대기 배 ② ⏸ N일 정지 배 ③ 남는 폭에 정상 진행 배 — 나(role)는 뺀다(내 배는 앞에 있다).
 *  'GM 결재 대기' 판별은 큐에 전용 칸이 없어 제목·next 의 문구로 잡는다(기술 배선 = 시토):
 *    "GM go/승인/결재/결정 + 후·대기·필요·받·로·요청" 꼴, "[GM보좌 제안]", "승인/결재/검수 대기".
 *    ※"(GM 승인 2026-07-25)" 같은 **이미 승인된** 표기는 잡지 않는다. */
function companyItems(q, role) {
  const now = Date.now();
  const gmWait = /(GM\s?(go|승인|결재|결정))(\s?(승인|결재))?\s?(후|대기|필요|받|로|요청)|\[GM보좌 제안\]|(승인|결재|검수)\s?대기/i;
  const A = [], P = [], N = [];
  for (const s of q) {
    if (!s || s.clevel === role || !NICK[s.clevel]) continue;
    const st = s.status;
    if (st === 'PENDING' || st === 'STANDBY') {
      if (!gmWait.test(`${s.title || ''} ${s.next || ''}`)) continue;
      const d = idleDays(s, now);
      A.push({ d, pre: `${Y}⚠️${NICK[s.clevel]}▸${noOf(s)}${X}`, label: `${Y}결재${d}일${X}` });
    } else if (st === 'IN_PROGRESS') {
      const d = idleDays(s, now);
      if (d >= STALL_DAYS) P.push({ d, pre: `${Y}⏸${NICK[s.clevel]}▸${noOf(s)}${X}`, label: `${Y}${d}일${X}` });
      else N.push({ d, pre: `${D}${NICK[s.clevel]}▸${noOf(s)}${X}`, label: `${D}${shortTitle(s.title, 6)}${X}` });
    }
  }
  A.sort((a, b) => b.d - a.d);       // 오래 막힌 결재부터
  P.sort((a, b) => b.d - a.d);       // 오래 멈춘 배부터
  N.sort((a, b) => a.d - b.d);       // 정상 진행은 최근에 움직인 배부터
  return [...A, ...P, ...N];
}

/** 전사 목록을 주어진 폭에 채운다 — 뒤에서부터 접기: 제목→번호→생략(+N). (웰리 결정 D안) */
function buildCompany(items, budget) {
  if (!items.length || budget < 4) return '';
  const out = [];
  let used = 0, withLabel = true;
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    const restN = items.length - 1 - i;
    const tail = restN > 0 ? dw(`+${restN}`) + 1 : 0;   // 뒤에 올 '+N' 자리 예약 — 잘림 0
    let cand = withLabel ? `${it.pre} ${it.label}` : it.pre;
    let cw = dw(cand) + (out.length ? 1 : 0);
    if (withLabel && used + cw + tail > budget) {        // 제목부터 접는다
      withLabel = false;
      cand = it.pre;
      cw = dw(cand) + (out.length ? 1 : 0);
    }
    if (used + cw + tail > budget) {                     // 번호도 안 들어가면 생략(+N)
      if (!out.length) return '';                        // 한 척도 못 실으면 '+N'만 덜렁 내지 않는다 — 통째로 접는다
      out.push(`${D}+${items.length - i}${X}`);
      break;
    }
    out.push(cand);
    used += cw;
  }
  return out.join(' ');
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
function buildLine(cwd, role) {
  const W = termWidth() - 1;                    // 마지막 칸 자동줄바꿈 여유 1칸
  const q = loadQueue(cwd);
  const s = q ? myShips(q, cwd, role) : null;
  const lc = myLastCommit(cwd, role);
  const pg = lastProgress(cwd, role);

  // ① 닉네임 + ② 현재 배 번호 — 접지 않는 고정부. 제목은 폭 따라 가변(최소 20자).
  let head = `${B}${C}${NICK[role]}${X}`;
  let title = '';
  if (s && s.cur) {
    const n = (s.shortOf[s.cur.no] != null) ? s.shortOf[s.cur.no] : s.cur.no;
    head += `${C}▶${n}${X}`;
    title = String(s.cur.title || '').replace(/^\[[^\]]*\]\s*/, '').trim();
  } else if (lc && lc.ship != null) {
    const n = (s && s.shortOf[lc.ship] != null) ? s.shortOf[lc.ship] : lc.ship;
    head += `${D}✓${n}${X}`;   // 진행중 없음 = 방금 끝낸 배 표시(진행중과 헷갈리지 않게 다른 기호)
  } else {
    // ★잡은 배도 방금 끝낸 배도 없으면 **빈칸으로 두지 않는다** (GM 2026-07-25 "없으면 없다고").
    head += `${D}·작업없음${X}`;
  }
  // 시각 칸 — '방금 넘긴 단계'가 있으면 그걸 쓰고, 없을 때만 커밋 시각으로 폴백한다.
  //   커밋은 일이 **끝나야** 찍히므로 일하는 중에는 멈춰 보였다. 진행 한 줄이 더 진실에 가깝다.
  let time = '';
  if (pg) {
    const icon = { start: '🚀', doing: '⏳', done: '✅', blocked: '⚓' }[pg.state] || '✅';
    time = `${D}·${X}${icon}${pg.step ? `${D}${pg.step}${X}` : ''}${agoColor(pg.mins)}${agoText(pg.mins)}${X}`;
  } else if (lc) {
    time = `${D}·${X}${agoColor(lc.mins)}${agoText(lc.mins)}${X}`;
  }

  // 선택부(접히는 순서의 역순으로 정의) — ③🆕 ④대기 목록 ⑤오늘🏁 ⑥전사 막힌 것 우선.
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
  const coItems = q ? companyItems(q, role) : [];

  // 제목 최소 폭(20자 확보 — 배107) — 제목이 그보다 짧으면 그 길이만큼만.
  const titleChars = Array.from(title);
  const minTitleW = titleChars.length
    ? dw(titleChars.slice(0, 20).join('')) + (titleChars.length > 20 ? 2 : 0) : 0;
  const fixedW = dw(head) + dw(time) + (title ? 2 : 0);   // 제목 앞뒤 한 칸씩
  const SEPW = 3;                                          // ' · '
  const segsW = (arr) => arr.reduce((a, g) => a + SEPW + dw(g), 0);

  // 사다리 — 위에서부터 처음 폭에 들어가는 단을 쓴다. 마지막 단 = 내 배만.
  const ladder = [
    ['new', 'waitN', 'done', 'co'],
    ['new', 'waitN', 'done'],
    ['new', 'waitC', 'done'],
    ['new', 'waitC'],
    ['new'],
    [],
  ];
  let chosen = [];
  for (const lv of ladder) {
    const segs = [];
    if (lv.includes('new') && segNew) segs.push(segNew);
    if (lv.includes('waitN') && waitNums) segs.push(waitNums);
    if (lv.includes('waitC') && waitCount) segs.push(waitCount);
    if (lv.includes('done') && segDone) segs.push(segDone);
    if (lv.includes('co')) {
      const budget = W - fixedW - minTitleW - segsW(segs) - SEPW;
      const co = buildCompany(coItems, budget);
      if (!co) continue;                        // 전사가 한 척도 안 들어가면 이 단은 접는다
      segs.push(co);
    }
    if (fixedW + minTitleW + segsW(segs) <= W) { chosen = segs; break; }
  }
  // 남는 폭은 전부 제목에게 — 12자 상한 폐지의 실체. (좁으면 20자 밑으로도 줄여 잘림만은 막는다)
  const titleBudget = W - dw(head) - dw(time) - (title ? 2 : 0) - segsW(chosen);
  const titleFit = title ? fitCols(title, Math.max(titleBudget, 0)) : '';

  const first = head + (titleFit ? ` ${D}${titleFit}${X} ` : '') + time;
  return [first.replace(/ $/, ''), ...chosen].join(`${D} · ${X}`);
}

function main() {
  const input = readStdin();
  const base = omcHud(input);

  let cwd = process.cwd(), transcript = '';
  try {
    const j = JSON.parse(input);
    cwd = j?.workspace?.current_dir || j?.cwd || cwd;
    transcript = j?.transcript_path || '';
  } catch { /* 기본값 사용 */ }

  const role = resolveRole(cwd, transcript);
  // ★역할을 못 찾은 경우 — 사라지는 대신 왜 안 보이는지를 적는다(GM 2026-07-25).
  //   역할 기억함(ROLE_CACHE)이 채워지면 저절로 복구된다.
  const line = role ? buildLine(cwd, role) : `${D}역할 확인중 · 작업표시 대기${X}`;

  // ★OMC 줄에 이어 붙이지 않고 **줄을 따로 뺀다** (GM 2026-07-24 '시모·시우·시포는 잘리는데?').
  //   같은 줄이면 폭 경쟁으로 끝에 붙은 우리 부분부터 잘린다.
  process.stdout.write(base + (line ? '\n' + line : ''));
}

main();
