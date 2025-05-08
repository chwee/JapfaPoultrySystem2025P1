import logging
import os
import re
import json
import smtplib
from email.message import EmailMessage
from langchain_openai import ChatOpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from crew import run_upload_analysis, save_attachment
from Sales.test_free_text_in_telegram import (
    execute_case_closing,
    check_case_exists,
    get_case_info,
    generate_individual_case_summary,
    generate_report_for_forms,
    generate_summary_of_all_issues,
    generate_and_execute_sql,
    generate_report_from_prompt
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

schema = """
Tables:
- biosecurity_form(id, case_id, farm_location, breach_type, affected_area, timestamp)
- mortality_form(id, case_id, number_dead, cause_of_death, timestamp)
- health_status_form(id, case_id, symptoms_observed, vet_comments, timestamp)
- issues(id, title, description, farm_name, status, assigned_team, case_id, created_at, updated_at)
- farmer_problem(id, case_id, problem_description, timestamp)
"""

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL_PASSKEY = os.getenv("EMAIL_PASSKEY")
user_state = {}

def send_escalation_email(case_id: str, reason: str, case_info: str):
    try:
        msg = EmailMessage()
        msg["Subject"] = f"🚨 Escalation Notice: Case #{case_id}"
        msg["From"] = "2006limjy@gmail.com"
        msg["To"] = "2006limjy@gmail.com"

        msg.set_content(f"""
A case has been escalated by a sales user.

Case ID: {case_id}
Reason for Escalation:
{reason}

Case Details:
{case_info}

Please review and follow up promptly, thank you.
""")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login("2006limjy@gmail.com", EMAIL_PASSKEY)
            smtp.send_message(msg)

        return True
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False

def get_main_menu_buttons():
    keyboard = [
        [
            InlineKeyboardButton("Get Case Summary", callback_data="case_summary"),
            InlineKeyboardButton("Generate Report", callback_data="generate_report"),
            InlineKeyboardButton("View All Issues", callback_data="view_all_issues")
        ],
        [
            InlineKeyboardButton("Close Case", callback_data="close_case"),
            InlineKeyboardButton("Escalate Case", callback_data="escalate_case")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def show_main_menu(update: Update):
    await update.message.reply_text(
        "📋 Main Menu: Please choose an option below:",
        reply_markup=get_main_menu_buttons()
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "case_summary":
        user_state[user_id] = {"action": "case_summary", "step": "awaiting_case_id"}
        await query.edit_message_text("📥 Please enter the Case ID for the summary:")

    elif query.data == "generate_report":
        user_state[user_id] = {"action": "generate_report", "step": "awaiting_case_id"}
        await query.edit_message_text("📥 Please enter the Case ID for the full report:")

    elif query.data == "view_all_issues":
        await query.edit_message_text("🔍 Viewing all issues...")
        try:
            result = generate_summary_of_all_issues()
            await query.message.reply_text(f"<pre>{result}</pre>", parse_mode="HTML")
        except Exception as e:
            await query.message.reply_text(f"❌ Error: {e}")

        await query.message.reply_text("📋 Main Menu: Please choose an option below:", reply_markup=get_main_menu_buttons())

    elif query.data == "close_case":
        user_state[user_id] = {"action": "closing_case", "step": "awaiting_case_id"}
        await query.edit_message_text("📥 Please enter the Case ID for the case you want to close.")

    elif query.data == "escalate_case":
        user_state[user_id] = {"action": "escalating_case", "step": "awaiting_case_id"}
        await query.edit_message_text("📥 Please enter the Case ID for the case you want to escalate.")

async def case_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_input = update.message.text.strip()

    if user_id not in user_state:
        case_match = re.search(r"(?:case[_\s]*id)?[^\d]*(\d+)", user_input, re.IGNORECASE)
        case_id = int(case_match.group(1)) if case_match else None

        await update.message.reply_text("🔍 Processing your request...")

        try:
            result = generate_and_execute_sql(schema=schema, user_input=user_input, case_id=case_id)
            report = generate_report_from_prompt(result)

            if not result:
                await update.message.reply_text("⚠️ No data found or unable to generate query.")
                return

            await update.message.reply_text("📝 Here's the report:")
            await update.message.reply_text(f"<pre>{report}</pre>", parse_mode="HTML")

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

        await show_main_menu(update)
        return

    state = user_state[user_id]

    if state["action"] == "closing_case":
        if state["step"] == "awaiting_case_id":
            if not user_input.isdigit():
                await update.message.reply_text("❗ Please enter a valid numeric Case ID.")
                return

            if not check_case_exists(user_input):
                await update.message.reply_text(f"❌ Case ID {user_input} does not exist, please try again.")
                return

            state["case_id"] = user_input
            state["step"] = "awaiting_reason"
            await update.message.reply_text(f"📝 Please provide a reason for closing the case {user_input}:")

        elif state["step"] == "awaiting_reason":
            state["reason"] = user_input
            state["step"] = "waiting_for_upload_or_skip"
            await update.message.reply_text(
                "📤 Upload a document to support your case (optional), or type 'skip' to proceed without a document."
            )

        elif state["step"] == "waiting_for_upload_or_skip":
            if user_input.strip().lower() == "skip":
                reason = state.get("reason", "No reason provided.")
                try:
                    result = execute_case_closing(state["case_id"], reason)
                    await update.message.reply_text(f"✅ Case closed successfully: {result}")
                except Exception as e:
                    await update.message.reply_text(f"❌ Case closure failed: {e}")
                user_state.pop(user_id, None)
                await show_main_menu(update)
            else:
                await update.message.reply_text("❗ Please upload a document or type 'skip' to proceed without one.")

    elif state["action"] == "escalating_case":
        if state["step"] == "awaiting_case_id":
            if not user_input.isdigit():
                await update.message.reply_text("❗ Please enter a valid numeric Case ID.")
                return

            if not check_case_exists(user_input):
                await update.message.reply_text(f"❌ Case ID {user_input} does not exist.")
                return

            state["case_id"] = user_input
            state["step"] = "awaiting_reason"
            await update.message.reply_text(f"📝 Please enter the reason for escalating the case {user_input}:")

        elif state["step"] == "awaiting_reason":
            reason = user_input
            case_info = get_case_info(state["case_id"])
            success = send_escalation_email(state["case_id"], reason, case_info)

            if success:
                await update.message.reply_text(f"✅ Case {state['case_id']} has been escalated and the technical team has been notified.")
            else:
                await update.message.reply_text("❌ Failed to send the escalation email. Please try again later.")

            user_state.pop(user_id)
            await show_main_menu(update)

    elif state["action"] == "case_summary":
        await update.message.reply_text("⏳ Generating case summary...")
        case_id = int(user_input)
        result = generate_individual_case_summary(case_id)
        await update.message.reply_text(f"<pre>{result}</pre>", parse_mode="HTML")
        await show_main_menu(update)

    elif state["action"] == "generate_report":
        await update.message.reply_text("⏳ Generating full report...")
        case_id = int(user_input)
        result = generate_report_for_forms(case_id)
        await update.message.reply_text(f"<pre>{result}</pre>", parse_mode="HTML")
        await show_main_menu(update)

    else:
        await update.message.reply_text("⚠️ Unknown action. Please try again.")
        await show_main_menu(update)

async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data = user_state.get(user_id)

    if not user_data or "case_id" not in user_data:
        await update.message.reply_text("⚠️ Please enter a valid case ID before uploading.")
        return

    document = update.message.document
    if not document:
        await update.message.reply_text("❌ No file found.")
        return

    file = await context.bot.get_file(document.file_id)
    file_name = document.file_name
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, file_name)
    try:
        await file.download_to_drive(file_path)
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to download the file: {e}")
        return

    await update.message.reply_text("📄 File received. Analyzing...")

    try:
        raw_output = run_upload_analysis(user_data["case_id"], file_path)
        print("DEBUG: Raw analysis result:", raw_output)

        # Check if json_dict exists
        if raw_output.json_dict:
            analysis_result = raw_output.json_dict
            print(f"DEBUG: Analysis result (json_dict): {analysis_result}")

            # Access the fields
            is_relevant = analysis_result.get("is_relevant", False)
            explanation = analysis_result.get("explanation", "No explanation provided by the analysis system.")
            
            if not is_relevant:
                await update.message.reply_text(
                    f"⚠️ The uploaded file is *not relevant* to Case ID {user_data['case_id']}. Case closure aborted.\n\n📄 Explanation: {explanation}",
                    parse_mode="Markdown"
                )
                return

            await update.message.reply_text(
                f"✅ File is relevant to Case ID {user_data['case_id']}.\n\n📄 Explanation: {explanation}\n\n🚪 Proceeding to close the case..."
            )

            # Proceed to close the case after checking relevance
            reason = user_data.get("reason", "No reason provided.")
            try:
                result = execute_case_closing(user_data["case_id"], reason)
                await update.message.reply_text(f"✅ Case closed successfully: {result}")
            except Exception as e:
                await update.message.reply_text(f"❌ Case closure failed: {e}")

        else:
            print("DEBUG: json_dict is not available in raw_output.")
            # Fallback: Check if raw_output contains a valid JSON string
            raw_data = raw_output.raw
            print(f"DEBUG: Raw data for analysis: {raw_data}")

            try:
                analysis_result = json.loads(raw_data)
                print(f"DEBUG: Analysis result (raw output): {analysis_result}")

                is_relevant = analysis_result.get("is_relevant", False)
                explanation = analysis_result.get("explanation", "No explanation provided by the analysis system.")

                if not is_relevant:
                    await update.message.reply_text(
                        f"⚠️ The uploaded file is *not relevant* to Case ID {user_data['case_id']}. Case closure aborted.\n\n📄 Explanation: {explanation}",
                        parse_mode="Markdown"
                    )
                    return

                await update.message.reply_text(
                    f"✅ File is relevant to Case ID {user_data['case_id']}.\n\n📄 Explanation: {explanation}\n\n🚪 Proceeding to close the case..."
                )

                # Proceed to close the case after checking relevance
                reason = user_data.get("reason", "No reason provided.")
                try:
                    result = execute_case_closing(user_data["case_id"], reason)
                    await update.message.reply_text(f"✅ Case closed successfully: {result}")
                except Exception as e:
                    await update.message.reply_text(f"❌ Case closure failed: {e}")
            except json.JSONDecodeError:
                await update.message.reply_text("❌ Error: The raw output is not a valid JSON.")
            except Exception as e:
                await update.message.reply_text(f"❌ Unexpected error: {e}")
            except Exception as e:
                await update.message.reply_text(f"❌ Error during analysis or closure: {e}")
    finally:
        user_state.pop(user_id, None)
        await show_main_menu(update)

async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Error occurred: {context.error}")

def run_telegram_bot():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, case_id_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_upload))
    app.add_error_handler(error)

    print("🚀 Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    run_telegram_bot()
