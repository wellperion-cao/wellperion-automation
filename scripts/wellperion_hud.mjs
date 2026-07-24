#!/usr/bin/env node
/**
 * 웰페리온 statusline 래퍼 (2026-07-24 시토).
 *
 * 왜: 기존 OMC HUD 는 비용·모델·컨텍스트만 보여줘서, GM 이 "지금 일이 돌고 있는지"를
 *     화면에서 알 수 없었다("작업을 하는건지 마는건지 모르겠는데" — GM 2026-07-24).
 * 무엇: OMC HUD 출력을 그대로 살리고, 그 뒤에 **일이 돌고 있다는 신호**를 덧붙인다.
 *       🚢진행중 배 수 · ⚓대기 배 수 · 마지막 커밋이 몇 분 전이고 누가 했는지.
 *       마지막 커밋 시각이 "멈췄나?"에 가장 정확한 답이다(모든 C-Level 이 작업하며 커밋한다).
 *
 * 위치: **저장소 안**에 둔다. ~/.claude 아래에만 두면 PC 가 바뀔 때 조용히 사라진다
 *       (배9889 에서 예약 런처로 똑같이 당했다). settings.json 이 이 경로를 가리킨다.
 * 원칙: OMC HUD 파일은 건드리지 않는다(업데이트 때 덮어써진다). 이 래퍼가 감싼다.
 *       무슨 일이 생겨도 statusline 이 비지 않게 — 실패하면 OMC 출력만이라도 낸다.
 */
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const OMC_HUD = 'C:/Users/jjky0/.claude/hud/omc-hud-cost.mjs';
const NODE = process.execPath;

const D = '\x1b[2m';      // 흐리게
const C = '\x1b[36m';     // 청록
const G = '\x1b[32m';     // 초록
const Y = '\x1b[33m';     // 노랑
const R = '\x1b[31m';     // 빨강
const X = '\x1b[0m';      // 원복

function readStdin() {
  try { return readFileSync(0, 'utf8'); } catch { return '{}'; }
}

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

/** 배 현황 — 큰 JSON 을 매번 파싱하면 느리다. 상태 문자열만 센다(충분하고 빠르다). */
function ships(cwd) {
  try {
    const raw = readFileSync(path.join(cwd, 'status', '_queue.json'), 'utf8');
    const run = (raw.match(/"status":\s*"IN_PROGRESS"/g) || []).length;
    const wait = (raw.match(/"status":\s*"PENDING"/g) || []).length;
    return { run, wait };
  } catch { return null; }
}

/** 마지막 커밋: 몇 분 전 · 어느 역할이 했나(fix(cto): … 의 cto). */
function lastCommit(cwd) {
  const out = git(cwd, ['log', '-1', '--format=%ct%x09%s']);
  if (!out) return null;
  const [ctRaw, subj = ''] = out.split('\t');
  const ct = Number(ctRaw);
  if (!Number.isFinite(ct)) return null;
  const mins = Math.max(0, Math.round((Date.now() / 1000 - ct) / 60));
  const m = subj.match(/^[a-z]+\(([^)]+)\)/i);
  return { mins, who: m ? m[1] : '' };
}

function agoText(mins) {
  if (mins < 60) return `${mins}분전`;
  const h = Math.floor(mins / 60);
  if (h < 24) return `${h}시간전`;
  return `${Math.floor(h / 24)}일전`;
}

function main() {
  const input = readStdin();
  const base = omcHud(input);

  let cwd = process.cwd();
  try {
    const j = JSON.parse(input);
    cwd = j?.workspace?.current_dir || j?.cwd || cwd;
  } catch { /* 기본 cwd 사용 */ }

  const parts = [];
  const s = ships(cwd);
  if (s) parts.push(`${C}🚢${s.run}${X}${D}·⚓${s.wait}${X}`);

  const lc = lastCommit(cwd);
  if (lc) {
    // 오래 조용하면 색으로 티를 낸다 — 30분 넘게 커밋이 없으면 "멈춘 것 같다"는 신호.
    const col = lc.mins <= 10 ? G : lc.mins <= 30 ? Y : R;
    const who = lc.who ? `${D}(${lc.who})${X}` : '';
    parts.push(`${D}커밋${X}${col}${agoText(lc.mins)}${X}${who}`);
  }

  const tail = parts.length ? `${D} | ${X}${parts.join(`${D}·${X}`)}` : '';
  process.stdout.write(base + tail);
}

main();
