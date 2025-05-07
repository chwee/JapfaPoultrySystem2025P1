import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)
from farmer_agents import dynamic_sql_agent, db_init_agent, data_validator_agent
import ast
import uuid
import re
import textwrap
import inspect

# States
SELECTING_FORM, SELECTING_QUESTION, ENTERING_ANSWER = range(3)

# ==================================DATA THAT CAN CHANGE=========================================

form_definitions = {
    "flock_farm_information": {
        "Type of Chicken": "What type of chicken is this? (e.g., Layer, Broiler, Breeder)",
        "Age of Chicken": "What is the age of the chicken? (years, round up to nearest whole number)",
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

form_definitions_types = {
    "flock_farm_information": {
        "Type of Chicken": "TEXT",
        "Age of Chicken": "INTEGER",
        "Housing Type": "TEXT",
        "Number of Affected Flocks/Houses": "INTEGER",
        "Feed Type": "TEXT",
        "Environment Information": "TEXT"
    },
    "symptoms_performance_data": {
        "Main Symptoms": "TEXT",
        "Daily Production Performance": "TEXT",  # Can be JSON or text-encoded data
        "Pattern of Spread or Drop": "TEXT"
    },
    "medical_diagnostic_records": {
        "Vaccination History": "TEXT",
        "Lab Data": "TEXT",
        "Pathology Findings (Necropsy)": "TEXT",
        "Current Treatment": "TEXT",
        "Management Questions": "TEXT"
    }
}

form_validation = {
    "flock_farm_information": {
        "Type of Chicken": lambda x: x.lower() in ["layer", "broiler", "breeder"],
        "Age of Chicken": lambda x: x.isdigit() and 0 < int(x) < 200,
        "Housing Type": lambda x: x.lower() in ["closed house", "opened-side", "open-sided", "open house"],
        "Number of Affected Flocks/Houses": lambda x: x.isdigit() and int(x) >= 0,
        "Feed Type": lambda x: x.lower() in ["complete feed", "self mix"],
        "Environment Information": lambda x: len(x.strip()) > 10
    },
    "symptoms_performance_data": {
        "Main Symptoms": lambda x: len(x.strip()) > 5,
        "Daily Production Performance": lambda x: len(x.strip()) > 5,
        "Pattern of Spread or Drop": lambda x: len(x.strip()) > 5
    },
    "medical_diagnostic_records": {
        "Vaccination History": lambda x: len(x.strip()) > 5,
        "Lab Data": lambda x: len(x.strip()) > 5,
        "Pathology Findings (Necropsy)": lambda x: len(x.strip()) > 5,
        "Current Treatment": lambda x: len(x.strip()) > 5,
        "Management Questions": lambda x: len(x.strip()) > 5
    }
}

intent_dict = {   
    "insert_into_db": "Insert or update a given form entry for the given user and case_id with the latest field values from the session."
}

# =================================================================================================

# DB SETUP
DB_PATH = "../JAPFASNOWFLAKE.db"

# In-memory session data
user_session_data = {}

# DB Setup
def init_db(form_definitions_types):
    sql_block = db_init_agent(form_definitions_types)

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
        
def to_sql_field_name(label):
    return re.sub(r'\W+', '_', label.strip().lower())

def extract_field_names_from_insert(sql):
    match = re.search(r"INSERT INTO \w+ \((.*?)\)", sql)
    if not match:
        return []
    field_str = match.group(1)
    return [field.strip() for field in field_str.split(",")]

def save_to_db_with_agent(user_id, form, case_id, data, sql_dict):
    sql = sql_dict.get(form)
    if not sql:
        print(f"No SQL returned for form: {form}")
        return

    try:
        # Normalize field names in data
        normalized_data = {
            to_sql_field_name(k): v for k, v in data.items()
        }

        # Extract expected field names from SQL
        field_names = extract_field_names_from_insert(sql)

        # Build value map including case_id and user
        value_map = {
            "case_id": case_id,
            "user": str(user_id),
            **normalized_data
        }

        # Final value list in correct order
        values = [value_map.get(field, None) for field in field_names]

        print("FINAL SQL:", sql)
        print("VALUES:", values)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(sql, values)
        conn.commit()
        conn.close()

    except Exception as e:
        print("❌ Error executing dynamic SQL:", e)

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
    if update.message:
        await update.message.reply_text("📋 Choose a form to answer:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        await update.callback_query.message.reply_text("📋 Choose a form to answer:", reply_markup=InlineKeyboardMarkup(keyboard))
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

    # Add Return to Form Select button
    keyboard.append([InlineKeyboardButton("🔙 Return to Form Select", callback_data="return_to_form_select")])

    await query.edit_message_text(
        f"📄 Answering: {form.replace('_', ' ').title()}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_QUESTION

async def return_to_form_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # user_id = query.from_user.id
    # print(f"User {user_id} pressed 'Return to Form Select'")  # Debugging log
    return await start(update, context, preserve_session=True)

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

    # Get validator for this field
    validator = form_validation.get(form, {}).get(question)

    if validator and not validator(answer):
        dynamic_error = local_validator(question, validator)
        await update.message.reply_text(dynamic_error)
        await update.message.reply_text(form_definitions[form][question])
        return ENTERING_ANSWER

    # ✅ Extra validation for TEXT responses using agent (only if local passed)
    if validator and "strip" in inspect.getsource(validator):
        form_question_map = form_definitions[form]
        validator_output, error_message = data_validator_agent(
            question=question,
            answer=answer,
            form_def=form_question_map,
            form_val=form_validation
        )
        print("🧪 Validator Output:", repr(validator_output))
        if not validator_output.strip().startswith("✅ Valid"):
            await update.message.reply_text(error_message or validator_output)
            await update.message.reply_text(form_question_map[question])
            return ENTERING_ANSWER

    # Save valid answer
    user_session_data[user_id]["forms"][form][question] = answer

    if len(user_session_data[user_id]["forms"][form]) == len(form_definitions[form]):
        await update.message.reply_text("✅ All questions answered! Returning to main menu...")
        return await start(update, context, preserve_session=True)
    else:
        await update.message.reply_text("✅ Answer saved.")

        class FakeQuery:
            async def edit_message_text(self, text, reply_markup=None):
                await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)

        return await show_question_menu(FakeQuery(), user_id)
    
def local_validator(question, validator):
    try:
        src = textwrap.dedent(inspect.getsource(validator)).strip()

        # 🧠 Detect number validation
        if "x.isdigit()" in src:
            # Check if there's a numeric range check
            match = re.search(r"int\(x\)\s*([<>]=?)\s*(\d+)", src)
            if match:
                operator, threshold = match.groups()
                operators = {
                    ">": "greater than",
                    ">=": "greater than or equal to",
                    "<": "less than",
                    "<=": "less than or equal to"
                }
                op_text = operators.get(operator, operator)
                return f"⚠️ Please enter only a number {op_text} {threshold}."
            else:
                return "⚠️ Please enter only a number."

        # 🧠 Detect string list options
        elif "x.lower()" in src and "in" in src:
            options = re.findall(r"\[([^\]]+)\]", src)
            if options:
                clean_opts = options[0].replace('"', '').replace("'", "").split(",")
                formatted = ", ".join(o.strip().title() for o in clean_opts)
                return f"⚠️ Please choose one of the following: {formatted}."

        # 🧠 Detect length checks
        elif "len(x.strip())" in src:
            match = re.findall(r"len\(x\.strip\(\)\)\s*([<>]=?)\s*(\d+)", src)
            if match:
                msgs = []
                for operator, length in match:
                    operators = {
                        ">": f"at least {int(length)+1} characters",
                        ">=": f"{length} or more characters",
                        "<": f"fewer than {length} characters",
                        "<=": f"{length} or fewer characters"
                    }
                    msgs.append(operators.get(operator, f"length condition ({operator} {length})"))
                return "⚠️ Please enter text with " + " and ".join(msgs) + "."
            return "⚠️ Input length does not meet requirements."

        return "⚠️ Invalid input. Please try again."

    except Exception:
        return "⚠️ Invalid input. Please try again."

async def save_quit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    session = user_session_data.get(user_id)
    if session:
        case_id = str(uuid.uuid4())
    user_prompt = intent_dict["insert_into_db"]
    sql_dict = ast.literal_eval(dynamic_sql_agent(user_prompt, form_definitions_types))

    for form_name in form_definitions.keys():
        answers = session.get("forms", {}).get(form_name, {})
        save_to_db_with_agent(user_id, form_name, case_id, answers, sql_dict)
    await query.edit_message_text("💾 Saved. Goodbye!")
    user_session_data.pop(user_id, None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

def main():
    if not os.path.exists(DB_PATH):
        print("Database not found. Initializing...")
        init_db(form_definitions_types)
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
                CallbackQueryHandler(select_form, pattern="^form:"),
                CallbackQueryHandler(return_to_form_select, pattern="^return_to_form_select$")
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