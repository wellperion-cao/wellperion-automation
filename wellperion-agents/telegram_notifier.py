"""텔레그램 업무 보고 알림 모듈 (인라인 버튼 승인 포함)"""
import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


class TelegramNotifier:
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def send(self, message: str, reply_markup: dict = None) -> dict:
        """메시지 전송. reply_markup 있으면 인라인 버튼 포함."""
        if not self.token or not self.chat_id:
            return {}
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            resp = httpx.post(f"{self.base_url}/sendMessage", json=payload, timeout=10)
            return resp.json()
        except Exception:
            return {}

    def send_approval_request(self, task_name: str, summary: str, task_key: str) -> int:
        """CEO 승인 요청 — 인라인 [✅ 승인] [❌ 반려] 버튼 포함. message_id 반환."""
        result = self.send(
            f"📋 <b>CEO 승인 요청</b>\n\n"
            f"<b>태스크:</b> {task_name}\n\n"
            f"<b>요약:</b>\n{summary[:600]}\n\n"
            f"승인하시겠습니까?",
            reply_markup={
                "inline_keyboard": [[
                    {"text": "✅ 승인", "callback_data": f"approve_{task_key}"},
                    {"text": "❌ 반려", "callback_data": f"reject_{task_key}"},
                ]]
            },
        )
        return result.get("result", {}).get("message_id", 0)

    def send_photo(self, image_path: str, caption: str = None) -> dict:
        """사진 전송 (sendPhoto). caption UTF-8 한글 지원. API 응답 dict 반환."""
        if not self.token or not self.chat_id:
            return {}
        if not os.path.exists(image_path):
            return {"ok": False, "description": "file not found"}
        data = {"chat_id": self.chat_id}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"
        try:
            with open(image_path, "rb") as f:
                resp = httpx.post(
                    f"{self.base_url}/sendPhoto",
                    data=data,
                    files={"photo": f},
                    timeout=30,
                )
            return resp.json()
        except Exception as e:
            return {"ok": False, "description": str(e)}

    def send_document(self, file_path: str, caption: str = None) -> dict:
        """파일(산출물) 전송 (sendDocument). caption UTF-8 한글 지원. API 응답 dict 반환."""
        if not self.token or not self.chat_id:
            return {}
        if not os.path.exists(file_path):
            return {"ok": False, "description": "file not found"}
        data = {"chat_id": self.chat_id}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"
        try:
            with open(file_path, "rb") as f:
                resp = httpx.post(
                    f"{self.base_url}/sendDocument",
                    data=data,
                    files={"document": f},
                    timeout=60,
                )
            return resp.json()
        except Exception as e:
            return {"ok": False, "description": str(e)}

    def answer_callback(self, callback_query_id: str, text: str = ""):
        """인라인 버튼 클릭 응답 처리 (버튼 로딩 스피너 제거)"""
        try:
            httpx.post(
                f"{self.base_url}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text},
                timeout=5,
            )
        except Exception:
            pass

    def edit_message(self, message_id: int, new_text: str):
        """승인/반려 후 버튼 메시지를 결과 텍스트로 교체"""
        try:
            httpx.post(
                f"{self.base_url}/editMessageText",
                json={
                    "chat_id": self.chat_id,
                    "message_id": message_id,
                    "text": new_text,
                    "parse_mode": "HTML",
                },
                timeout=5,
            )
        except Exception:
            pass

    def wait_for_approval(self, task_key: str, timeout: int = 300) -> str:
        """CEO 승인/반려 응답 대기 (최대 timeout초). 'approved'/'rejected'/'timeout' 반환."""
        offset = None
        deadline = time.time() + timeout
        while time.time() < deadline:
            params = {"timeout": 20, "allowed_updates": ["callback_query"]}
            if offset:
                params["offset"] = offset
            try:
                resp = httpx.get(f"{self.base_url}/getUpdates", params=params, timeout=25)
                updates = resp.json().get("result", [])
            except Exception:
                time.sleep(2)
                continue

            for update in updates:
                offset = update["update_id"] + 1
                cq = update.get("callback_query")
                if not cq:
                    continue
                data = cq.get("data", "")
                self.answer_callback(cq["id"])
                if data == f"approve_{task_key}":
                    return "approved"
                if data == f"reject_{task_key}":
                    return "rejected"

        return "timeout"

    # ── 단계별 알림 ──────────────────────────────────────

    def notify_workflow_start(self, task_name: str):
        self.send(
            f"🚀 <b>워크플로우 시작</b>\n"
            f"📋 태스크: {task_name}\n"
            f"⏳ C레벨 분석 진행 중..."
        )

    def notify_approval(self, task_name: str, approved: bool, reason: str = ""):
        emoji = "✅" if approved else "❌"
        status = "승인" if approved else "반려"
        self.send(
            f"{emoji} <b>CEO 승인게이트: {status}</b>\n"
            f"📋 {task_name}\n"
            f"{f'💬 {reason[:200]}' if reason else ''}"
        )

    def notify_field_feedback(self, task_name: str):
        self.send(
            f"👥 <b>현장 피드백 수집 완료</b>\n"
            f"📋 {task_name}\n"
            f"💡 C레벨 내부 토론 시작"
        )

    def notify_debate_complete(self, task_name: str):
        self.send(
            f"⚔️ <b>C레벨 토론 완료</b>\n"
            f"📋 {task_name}\n"
            f"📝 CEO 최종 보고서 작성 중..."
        )

    def notify_workflow_complete(self, task_name: str):
        self.send(
            f"🎯 <b>워크플로우 완료</b>\n"
            f"📋 {task_name}\n"
            f"📊 가이드허브에서 확인하세요."
        )

    def notify_workflow_rejected(self, task_name: str):
        self.send(
            f"🚫 <b>태스크 반려됨</b>\n"
            f"📋 {task_name}\n"
            f"💬 CEO가 반려했습니다. 가이드허브 또는 GitHub에서 이유를 확인하세요."
        )

    def notify_confirmed(self, task_name: str):
        self.send(
            f"📌 <b>GitHub 확정 기록 완료</b>\n"
            f"📋 {task_name}\n"
            f"✅ 승인된 내용이 GitHub에 확정 저장되었습니다."
        )

    def send_daily_report(self, role: str, task_summary: str):
        role_emoji = {
            "CEO": "👑", "CTO": "💻", "CFO": "💰",
            "CMO": "📣", "COO": "⚙️", "CPO": "🎯",
        }
        emoji = role_emoji.get(role, "👤")
        self.send(
            f"{emoji} <b>[{role}] 일일 업무 보고</b>\n\n"
            f"{task_summary[:800]}\n\n"
            f"📊 상세 내용 → 가이드허브"
        )
