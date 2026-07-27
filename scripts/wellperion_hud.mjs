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
import { readFileSync, statSync, writeFileSync, mkdirSync, openSync, readSync, closeSync, fstatSync } from 'node:fs';
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
function loadQueue(cwd) {
  try {
    const q = JSON.parse(readFileSync(path.join(cwd, 'status', '_queue.json'), 'utf8'));
    return Array.isArray(q) ? q : null;
  } catch { return null; }
}

/** 'GM 답을 기다리는 배'를 가려내는 단 하나의 잣대 — 내 배 칸과 전사 칸이 같은 것을 쓴다(약속 L01).
 *  큐에 전용 칸이 없어 제목·next 문구로 잡는다. "(GM 승인 2026-07-25)" 같은 **이미 승인된** 표기는 제외. */
const GM_WAIT = /(GM\s?(go|승인|결재|결정))(\s?(승인|결재))?\s?(후|대기|필요|받|로|요청)|\[GM보좌 제안\]|(승인|결재|검수)\s?대기/i;

/** '내 배가 GM(또는 웰리) 답을 기다리는 중'인가 — 위 GM_WAIT(전사 결재 대기)와 다른 개념이라 따로 둔다.
 *  전사 칸 = 남의 배가 **결재**에 걸려 있나 / 이 칸 = 내 배가 **답을 못 받아** 못 나아가나.
 *
 *  ★설명글의 단어로 판정하지 않는다. next 앞머리의 ⏳ 표식 **하나만** 본다.
 *    왜: 단어로 잡으면 부정문에 걸린다 — 배9260 의 next 는 "시토(**GM 결정 불필요**·먼저 진행)"
 *    인데 'GM 결정'이 들어 있다는 이유로 '답 기다리는 중'으로 잡혔다(실측). 이건 배10024
 *    ('자율 선별기 오탐 — 설명글 단어로 배를 거르고 있음')와 **같은 뿌리**의 두 번째 사례다.
 *    ⏳ 는 사람이 일부러 붙이는 선언이라 부정문에 휘둘리지 않는다. 관례는 이미 쓰이고 있어
 *    새 칸을 만들 필요도 없다(약속 L21 — 장치를 늘리지 않는다).
 *  ▸규칙: GM·웰리 답이 있어야 진행되는 배는 next 를 ⏳ 로 시작한다. */
const GM_ANSWER = /^[\s·]*⏳/;

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
    return { run, wait: waitNos.length, waitNos, fresh, done, shortOf, cur, ask };
  } catch { return null; }
}

/** 전사 '막힌 것 우선' 목록 (웰리 결정 D안 · GM 승인 2026-07-25 — 전사 가동 점 ●●●● 대체).
 *  ① ⚠️ GM 결재 대기 배 ② ⏸ N일 정지 배 ③ 남는 폭에 정상 진행 배 — 나(role)는 뺀다(내 배는 앞에 있다).
 *  'GM 결재 대기' 판별은 큐에 전용 칸이 없어 제목·next 의 문구로 잡는다(기술 배선 = 시토):
 *    "GM go/승인/결재/결정 + 후·대기·필요·받·로·요청" 꼴, "[GM보좌 제안]", "승인/결재/검수 대기".
 *    ※"(GM 승인 2026-07-25)" 같은 **이미 승인된** 표기는 잡지 않는다. */
function companyItems(q, role) {
  const now = Date.now();
  const gmWait = GM_WAIT;
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
function buildLine(cwd, role, transcript) {
  const W = termWidth() - 1;                    // 마지막 칸 자동줄바꿈 여유 1칸
  const q = loadQueue(cwd);
  const s = q ? myShips(q, cwd, role) : null;
  const lv = liveAction(transcript);            // ★지금 하는 일 — 보고와 무관하게 항상 움직이는 신호
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
    head += `${C}▶${n}${X}`;
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
  // 시각 칸 — ★1순위는 세션 기록에서 읽은 '지금 하는 일 + 경과'(GM 지시 2026-07-27).
  //   커밋은 일이 **끝나야** 찍히고, 진행 한 줄은 내가 손으로 써야 움직인다. 둘 다 일하는
  //   동안에는 멎어 보였다. 세션 기록만이 보고와 무관하게 항상 움직인다 → 이걸 먼저 쓴다.
  let time = '';
  if (lv) {
    const when = `${clockText(lv.at)}부터`;
    if (lv.working && lv.idle <= 900) {
      // ① 돌고 있음 — 도구를 부를 때마다 다시 그려지므로 여기서만 경과 초가 실제로 움직인다.
      const name = lv.act ? (ACT[lv.act.tool] || lv.act.tool) : '작업중';
      const tgt = (lv.act && lv.act.target) ? ` ${D}${shortTitle(lv.act.target, 12)}${X}` : '';
      const sec = lv.elapsed != null ? lv.elapsed : lv.idle;   // 지시 시작점을 못 찾으면 마지막 움직임 기준
      time = `${D}·${X}${G}🟢${name}${X}${tgt} ${G}${elapsedText(sec)}${X}`;
    } else if (lv.agents) {
      // ★배경 에이전트가 하나라도 돌고 있으면 무조건 이 칸(웰리 결정 2026-07-27 18:30) — 아래
      //   ②③④(GM답 대기·멎음·💤대기)는 전부 '내 차례가 끝났다'는 뜻인데, 에이전트가 도는 중이면
      //   그건 거짓말이다. 전부 끝나고 웰리 차례일 때만 아래 branch 로 내려간다.
      const sec = Math.max(0, Math.round((Date.now() - lv.agents.since) / 1000));
      time = `${D}·${X}${G}🟢위임중 ${lv.agents.count}척${X} ${G}${elapsedText(sec)}${X}`;
    } else if (s && s.ask) {
      // ② GM 이 답해야 진행되는 상태 — ★무엇을 기다리는지까지 적는다(GM 2026-07-27
      //    "어떤 답을 기다리는건데?"). 배 번호 + 제목 핵심이라 되물을 필요가 없다.
      time = `${D}·${X}${Y}❓GM답 ${s.ask.no} ${shortTitle(s.ask.gist, 14)}${X} ${D}${when}${X}`;
    } else if (lv.idle > 1800) {
      // ③ 아무도 안 기다리는데 30분 넘게 멈춤 = **문제다**(GM 2026-07-27 "멎음은 문제인 것 같은데").
      //    기다릴 답도 없는데 일이 안 도는 것이므로 눈에 띄게 — 2시간 넘으면 빨강.
      time = `${D}·${X}${lv.idle > 7200 ? R : Y}⏸멈춤 ${when}${X}`;
    } else {
      // ④ 방금 끝냄 — 정상. 조용히 둔다.
      time = `${D}·💤대기 ${when}${X}`;
    }
  } else if (pg) {
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
  const line = role ? buildLine(cwd, role, transcript) : `${D}역할 확인중 · 작업표시 대기${X}`;

  // ★OMC 줄에 이어 붙이지 않고 **줄을 따로 뺀다** (GM 2026-07-24 '시모·시우·시포는 잘리는데?').
  //   같은 줄이면 폭 경쟁으로 끝에 붙은 우리 부분부터 잘린다.
  process.stdout.write(base + (line ? '\n' + line : ''));
}

main();
