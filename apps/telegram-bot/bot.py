import asyncio
import json
import logging
import os
from typing import Any

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER = str(os.environ["TELEGRAM_OWNER_USER_ID"])
API = os.getenv("CONTROL_PLANE_URL", "http://127.0.0.1:8080").rstrip("/")
HEADERS = {"X-Bot-Token": os.environ["CONTROL_PLANE_BOT_TOKEN"]}
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
TERMINAL = {"SUCCEEDED", "FAILED", "FAILED_POLICY", "CANCELLED"}


def allowed(update: Update) -> bool:
    return bool(
        update.effective_user
        and str(update.effective_user.id) == OWNER
        and update.effective_chat
        and update.effective_chat.type == "private"
    )


async def call(method: str, path: str, **kwargs: Any) -> Any:
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.request(method, API + path, headers=HEADERS, **kwargs)
        response.raise_for_status()
        return response.json()


def buttons(task: dict[str, Any]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Approve once", callback_data="approve:" + task["id"]),
                InlineKeyboardButton("Reject", callback_data="cancel:" + task["id"]),
            ],
            [InlineKeyboardButton("View status", callback_data="status:" + task["id"])],
        ]
    )


def compact(value: Any, limit: int = 3000) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def format_result(task: dict[str, Any]) -> str:
    if task.get("status") == "FAILED":
        return f"I could not complete that request.\n\n{compact(task.get('error') or 'The runner returned an unspecified failure.')}"
    if task.get("status") == "FAILED_POLICY":
        return f"I did not perform that request because approval was missing, expired, or denied.\n\n{compact(task.get('error'))}"
    if task.get("status") == "CANCELLED":
        return "Cancelled."

    result = task.get("result") or {}
    if not isinstance(result, dict):
        return f"Completed.\n\n{compact(result)}"

    lines: list[str] = []
    summary = compact(result.get("summary"), 700)
    if summary:
        lines.append(summary)

    for action in result.get("actions") or []:
        kind = action.get("type", "action")
        if kind == "shell":
            code = action.get("exit_code")
            stdout = compact(action.get("stdout"), 2200)
            stderr = compact(action.get("stderr"), 900)
            if code == 0:
                lines.append(stdout or "Command completed successfully.")
            else:
                lines.append(f"Command failed with exit code {code}.\n{stderr or stdout or 'No output returned.'}")
        elif kind == "browser":
            opened = compact(action.get("opened"), 1000)
            lines.append(f"Opened: {opened}")
        elif kind == "app":
            if action.get("verified"):
                lines.append(f"Opened {action.get('app') or 'the application'}.")
            else:
                lines.append(f"Application launch failed: {compact(action.get('stderr') or action.get('stdout') or 'No operating-system confirmation was returned.')}")
        elif kind == "macos_terminal_command":
            stdout = compact(action.get("stdout"), 2200)
            if action.get("exit_code") == 0 and action.get("verified"):
                lines.append(f"Opened Terminal and ran: {action.get('command', '')}\n\n{stdout or 'Command completed successfully.'}")
            else:
                lines.append(f"Terminal command failed with exit code {action.get('exit_code')}.\n{stdout or 'No output returned.'}")
        elif kind == "file_read":
            content = compact(action.get("content"), 2200)
            lines.append(content or f"Read {action.get('path', 'file')}.")
        elif kind == "file_write":
            lines.append(f"Wrote {action.get('bytes', 0)} bytes to {action.get('path', 'the requested file')}.")
        else:
            lines.append(compact(action))

    # The current runner can open pages but cannot verify page contents. Never imply that it did.
    if any(a.get("type") == "browser" for a in result.get("actions") or []) and not any(
        a.get("type") in {"file_read", "shell"} and a.get("content") or a.get("stdout")
        for a in result.get("actions") or []
    ):
        lines.append("Note: the page was opened, but this runner did not inspect its contents or generate a verified web-page summary.")

    return compact("\n\n".join(line for line in lines if line), 3800) or "Completed."


async def replace_progress(context: ContextTypes.DEFAULT_TYPE, data: dict[str, Any], text: str, *, reply_markup=None) -> None:
    try:
        await context.bot.edit_message_text(
            chat_id=data["chat_id"],
            message_id=data["message_id"],
            text=text,
            reply_markup=reply_markup,
        )
    except BadRequest as exc:
        if "Message is not modified" not in str(exc):
            raise


async def reject(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("Unauthorized direct-message request.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await reject(update)
        return
    await update.effective_message.reply_text("Operator online. Send a message naturally. Use /devices, /tasks, /status <id>, or /cancel <id> when needed.")


async def watch_task(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    try:
        task = await call("GET", "/v1/tasks/" + data["task_id"])
        status = task["status"]
        if status in TERMINAL:
            await replace_progress(context, data, format_result(task))
            context.job.schedule_removal()
            return
        if status == "WAITING_FOR_APPROVAL" and not data.get("approval_sent"):
            await replace_progress(
                context,
                data,
                "Approval required before I can continue.\n\n"
                f"Request: {compact(task['text'], 1000)}\n"
                f"Risk: {task['risk']}",
                reply_markup=buttons(task),
            )
            data["approval_sent"] = True
    except Exception as exc:
        logging.warning("task watcher failed: %s", exc)


async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await reject(update)
        return
    text = (update.effective_message.text or "").strip()
    if not text:
        return
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        response = await call("POST", "/v1/intake", json={"requester_id": OWNER, "text": text})
        if response["kind"] == "chat":
            await update.effective_message.reply_text(response["reply"][:4000])
            return

        task = response["task"]
        if task["requires_approval"]:
            await update.effective_message.reply_text(
                "Approval required before I can continue.\n\n"
                f"Request: {compact(task['text'], 1000)}\n"
                f"Risk: {task['risk']}",
                reply_markup=buttons(task),
            )
            return

        progress = await update.effective_message.reply_text("Working on it…")
        context.job_queue.run_repeating(
            watch_task,
            interval=2,
            first=2,
            data={"task_id": task["id"], "chat_id": update.effective_chat.id, "message_id": progress.message_id},
            name="task-" + task["id"],
        )
    except httpx.HTTPStatusError as exc:
        await update.effective_message.reply_text(f"I could not start that request.\n\n{compact(exc.response.text, 1500)}")
    except Exception as exc:
        logging.exception("intake failed")
        await update.effective_message.reply_text(f"Request failed: {type(exc).__name__}: {exc}")


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await reject(update)
        return
    try:
        rows = await call("GET", "/v1/tasks?limit=10")
        output = "\n\n".join(
            f"{x['id'][:8]} | {x['status']} | {x['risk']} | {x.get('device_id') or '-'}\n{x['text'][:180]}"
            for x in rows
        )
        await update.effective_message.reply_text(output or "No tasks.")
    except Exception as exc:
        await update.effective_message.reply_text(f"List failed: {exc}")


async def devices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await reject(update)
        return
    try:
        rows = await call("GET", "/v1/devices")
        await update.effective_message.reply_text(
            "\n".join(f"{x['id']} | {x['os']} | {x['status']} | {x['hostname']} | {x['last_seen_at'] or '-'}" for x in rows)
            or "No runners are registered. Start the runner on your Mac or Windows device first."
        )
    except Exception as exc:
        await update.effective_message.reply_text(f"Device lookup failed: {exc}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await reject(update)
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /status <full-task-id>")
        return
    try:
        item = await call("GET", "/v1/tasks/" + context.args[0])
        await update.effective_message.reply_text(
            f"{item['id']}\n{item['status']} | {item['risk']} | {item.get('device_id') or '-'}\n\n{format_result(item)}"[:4000]
        )
    except Exception as exc:
        await update.effective_message.reply_text(f"Status lookup failed: {exc}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await reject(update)
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /cancel <full-task-id>")
        return
    try:
        item = await call("POST", f"/v1/tasks/{context.args[0]}/cancel", params={"requester_id": OWNER})
        await update.effective_message.reply_text("Cancelled." if item["status"] == "CANCELLED" else f"Task is {item['status']}.")
    except Exception as exc:
        await update.effective_message.reply_text(f"Cancellation failed: {exc}")


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not allowed(update):
        await query.answer("Unauthorized", show_alert=True)
        return
    await query.answer()
    action, task_id = query.data.split(":", 1)
    try:
        if action == "approve":
            item = await call("POST", f"/v1/tasks/{task_id}/approve", params={"requester_id": OWNER})
            await query.edit_message_text("Working on it…")
            context.job_queue.run_repeating(
                watch_task,
                interval=2,
                first=2,
                data={"task_id": item["id"], "chat_id": query.message.chat_id, "message_id": query.message.message_id},
                name="task-" + item["id"],
            )
        elif action == "cancel":
            await call("POST", f"/v1/tasks/{task_id}/cancel", params={"requester_id": OWNER})
            await query.edit_message_text("Cancelled.")
        else:
            item = await call("GET", f"/v1/tasks/{task_id}")
            await query.edit_message_text(format_result(item))
    except Exception as exc:
        await query.edit_message_text(f"Request failed: {exc}")


def main() -> None:
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", list_tasks))
    app.add_handler(CommandHandler("devices", devices))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, submit))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
