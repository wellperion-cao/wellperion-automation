#!/usr/bin/env node
/**
 * 웰페리온 statusline (2026-07-24 시토 · GM 지시).
 *
 * 왜: 기존 statusline(OMC HUD)은 비용·모델·컨텍스트만 보여줘 GM 이 "지금 일이 돌고 있는지"를
 *     알 수 없었다("작업을 하는건지 마는건지 모르겠는데" — GM 2026-07-24).
 *
 * 무엇을 덧붙이나 (GM 2026-07-24 선택 = '내 배 + 남은 일까지'):
 *     시토▶10026·4분전 · 항로🚢3⚓9 · 오늘🏁5 │ 전사●●●○
 *     └역할  └잡은 배 └내 마지막 커밋  └진행/대기  └오늘 입항   └나 뺀 4역할 가동
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
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';

const OMC_HUD = 'C:/Users/jjky0/.claude/hud/omc-hud-cost.mjs';
const PROJECT_LOGS = 'C:/Users/jjky0/.claude/projects/C--Users-jjky0-welperion-automation';
const NODE = process.execPath;
const ALIVE_MIN = 30;   // 이 시간 안에 움직인 세션 = 가동중(●)

// 역할 고정 순서 — 점의 자리가 늘 같아야 눈이 익는다.
// 시로(chro)·시뽀(cfo)는 GM 지시로 점에서 제외(2026-07-24). 순서 = 웰리·시토·시모·시우·시포.
const ROLES = ['ceo', 'cto', 'cmo', 'coo', 'cpo'];
const NICK = { ceo: '웰리', cfo: '시뽀', chro: '시로', cmo: '시모', coo: '시우', cpo: '시포', cto: '시토' };

const D = '\x1b[2m', C = '\x1b[36m', G = '\x1b[32m', Y = '\x1b[33m', R = '\x1b[31m';
const B = '\x1b[1m', X = '\x1b[0m';

function readStdin() { try { return readFileSync(0, 'utf8'); } catch { return '{}'; } }

function omcHud(input) {
  try {
    const r = spawnSync(NODE, [OMC_HUD], { input, encoding: 'utf8', timeout: 5000 });
    return (r.stdout || '').replace(/\s+$/, '');
  } catch { return ''; }
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

/** 지금 살아있는 역할 — 최근 움직인 transcript 들만 훑는다(오래된 파일은 건너뛰어 싸다). */
function aliveRoles() {
  const alive = new Set();
  try {
    const cut = Date.now() - ALIVE_MIN * 60000;
    for (const f of readdirSync(PROJECT_LOGS)) {
      if (!f.endsWith('.jsonl')) continue;
      const p = path.join(PROJECT_LOGS, f);
      let st;
      try { st = statSync(p); } catch { continue; }
      if (st.mtimeMs < cut) continue;
      const r = roleOf(p);
      if (r) alive.add(r);
    }
  } catch { /* 못 읽으면 빈 집합 — 점이 다 ○ 로 나온다 */ }
  return alive;
}

/** 내 항로 — 진행/대기/오늘 입항 + 배번호 짧은번호 매핑. */
function myShips(cwd, role) {
  try {
    const q = JSON.parse(readFileSync(path.join(cwd, 'status', '_queue.json'), 'utf8'));
    if (!Array.isArray(q)) return null;
    const mine = q.filter((s) => s && s.clevel === role);
    const t = new Date();
    const ymd = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
    const run = mine.filter((s) => s.status === 'IN_PROGRESS').length;
    const wait = mine.filter((s) => s.status === 'PENDING' || s.status === 'STANDBY').length;
    // '오늘 입항'은 보관함까지 세야 한다(GM 2026-07-24 '오늘 🏁0이 틀렸다').
    //   완료한 배는 곧 _queue_archive.json 으로 옮겨진다 → 살아있는 큐만 보면 오늘 끝낸 배가
    //   보관되는 순간 사라져 이 칸이 사실상 항상 0이었다(죽은 칸).
    //   완료 날짜 칸은 배마다 제각각(processed_at·done_at·둘 다 없으면 enqueued_at)이라 셋 다 본다.
    // ★기계가 찍어낸 배는 뺀다(GM 2026-07-24 '오늘🏁31이 부풀려졌다').
    //   문의 스냅샷(3분마다)·주차매출 같은 무인 예약 스크립트가 만든 배까지 세면 실무 성과가 아니라
    //   가동 횟수가 된다. 판별 규칙 정본 = scripts/kpi_collector.py `_is_machine_ship`
    //   (adhoc_commit 존재 AND 제목에 "자동 발행") — KPI 완결률과 같은 잣대를 쓴다.
    //   ※JS/파이썬이라 함수를 직접 못 쓴다. 규칙이 바뀌면 정본과 함께 여기도 고칠 것.
    const isMachineShip = (s) => !!s.adhoc_commit && String(s.title || '').includes('자동 발행');
    const isDoneToday = (s) => (s.status === 'DONE' || s.status === '완료')
      && String(s.processed_at || s.done_at || s.enqueued_at || '').startsWith(ymd)
      && !isMachineShip(s);
    let done = mine.filter(isDoneToday).length;
    // 보관함(2.4MB)은 읽는 값이 있을 때만 연다 — 오늘 아무것도 보관되지 않았으면 파일이
    // 오늘 바뀌지도 않았으므로 열 이유가 없다(실측: 열면 +100ms, 안 열면 0ms).
    // 못 읽어도 살아있는 큐 기준 숫자는 그대로 나온다(0으로 무너뜨리지 않는다).
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
    // 지금 붙들고 있는 배 = 진행중 중 가장 최근에 움직인 것. 번호만으로는 무슨 일인지 알 수 없어
    // 제목까지 같이 낸다(GM 2026-07-24 '작업중인 내용은 안 나오는건가?').
    // ★커밋 제목에서 뽑던 번호(myLastCommit)는 '방금 끝낸 배'를 가리킬 수 있다 — 큐의 IN_PROGRESS 가 진실이다.
    const running = mine.filter((s) => s.status === 'IN_PROGRESS')
      .sort((a, b) => String(b.updated_at || b.enqueued_at || '').localeCompare(String(a.updated_at || a.enqueued_at || '')));
    const cur = running[0] ? { no: running[0].ship_no, title: shortTitle(running[0].title) } : null;
    return { run, wait, done, shortOf, cur };
  } catch { return null; }
}

/** 내 마지막 커밋 — 몇 분 전인지 + 내가 붙들고 있는 배 번호.
 *  시각은 '가장 최근 커밋'에서 가져오되, 배 번호는 제목에 번호가 없을 수도 있어
 *  번호가 나올 때까지 내 커밋을 거슬러 찾는다(제목이 '배 현황' 같은 말이면 번호가 없다). */
/** 배 제목을 상태줄용으로 줄인다. 앞의 '[시포] ' 같은 역할 꼬리표는 이미 옆에 닉네임이 있어 군더더기라 뗀다.
 *  ★표시문자 12자 상한(GM 07-24 폭 사고 재발 방지) — 한글·이모지가 섞이므로 코드포인트 단위(Array.from)로
 *  자른다. 바이트/UTF-16 slice 는 서로게이트 페어(일부 이모지)를 반으로 쪼개 깨질 수 있다. */
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

function main() {
  const input = readStdin();
  const base = omcHud(input);

  let cwd = process.cwd(), transcript = '';
  try {
    const j = JSON.parse(input);
    cwd = j?.workspace?.current_dir || j?.cwd || cwd;
    transcript = j?.transcript_path || '';
  } catch { /* 기본값 사용 */ }

  const role = roleOf(transcript);
  const parts = [];

  if (role) {
    const lc = myLastCommit(cwd, role);
    const s = myShips(cwd, role);
    let head = `${B}${C}${NICK[role]}${X}`;
    // 지금 붙들고 있는 배(큐 IN_PROGRESS)를 우선 — 번호 + 무슨 일인지. 진행중이 없을 때만
    // 마지막 커밋에서 뽑은 번호로 폴백(그건 '방금 끝낸 배'일 수 있어 뒤로 뺀다).
    if (s && s.cur) {
      const n = (s.shortOf[s.cur.no] != null) ? s.shortOf[s.cur.no] : s.cur.no;
      head += `${C}▶${n}${X}` + (s.cur.title ? ` ${D}${s.cur.title}${X} ` : '');   // 제목=흐리게(번호·시간 먼저 눈에), 뒤 한 칸은 '재설계…·7분전'처럼 붙어 읽히지 않게
    } else if (lc && lc.ship != null) {
      const n = (s && s.shortOf[lc.ship] != null) ? s.shortOf[lc.ship] : lc.ship;
      head += `${D}✓${n}${X}`;   // 진행중 없음 = 방금 끝낸 배 표시(진행중과 헷갈리지 않게 다른 기호)
    }
    if (lc) head += `${D}·${X}${agoColor(lc.mins)}${agoText(lc.mins)}${X}`;
    parts.push(head);
    if (s) {
      parts.push(`${D}항로${X}🚢${s.run}${D}⚓${s.wait}${X}`);
      parts.push(`${D}오늘${X}🏁${s.done}`);
    }
  }

  // 전사 — 나를 뺀 나머지가 지금 도는지. 자리 순서 고정(웰리·시토·시모·시우·시포 중 나 제외).
  const alive = aliveRoles();
  const dots = ROLES.filter((r) => r !== role)
    .map((r) => (alive.has(r) ? `${G}●${X}` : `${D}○${X}`)).join('');
  if (dots) parts.push(`${D}전사${X}${dots}`);

  // ★같은 줄에 이어 붙이지 않고 **줄을 따로 뺀다** (GM 2026-07-24 '시모·시우·시포는 잘리는데?').
  //   OMC HUD 는 서브에이전트가 돌면 그 목록까지 찍어 줄이 길어진다. 거기에 이어 붙이면
  //   터미널 폭을 넘겨 **끝에 붙은 우리 부분부터 잘린다** — 정작 제일 보고 싶은 게 사라진다.
  //   별도 줄이면 폭 경쟁이 없어 어느 창에서도 온전히 보인다(OMC 도 이미 여러 줄을 쓴다).
  process.stdout.write(base + (parts.length ? '\n' + parts.join(`${D} · ${X}`) : ''));
}

main();
