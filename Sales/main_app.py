import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from crew import (
    generate_individual_case_summary,
    generate_report_for_forms,
    generate_summary_of_all_issues,
    close_case_with_reason,
    check_case_exists
)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
user_state = {}

# Create inline button layout
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
    """Send the main menu to the user."""
    await update.message.reply_text(
        "📋 Main Menu: Please choose an option below:",
        reply_markup=get_main_menu_buttons()
    )

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update)

# Button interactions
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

        # Show menu again
        await query.message.reply_text("📋 Main Menu: Please choose an option below:", reply_markup=get_main_menu_buttons())

    elif query.data == "close_case":
        user_state[user_id] = {"action": "closing_case", "step": "awaiting_case_id"}
        await query.edit_message_text("📥 Please enter the Case ID for the case you want to close.")


async def case_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_input = update.message.text.strip()

    if user_id not in user_state:
        await update.message.reply_text("❓ Please choose an action first using the menu.")
        await show_main_menu(update)
        return

    state = user_state[user_id]

    # Handle action based on user state
    if state["action"] == "closing_case":
        if state["step"] == "awaiting_case_id":
            # Validate Case ID (it should be numeric)
            if not user_input.isdigit():
                await update.message.reply_text("❗ Please enter a valid numeric Case ID.")
                return
            
            # Check if the Case ID exists in the database
            if not check_case_exists(user_input):
                await update.message.reply_text(f"❌ Case ID {user_input} does not exist, please try again.")
                return

            # Store the Case ID and move to awaiting_reason
            state["case_id"] = user_input
            state["step"] = "awaiting_reason"
            await update.message.reply_text(f"📝 Please provide a reason for closing Case {user_input}:")

        elif state["step"] == "awaiting_reason":
            # No validation needed for the reason
            reason = user_input
            await update.message.reply_text(f"⏳ Closing case {state['case_id']}...")

            try:
                result = close_case_with_reason(state["case_id"], reason)
                await update.message.reply_text(f"✅ {result}")
            except Exception as e:
                await update.message.reply_text(f"❌ Error: {e}")

            # Clear state and return to menu
            user_state.pop(user_id)
            await show_main_menu(update)

    elif state["action"] == "case_summary":
        # Handle case summary generation
        await update.message.reply_text("⏳ Generating case summary...")
        result = generate_individual_case_summary(int(user_input))
        await update.message.reply_text(f"<pre>{result}</pre>", parse_mode="HTML")
        await show_main_menu(update)

    elif state["action"] == "generate_report":
        # Handle full report generation
        await update.message.reply_text("⏳ Generating full report...")
        result = generate_report_for_forms(int(user_input))
        await update.message.reply_text(f"<pre>{result}</pre>", parse_mode="HTML")
        await show_main_menu(update)

    else:
        await update.message.reply_text("⚠️ Unknown action. Please try again.")
        await show_main_menu(update)

# Log errors
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Error occurred: {context.error}")

# Launch bot
def run_telegram_bot():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, case_id_handler))
    app.add_error_handler(error)

    print("🚀 Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    run_telegram_bot()
