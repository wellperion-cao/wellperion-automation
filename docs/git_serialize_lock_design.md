# 동시 git 커밋 직렬화 lock 설계안 (B)

> 작성: AI CTO(시토) · 2026-06-15 · task CTO-2026-06-13-QUEUE-WATCHER-HARDENING-NEXT ②
> 상태: **설계 완료 · 라이브 적용은 GM 게이트(bot.py 재기동)**

## 1. 문제
여러 프로세스가 직렬화 없이 `git add → commit → push`를 동시 수행 → `.git/index.lock` 경쟁, 부분 커밋, working tree 손상(운영부 1400줄 유실·가이드허브 깨짐의 재발원). pre-commit truncation 게이트는 *catastrophic 잘림*만 막을 뿐 **동시성 자체는 못 막음**.

## 2. 실측 위험 쌍 (조사 결과)
| 순위 | 쌍 | 공유 자원 | 현 대책 |
|---|---|---|---|
| 1 (즉각) | `bot.py`(승인 콜백) ↔ IG 발행(`--once`, 봇이 호출) | `review_queue.json` + git 시퀀스 | 없음(.publish.lock은 파일쓰기만) |
| 2 (간접) | `ceo_morning_pipeline.py`(08시 read) ↔ `clevel_post_action.py`(세션종료 write) | `status/*.json`·`_queue.json` 부분읽기 | 없음 |
| 3 (저위험) | 다수 `clevel_post_action` 세션종료 근접 | `status/*.json` | autostash(부분) |

**상시가동 프로세스 = bot.py(콜백), 나머지는 단발/폴링.** Windows라 `fcntl` 불가.

## 3. 설계 — 단일 글로벌 git lock
모든 git 쓰기 주체가 **하나의 크로스-프로세스 lock**을 거쳐 `add→commit→(pull --autostash)→push` **전체 시퀀스를 임계구역**으로 실행.

### 3.1 기제: atomic `mkdir` 디렉터리 lock
- 경로: `<repo>/.locks/git.lock/` (디렉터리). `os.mkdir`는 Windows에서 **원자적** — 존재 시 `FileExistsError`.
- 락 안에 `holder.txt` = `pid|host|iso_ts|holder_name` 기록(진단·stale 판정용).
- `fcntl`/`msvcrt` 불필요(이식성·단순성). 의존성 0.

### 3.2 공유 모듈 `scripts/git_lock.py` (신규)
```python
# 핵심 인터페이스 (의사코드)
ACQUIRE_TIMEOUT = 90      # 락 획득 대기 한계(초) — 초과 시 loud fail (무방비 진행 금지)
STALE_SECONDS   = 300     # 보유 한계 — 느린 push 허용하되 크래시 회수
POLL            = 0.2

class GitLock:                       # context manager
    def __enter__():
        loop:
            try os.mkdir(lockdir); write holder.txt; return
            except FileExistsError:
                if _is_stale(): _steal()      # ts age>STALE 또는 PID 죽음(ctypes OpenProcess) → rmtree 후 재시도
                elif waited>ACQUIRE_TIMEOUT: raise GitLockTimeout
                else: sleep(POLL)
    def __exit__(): rmtree(lockdir)  # 항상 해제(예외에도)

def git_commit_push(paths, message, holder, pull_autostash=True, push=True):
    with GitLock(holder):
        git add <paths>;  git commit -m <message>
        if pull_autostash: git pull --rebase --autostash
        if push:           git push
```
- **stale 회수 2중**: ① 타임스탬프 age>STALE ② PID 생존검사(Windows `ctypes.OpenProcess`, 실패=죽음). 크래시 시 즉시 회수, 평시 false-steal 방지.
- **획득 실패 = 시끄럽게 실패**(로그+예외). 절대 무락 진행 금지(부분커밋 원천차단).
- 로그: `logs/git_lock.log` (획득·해제·steal·timeout, 30일 회전).

### 3.3 통합 지점
| 주체 | 변경 | 재기동 |
|---|---|---|
| `clevel_post_action.py` | raw git → `git_commit_push(...)` | 불필요(단발) |
| IG 발행(`ig_review_publish_watcher.py` 등) | 동상 | 불필요(단발/--once) |
| `ceo_morning_pipeline.py` | git 쓰기 있으면 동상 / read는 락 안에서 스냅샷 읽기 권장 | 불필요(단발) |
| `bot.py` | 콜백의 git 시퀀스 → `git_commit_push(...)` | **필요(상시 프로세스)=GM 게이트** |

### 3.4 pre-commit 훅 데드락 회피 (중요)
pre-commit 훅(truncation guard 등 가드)은 **이미 락을 쥔 commit 프로세스 내부**에서 실행됨 → 훅은 **절대 락을 재획득하지 않는다**(재진입 금지). 훅의 `git add`(ship_no·_queue 미러 등)는 같은 프로세스 임계구역 안이라 안전. 락은 오직 최상위 시퀀스에서만 잡는다.

## 4. 파라미터 근거
- `STALE=300s`: 느린 push(네트워크) 허용 상한 > 정상 보유시간(수초). PID 생존검사로 크래시는 더 빨리 회수.
- `ACQUIRE_TIMEOUT=90s`: 정상 경합(타 프로세스 push 대기)은 90s 내 해소. 초과 = 비정상 → 실패시켜 사람이 인지.
- 둘 다 `git_lock.py` 상단 상수(환경변수 override 가능).

## 5. 단계별 롤아웃 (GM 게이트 분리)
- **P1 (무영향):** `git_lock.py` 작성 + 자기검증 테스트(동시 2~3 프로세스가 같은 파일 커밋 → 직렬화·무손상 실증). **GM 게이트 없음.**
- **P2 (저위험):** 단발 주체(clevel_post_action·IG·pipeline) 전환. 재기동 불필요. 라이브 1회 실측.
- **P3 (GM 게이트): [코드 완료 2026-06-16]** `bot.py` 승인 콜백의 4분리 git 호출(add/commit/pull/push)을 단일 `GitLock` 임계구역 동기 시퀀스 `_git_seq_locked`로 교체, `asyncio.to_thread`로 호출(블로킹이 봇 이벤트 루프 비차단). 위험쌍#1(콜백↔IG `--once`) 차단. 검증: py_compile PASS·`_git_async` 잔재 0·GitLock 획득/해제 라이브 PASS. **라이브 적용 보류 = 현 봇 인스턴스(PID 2968)가 RunLevel=Highest로 떠 사용자권한 세션에서 kill 불가(elevation 벽).** 새 코드는 **다음 아침 부팅·로그온 시 `WellperionTelegramBot` 작업(elevated)이 자동 재기동하며 자연 로드**(야간 PC종료로 선행봇 없어 충돌 없음), 또는 GM 재부팅 시 즉시. 재기동 후 라이브 검증 = 다음 콘텐츠 승인 1건 + 동시 IG `--once`에서 `git_lock.log` 직렬화 확인.

## 6. 리스크·롤백
- 데드락: 락은 단일 자원·재진입 금지·항상 `__exit__` 해제·stale 회수 2중 → 영구 데드락 불가. 최악도 STALE(300s) 후 자동 회수.
- 성능: push까지 직렬화로 락 보유 ↑이나 push 빈도 낮음 → 무시 가능. 오히려 push non-fast-forward 경합도 제거(부수이득).
- 롤백: 각 주체는 `git_commit_push` 한 줄 호출이라 되돌리기 단순. 모듈 미사용 시 기존 동작 동일.
- 호환: truncation 게이트·autostash와 **상호보완**(게이트=내용 손상 차단 / 락=동시성 차단 / autostash=dirty pull).

## 7. 검증(완료 정의)
P1 자기테스트: 동시 3프로세스가 각자 다른 status/*.json에 100회 커밋 → ① 손실 0 ② index.lock fatal 0 ③ 최종 git log 카운트 일치 ④ JSON 전건 파싱 PASS. P3 후 라이브: 봇 승인 1건 + 동시 IG --once 강제 → 직렬화 로그(`git_lock.log`) 확인·무손상.
