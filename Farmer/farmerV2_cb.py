import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)
from farmer_agents import dynamic_sql_agent
from farmer_agents import db_init_agent
import ast
import uuid
import re

# States
SELECTING_FORM, SELECTING_QUESTION, ENTERING_ANSWER = range(3)

# Sample dynamic form definitions
form_definitions = {
    "flock_farm_information": {
        "Type of Chicken": "What type of chicken is this? (e.g., Layer, Broiler, Breeder)",
        "Age of Chicken": "What is the age of the chicken?",
        "Housing Type": "What housing type is used? (e.g., Closed House, Opened-Side)",
        "Number of Affected Flocks/Houses": "How many flocks or houses are affected?",
        "Feed Type": "What type of feed is used? (e.g., Complete Feed, Self Mix)",
        "Environment Information": "Describe the environmental conditions (e.g., climate, weather, cage atmosphere, nearby poultry farms)"
    },
    "symptoms_performance_data": {
        "Main Symptoms": "What are the main symptoms or clinical signs observed?",
        "Daily Production Performance": "Provide daily chicken production data (e.g., mortality, %HD, feed intake, egg weight)",
        "Pattern of Spread or Drop": "Describe if there's mortality, production drop, or spreading pattern"
    },
    "medical_diagnostic_records": {
        "Vaccination History": "What is the vaccination history or program followed?",
        "Lab Data": "Provide any lab results or data if available",
        "Pathology Findings (Necropsy)": "List any pathology anatomy changes found during necropsy",
        "Current Treatment": "What treatment is currently being administered?",
        "Management Questions": "List any management-related concerns or questions"
    }
}

intent_dict = {   
    "insert_into_db": "Insert or update a given form entry for the given user and case_id with the latest field values from the session."
}

# DB SETUP
DB_PATH = "../JAPFASNOWFLAKE.db"

# In-memory session data
user_session_data = {}

# DB Setup
def init_db(form_definitions):
    sql_block = db_init_agent(form_definitions)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        # Split the SQL block into individual CREATE TABLE statements
        statements = [stmt.strip() for stmt in sql_block.split(";") if stmt.strip()]
        for stmt in statements:
            # If UNIQUE constraint is not present, inject it before the closing bracket
            if "UNIQUE(case_id, user)" not in stmt:
                stmt = re.sub(r"\)(\s*)$", r",\n    UNIQUE(case_id, user)\1)", stmt)

            print(f"Executing:\n{stmt}\n")
            c.execute(stmt)
        conn.commit()
    except Exception as e:
        print("❌ Error executing SQL schema:", e)
    finally:
        conn.close()

def save_to_db_with_agent(user_id, form, case_id, data):
    user_prompt = intent_dict["insert_into_db"]
    result_str = dynamic_sql_agent(user_prompt, form_definitions)
    try:
        sql_dict = ast.literal_eval(result_str)
        sql = sql_dict.get(form)
        if not sql:
            print(f"No SQL returned for form: {form}")
            return

        # Prepare values in order (user, case_id, ...fields)
        values = [case_id, str(user_id)] + list(data.values())

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(sql, values)
        conn.commit()
        conn.close()
        print(f"✅ Saved {form} for user {user_id} with case_id {case_id}")
    except Exception as e:
        print("Error executing dynamic SQL:", e)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, preserve_session=False):
    user_id = update.effective_user.id
    if not preserve_session:
        user_session_data[user_id] = {
            "forms": {},
            "current_form": "",
            "current_question": ""
        }
    keyboard = [[InlineKeyboardButton(name.replace("_", " ").title(), callback_data=f"form:{name}")]
                for name in form_definitions.keys()]
    keyboard.append([InlineKeyboardButton("💾 Save and Quit", callback_data="save_quit")])
    await update.message.reply_text("📋 Choose a form to answer:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECTING_FORM

# Form selection
async def select_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    form_name = query.data.split(":")[1]

    # Always initialize the expected nested structure safely
    session = user_session_data.setdefault(user_id, {})
    session.setdefault("forms", {})
    session.setdefault("current_form", "")
    session.setdefault("current_question", "")

    session["current_form"] = form_name
    session["forms"].setdefault(form_name, {})

    return await show_question_menu(query, user_id)


async def show_question_menu(query, user_id):
    form = user_session_data[user_id]["current_form"]
    answered = user_session_data[user_id]["forms"].get(form, {})
    keyboard = []
    for q in form_definitions[form]:
        status = "✅" if q in answered else "❌"
        keyboard.append([InlineKeyboardButton(f"{status} {q}", callback_data=f"question:{q}")])
    await query.edit_message_text(f"📄 Answering: {form.replace('_', ' ').title()}",
                                  reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECTING_QUESTION

async def select_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    question = query.data.split(":")[1]
    user_session_data[user_id]["current_question"] = question
    form = user_session_data[user_id]["current_form"]
    await query.edit_message_text(form_definitions[form][question])
    return ENTERING_ANSWER

async def enter_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    answer = update.message.text.strip()
    question = user_session_data[user_id].get("current_question")
    form = user_session_data[user_id]["current_form"]
    user_session_data[user_id]["forms"][form][question] = answer

    # If all answered, return to main
    if len(user_session_data[user_id]["forms"][form]) == len(form_definitions[form]):
        await update.message.reply_text("✅ All questions answered! Returning to main menu...")
        return await start(update, context, preserve_session=True)
    else:
        # Ask next
        keyboard = [[InlineKeyboardButton("Back to Questions", callback_data=f"form:{form}")]]
        await update.message.reply_text("✅ Answer saved.", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECTING_QUESTION

async def save_quit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    session = user_session_data.get(user_id)
    if session:
        case_id = str(uuid.uuid4())
        for form_name, answers in session.get("forms", {}).items():
            if answers:
                save_to_db_with_agent(user_id, form_name, case_id, answers)
    await query.edit_message_text("💾 Saved. Goodbye!")
    user_session_data.pop(user_id, None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

def main():
    if not os.path.exists(DB_PATH):
        print("Database not found. Initializing...")
        init_db(form_definitions)
    else:
        print("Database already exists. Skipping initialization.")
        
    app = Application.builder().token("7685786328:AAEilDDS65J7-GB43i1LlaCJWJ3bx3i7nWs").build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_FORM: [
                CallbackQueryHandler(select_form, pattern="^form:"),
                CallbackQueryHandler(save_quit, pattern="^save_quit$")
            ],
            SELECTING_QUESTION: [
                CallbackQueryHandler(select_question, pattern="^question:"),
                CallbackQueryHandler(select_form, pattern="^form:")
            ],
            ENTERING_ANSWER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_answer)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()