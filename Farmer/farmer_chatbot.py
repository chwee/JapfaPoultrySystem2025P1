# bot_token = "7613014862:AAEPedcrFspIzJ28wvkPAecfxhmpntibiYw"

import sqlite3
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)
import uuid

# States
SELECTING_DATA, ENTERING_VALUE, UPLOADING_IMAGE, CONFIRMING = range(4)

RESUME_OR_NEW = 99  # New state before SELECTING_DATA

CONFIRM_CANCEL = 100

# Constants
BIOSECURITY_FIELDS = [
    "Farm Entry Protocols",
    "Disinfectant Used",
    "Footbath Availability",
    "Protective Clothing Provided",
    "Frequency of Disinfection",
    "Biosecurity Breach"
]

MORTALITY_FIELDS = [
    "Number of Deaths",
    "Age Group Affected",
    "Date of First Death",
    "Pattern of Deaths"
]

HEALTH_STATUS_FIELDS = [
    "General Flock Health",
    "Visible Symptoms",
    "Feed and Water Intake",
    "Vaccination Status",
    "Other Health Concerns"
]

# Field to Full Question Mapping
FULL_QUESTIONS = {
    # Biosecurity Form
    "Farm Entry Protocols": "🛡️ *What protocols are followed before someone can enter the farm?*\n_(eg: Change boots and clothes, wash hands, register name)_",
    "Disinfectant Used": "🧴 *Which disinfectants do you use regularly?*\n_(eg: Virkon S, bleach solution, iodine)_",
    "Footbath Availability": "🚿 *Is a footbath provided at all entrances to animal areas?*\n_(eg: Yes / No / Not Reinforced)_",
    "Protective Clothing Provided": "🧥 *What type of protective clothing is provided for visitors/workers?*\n_(eg: Boots, coveralls, gloves)_",
    "Frequency of Disinfection": "🧹 *How often are animal enclosures disinfected?*\n_(eg: Daily, once a week, after every batch)_",
    "Biosecurity Breach": "🚨 *Describe any recent biosecurity incident and your response.*\n_(eg: Visitor entered without footbath, cleaned area immediately and disinfected)_",

    # Mortality Form
    "Number of Deaths": "☠️ *How many chickens died in the past 7 days?*\n_(eg: 15)_",
    "Age Group Affected": "👶 *What age group of the chickens were affected?*\n_(eg: 0–2 weeks, 3–6 weeks, Layers, Breeders)_",
    "Date of First Death": "🗓️ *When did the first death occur?*\n_(eg: 3/4/2024)_",
    "Pattern of Deaths": "📈 *Were deaths sudden or gradual over time?*\n_(Eg: Sudden / Gradual)_",

    # Health Status Form
    "General Flock Health": "❤️ *How would you describe the overall health of your flock today?*\n_(eg: Good, Fair, Poor)_",
    "Visible Symptoms": "👀 *What are the symptoms you observed?*\n_(eg: Coughing, diarrhea, swollen eyes, weak legs)_",
    "Feed and Water Intake": "🥤 *Have you noticed any decrease in feed or water consumption?*\n_(Yes / No)_",
    "Vaccination Status": "💉 *What are the vaccinations the chickens have taken?*\n_(eg: Newcastle disease, Infectious bronchitis)_",
    "Other Health Concerns": "🤔 *Do you have any other health concerns about the chickens?*\n_(eg: Sudden drop in egg production, feather loss)_"
}

# In-memory user session data
user_session_data = {}

# DB Setup
def init_db():
    conn = sqlite3.connect("../poultry_data.db")
    print(f"DB Path: {os.path.abspath('../poultry_data.db')}")
    c = conn.cursor()
    # New Biosecurity Form table
    c.execute('''
        CREATE TABLE IF NOT EXISTS biosecurity_form (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT,
            user TEXT,
            farm_entry_protocols TEXT,
            disinfectant_used TEXT,
            footbath_availability TEXT,
            protective_clothing TEXT,
            frequency_of_disinfection TEXT,
            biosecurity_breach TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # New Mortality Form table
    c.execute('''
        CREATE TABLE IF NOT EXISTS mortality_form (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT,
            user TEXT,
            number_of_deaths TEXT,
            age_group_affected TEXT,
            date_of_first_death TEXT,
            pattern_of_deaths TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # New Health Status Form table
    c.execute('''
        CREATE TABLE IF NOT EXISTS health_status_form (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT,
            user TEXT,
            general_flock_health TEXT,
            visible_symptoms TEXT,
            feed_water_intake TEXT,
            vaccination_status TEXT,
            other_health_concerns TEXT,
            image_path TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Start Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    previous_data = load_incomplete_data(user_id)

    if update.message:
        sender = update.message
        send = sender.reply_text
    elif update.callback_query:
        sender = update.callback_query.message
        await update.callback_query.answer()
        send = sender.reply_text
    else:
        return ConversationHandler.END

    if user_id not in user_session_data and previous_data:
        if "__resume_prompt" in previous_data:
            # 🧠 Custom resume message (1-2 completed forms, none in progress)
            case_id = previous_data["__case_id"]
            bio_done = previous_data.get("biosecurity_done", False)
            mort_done = previous_data.get("mortality_done", False)
            health_done = previous_data.get("health_status_done", False)

            prompt = f"📂 You have a previous case in progress (Case ID: *{case_id}*).\n"
            prompt += "Please select a form to continue:\n\n"
            keyboard = []

            if not bio_done:
                keyboard.append([InlineKeyboardButton("📋 Resume Biosecurity Form", callback_data="form_biosecurity")])
            if not mort_done:
                keyboard.append([InlineKeyboardButton("☠️ Resume Mortality Form", callback_data="form_mortality")])
            if not health_done:
                keyboard.append([InlineKeyboardButton("❤️ Resume Health Status Form", callback_data="form_health_status")])

            keyboard.append([InlineKeyboardButton("❌ Cancel and Delete This Case", callback_data="cancel_entry")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Save the case_id so next step knows what to work with
            user_session_data[user_id] = {"__case_id": case_id}
            await send(prompt, reply_markup=reply_markup)
            return SELECTING_DATA

        else:
            # Regular resume of incomplete form
            user_session_data[user_id] = previous_data
            await send_checklist(user_id, send)
            return SELECTING_DATA

    else:
        # No resume data
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Biosecurity Form", callback_data="form_biosecurity")],
            [InlineKeyboardButton("☠️ Mortality Form", callback_data="form_mortality")],
            [InlineKeyboardButton("❤️ Health Status Form", callback_data="form_health_status")]
        ])
        await send("✅ Please select the form you would like to fill:", reply_markup=keyboard)
        return SELECTING_DATA
    
async def handle_resume_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "resume_case":
        user_session_data[user_id] = load_incomplete_data(user_id)
        await send_checklist(user_id, query.message.edit_text)

    elif query.data == "new_case":
        # 🧹 Delete previously detected incomplete case from correct form table
        try:
            incomplete_data = load_incomplete_data(user_id)
            if incomplete_data:
                case_id = incomplete_data.get("__case_id")
                current_form = incomplete_data.get("__current_form")

                if case_id and current_form:
                    conn = sqlite3.connect("../poultry_data.db")
                    c = conn.cursor()
                    if current_form == "biosecurity":
                        c.execute('DELETE FROM biosecurity_form WHERE id = ?', (case_id,))
                    elif current_form == "mortality":
                        c.execute('DELETE FROM mortality_form WHERE id = ?', (case_id,))
                    elif current_form == "health_status":
                        c.execute('DELETE FROM health_status_form WHERE id = ?', (case_id,))
                    conn.commit()
                    conn.close()

        except Exception as e:
            print(f"❌ Error deleting previous case: {e}")

        user_session_data[user_id] = {}

        # After deleting, ask for form selection
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Biosecurity Form", callback_data="form_biosecurity")],
            [InlineKeyboardButton("☠️ Mortality Form", callback_data="form_mortality")],
            [InlineKeyboardButton("❤️ Health Status Form", callback_data="form_health_status")]
        ])
        await query.message.edit_text(
            "🆕 Starting a new case...\n\n✅ Please select the form you would like to fill:",
            reply_markup=keyboard
        )

    return SELECTING_DATA
  
async def handle_form_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    form_selection = query.data

    if user_id not in user_session_data:
        user_session_data[user_id] = {}
        
    # Set case_id if not exist
    if "__case_id" not in user_session_data[user_id]:
        user_session_data[user_id]["__case_id"] = str(uuid.uuid4())

    if form_selection == "form_biosecurity":
        user_session_data[user_id]["__current_form"] = "biosecurity"
    elif form_selection == "form_mortality":
        user_session_data[user_id]["__current_form"] = "mortality"
    elif form_selection == "form_health_status":
        user_session_data[user_id]["__current_form"] = "health_status"

    await send_checklist(user_id, query.message.edit_text)
    return SELECTING_DATA

async def send_checklist(user_id, send_func):
    if user_id not in user_session_data:
        user_session_data[user_id] = {}

    session = user_session_data[user_id]
    current_form = session.get("__current_form")  # new

    # Pick fields based on form
    if current_form == "biosecurity":
        fields = BIOSECURITY_FIELDS
        form_name = "Biosecurity Form"
    elif current_form == "mortality":
        fields = MORTALITY_FIELDS
        form_name = "Mortality Form"
    elif current_form == "health_status":
        fields = HEALTH_STATUS_FIELDS
        form_name = "Health Status Form"
    else:
        fields = []
        form_name = "Unknown Form"

    checklist = f"📋 Please provide the following information for *{form_name}*.\n\n"
    checklist += "✅ = Filled, ❌ = Missing\n\n"

    for field in fields:
        filled = "✅" if field in session else "❌"
        checklist += f"{filled} {field}\n"

    keyboard = [[InlineKeyboardButton(field, callback_data=field)] for field in fields]

    # Only Health Status Form needs image
    if current_form == "health_status":
        keyboard.append([InlineKeyboardButton("📷 Upload Symptom Image", callback_data="upload_image_option")])

    # Review and Finish
    keyboard.append([InlineKeyboardButton("🔍 Review Entered Data", callback_data="review_data")])
    keyboard.append([
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_entry"),
        InlineKeyboardButton("✅ Finish", callback_data="finish_review")
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_func(checklist, reply_markup=reply_markup)

# Handle field selection
async def select_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selection = query.data
    context.user_data["current_field"] = selection

    full_questions = FULL_QUESTIONS

    question = full_questions.get(selection, f"📝 Enter value for *{selection}*:")

    await query.edit_message_text(question, parse_mode="Markdown")
    return ENTERING_VALUE

# Replace your `enter_value` function with this:
async def enter_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    field = context.user_data["current_field"]
    value = update.message.text.strip()

    if field == "Body Weight":
        try:
            weight = float(value)
            if not (0.03 <= weight <= 30):
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid weight in kg (e.g., 1.5).")
            return ENTERING_VALUE
    elif field == "Body Temperature":
        try:
            temp = float(value)
            if not (30 <= temp <= 45):
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid temperature in °C (e.g., 41.5).")
            return ENTERING_VALUE
    elif field == "Vaccination/Medication":
        if len(value) < 2:
            await update.message.reply_text("❌ Please enter more details (at least 2 characters).")
            return ENTERING_VALUE
    elif field == "Infection Symptoms":
        if len(value) < 2:
            await update.message.reply_text("❌ Please enter more details (at least 2 characters).")
            return ENTERING_VALUE

    if user_id not in user_session_data:
        user_session_data[user_id] = {}
    user_session_data[user_id][field] = {"value": value}
    
    await update.message.reply_text(f"✅ {field} enterred.")

    return await ask_next_action(update, context)
    
async def ask_next_action(update, context):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add More", callback_data="add_more")],
        [InlineKeyboardButton("🔍 Review Data", callback_data="review_data")],
        [InlineKeyboardButton("✅ Finish & Review", callback_data="finish_review")]
    ])
    new_text = "What would you like to do next?"

    # Send new message OR edit the existing one
    if update.callback_query:
        message = update.callback_query.message
    else:
        message = await update.message.reply_text(new_text, reply_markup=keyboard)

    # Save message ID and chat ID for future editing
    context.user_data["next_action_msg_id"] = message.message_id
    context.user_data["next_action_chat_id"] = message.chat_id

    # If message wasn't sent new, update it
    if update.callback_query:
        await message.edit_text(new_text, reply_markup=keyboard)

    return CONFIRMING


async def handle_next_step_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Retrieve saved message info
    msg_id = context.user_data.get("next_action_msg_id")
    chat_id = context.user_data.get("next_action_chat_id")

    # You can safely remove this delete block entirely
    # We don't want to delete it anymore, just reuse

    if data == "add_more":
        return await send_checklist(query.from_user.id, query.message.edit_text)

    elif data == "review_data":
        return await review_callback(update, context)

    elif data == "finish_review":
        return await show_confirmation(update, context)

# Handle image upload for Infection Symptoms
async def upload_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in user_session_data:
        user_session_data[user_id] = {}

    photo = update.message.photo[-1]
    file = await photo.get_file()
    image_path = f"images/{user_id}_{file.file_id}.jpg"
    await file.download_to_drive(image_path)

    # Store in a generic image field
    user_session_data[user_id]["__poultry_image"] = image_path

    await update.message.reply_text("🖼️ Image received and saved.")
    return await ask_next_action(update, context)

async def handle_image_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
    ])

    await query.message.reply_text(
        "📷 Please upload an image for infection symptoms by:\n"
        "1️⃣ Tapping the 📎 (paperclip) or 📷 (camera) icon below.\n"
        "2️⃣ Selecting or taking a photo.\n\n"
        "If you don't want to upload one, you can tap the button below to return.",
        reply_markup=keyboard
    )

    return UPLOADING_IMAGE

async def send_back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Safely remove image upload handler context if any
    if "current_field" in context.user_data:
        del context.user_data["current_field"]

    # Use `reply_text` to send a fresh checklist message
    await send_checklist(query.from_user.id, query.message.reply_text)
    return SELECTING_DATA

# Skip uploading image
async def skip_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_confirmation(update, context)
    return CONFIRMING

# Show all collected data for confirmation
async def show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle both message and callback cases safely
    if update.message:
        user_id = update.message.from_user.id
        chat_id = update.message.chat_id
        send = update.message.reply_text
        send_photo = update.message.reply_photo
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        send = query.message.reply_text
        send_photo = context.bot.send_photo
    else:
        return

    data = user_session_data.get(user_id, {})
    
    # Check if no data is entered
    has_fields = any(k for k in data if not k.startswith("__"))
    has_image = "__poultry_image" in data

    if not has_fields and not has_image:
        await send("📭 You haven't entered any data yet.")
        await send_checklist(user_id, send)
        return SELECTING_DATA

    await send("📋 Here's the data you've entered:")

    for field, content in data.items():
        if field.startswith("__"):
            continue  # skip metadata keys like __case_id

        msg = f"📌 *{field}*\n📝 {content['value']}"
        await send(msg, parse_mode="Markdown")
        
    # ✅ Show poultry image if uploaded
    image_path = data.get("__poultry_image")
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as img:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=img,
                caption="🖼️ Uploaded image of infected poultry."
            )

    keyboard = [
        [InlineKeyboardButton("✅ Confirm & Save", callback_data="confirm_save")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_entry")],
        [InlineKeyboardButton("🔙 Return to Main Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send("Do you want to save this data?", reply_markup=reply_markup)

# Handle confirmation
async def confirm_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("✅ confirm_save called")
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        session_data = user_session_data.get(user_id, {})
        current_form = session_data.get("__current_form")
        print(f"Saving session_data for user {user_id}: {session_data}")

        conn = sqlite3.connect("../poultry_data.db")
        c = conn.cursor()

        if current_form == "biosecurity":
            c.execute('''
                INSERT INTO biosecurity_form (
                    case_id, user, farm_entry_protocols, disinfectant_used, footbath_availability,
                    protective_clothing, frequency_of_disinfection, biosecurity_breach
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_data["__case_id"],
                str(user_id),
                session_data.get("Farm Entry Protocols", {}).get("value"),
                session_data.get("Disinfectant Used", {}).get("value"),
                session_data.get("Footbath Availability", {}).get("value"),
                session_data.get("Protective Clothing Provided", {}).get("value"),
                session_data.get("Frequency of Disinfection", {}).get("value"),
                session_data.get("Biosecurity Breach", {}).get("value")
            ))

        elif current_form == "mortality":
            c.execute('''
                INSERT INTO mortality_form (
                    case_id, user, number_of_deaths, age_group_affected,
                    date_of_first_death, pattern_of_deaths
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                session_data["__case_id"],
                str(user_id),
                session_data.get("Number of Deaths", {}).get("value"),
                session_data.get("Age Group Affected", {}).get("value"),
                session_data.get("Date of First Death", {}).get("value"),
                session_data.get("Pattern of Deaths", {}).get("value")
            ))

        elif current_form == "health_status":
            c.execute('''
                INSERT INTO health_status_form (
                    case_id, user, general_flock_health, visible_symptoms,
                    feed_water_intake, vaccination_status, other_health_concerns, image_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_data["__case_id"],
                str(user_id),
                session_data.get("General Flock Health", {}).get("value"),
                session_data.get("Visible Symptoms", {}).get("value"),
                session_data.get("Feed and Water Intake", {}).get("value"),
                session_data.get("Vaccination Status", {}).get("value"),
                session_data.get("Other Health Concerns", {}).get("value"),
                session_data.get("__poultry_image")
            ))

        conn.commit()
        conn.close()

    except Exception as e:
        print(f"❌ DB Write Error: {e}")

    await query.edit_message_text(f"✅ Case saved successfully!\n🆔 Your Case ID: {session_data['__case_id']}")
    
    # ✅ Clear session EXCEPT keep case_id
    case_id = session_data.get("__case_id")
    user_session_data[user_id] = {"__case_id": case_id}
    
    # ✅ Only offer "Fill another form" if the previous form was completed
    if is_form_complete(session_data):
        completed_forms = get_forms_by_case_id(case_id)
    
        completed_text = "📋 *Completed Forms for This Case:*\n\n"
        completed_text += f"{'✅' if completed_forms['biosecurity'] else '❌'} Biosecurity Form\n"
        completed_text += f"{'✅' if completed_forms['mortality'] else '❌'} Mortality Form\n"
        completed_text += f"{'✅' if completed_forms['health_status'] else '❌'} Health Status Form\n"
    
        await query.message.reply_text(
            completed_text,
            parse_mode="Markdown"
        )
        
        keyboard_buttons = []

        if not completed_forms["biosecurity"]:
            keyboard_buttons.append([InlineKeyboardButton("📋 Biosecurity Form", callback_data="form_biosecurity")])
        if not completed_forms["mortality"]:
            keyboard_buttons.append([InlineKeyboardButton("☠️ Mortality Form", callback_data="form_mortality")])
        if not completed_forms["health_status"]:
            keyboard_buttons.append([InlineKeyboardButton("❤️ Health Status Form", callback_data="form_health_status")])

        # Always add "Finish Session" button
        keyboard_buttons.append([InlineKeyboardButton("🏁 Finish Session", callback_data="finish_session")])

        reply_markup = InlineKeyboardMarkup(keyboard_buttons)

        await query.message.reply_text(
            "Would you like to fill another form for the same case?",
            reply_markup=reply_markup
        )
        return SELECTING_DATA
      
    else:
        # Form was incomplete. End session immediately.
        await query.message.reply_text(
            "✅ Saved successfully, but you did not complete all required fields.\n\n🔚 Ending session now."
        )
        return await end_session(update, context)
  
async def end_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # End session cleanly
    user_session_data.pop(user_id, None)

    await query.edit_message_text("Session has ended.")
    return ConversationHandler.END
  
def is_form_complete(session_data):
    current_form = session_data.get("__current_form")
    if not current_form:
        return False

    # Get fields list
    if current_form == "biosecurity":
        fields = BIOSECURITY_FIELDS
    elif current_form == "mortality":
        fields = MORTALITY_FIELDS
    elif current_form == "health_status":
        fields = HEALTH_STATUS_FIELDS
    else:
        return False

    # Check if all fields are filled
    for field in fields:
        if field not in session_data:
            return False
    return True
  
def get_forms_by_case_id(case_id):
    conn = sqlite3.connect("../poultry_data.db")
    c = conn.cursor()
    
    completed = {
        "biosecurity": False,
        "mortality": False,
        "health_status": False
    }

    # Check each form
    c.execute('SELECT 1 FROM biosecurity_form WHERE case_id = ?', (case_id,))
    if c.fetchone():
        completed["biosecurity"] = True

    c.execute('SELECT 1 FROM mortality_form WHERE case_id = ?', (case_id,))
    if c.fetchone():
        completed["mortality"] = True

    c.execute('SELECT 1 FROM health_status_form WHERE case_id = ?', (case_id,))
    if c.fetchone():
        completed["health_status"] = True

    conn.close()
    return completed

# Cancel handler
async def cancel_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    session_data = user_session_data.get(user_id, {})
    case_id = session_data.get("__case_id")
    
    message = "⚠️ Are you sure you want to cancel?\n\n"
    message += "The following completed forms linked to this case will be deleted:\n\n"

    try:
        conn = sqlite3.connect("../poultry_data.db")
        c = conn.cursor()

        forms_deleted = []

        # Check if forms exist with same case_id
        c.execute('SELECT 1 FROM biosecurity_form WHERE case_id = ?', (case_id,))
        if c.fetchone():
            forms_deleted.append("📋 Biosecurity Form")

        c.execute('SELECT 1 FROM mortality_form WHERE case_id = ?', (case_id,))
        if c.fetchone():
            forms_deleted.append("☠️ Mortality Form")

        c.execute('SELECT 1 FROM health_status_form WHERE case_id = ?', (case_id,))
        if c.fetchone():
            forms_deleted.append("❤️ Health Status Form")

        conn.close()

        if forms_deleted:
            message += "\n".join(forms_deleted)
        else:
            message += "❌ No completed forms found."

    except Exception as e:
        print(f"❌ Error checking forms: {e}")
        message += "⚠️ (Unable to check completed forms.)"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Yes, cancel and delete everything", callback_data="cancel_confirmed")],
        [InlineKeyboardButton("🔙 No, go back", callback_data="cancel_abort")]
    ])

    await query.edit_message_text(message, reply_markup=keyboard)
    return CONFIRM_CANCEL

async def cancel_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    session_data = user_session_data.get(user_id, {})
    case_id = session_data.get("__case_id")

    if not case_id:
        await query.edit_message_text("❌ No active case found to cancel.")
        return ConversationHandler.END

    # Delete uploaded image if it exists
    image_path = session_data.get("__poultry_image")
    if image_path and os.path.exists(image_path):
        try:
            os.remove(image_path)
            print(f"🗑️ Deleted image at {image_path}")
        except Exception as e:
            print(f"❌ Failed to delete image: {e}")

    # Delete from database FIRST
    try:
        conn = sqlite3.connect("../poultry_data.db")
        c = conn.cursor()
        c.execute('DELETE FROM biosecurity_form WHERE case_id = ?', (case_id,))
        c.execute('DELETE FROM mortality_form WHERE case_id = ?', (case_id,))
        c.execute('DELETE FROM health_status_form WHERE case_id = ?', (case_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Error deleting forms from DB: {e}")
        await query.edit_message_text("❌ Error deleting forms from DB.")
        return ConversationHandler.END

    # NOW pop from memory
    user_session_data.pop(user_id, None)

    await query.edit_message_text("❌ Entry and saved progress have been cancelled and deleted.")
    return ConversationHandler.END


async def cancel_abort(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_checklist(query.from_user.id, query.message.edit_text)
    return SELECTING_DATA

# Cancel command
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

async def review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = user_session_data.get(user_id, {})

    if not data:
        await query.message.reply_text("📭 You haven't entered any data yet.")
        return SELECTING_DATA

    # 1. Show all entered data
    review_text = "📋 *Here's what you've entered so far:*\n\n"
    for field, content in data.items():
        if field.startswith("__"):
            continue
        review_text += f"📌 *{field}*\n📝 {content['value']}\n\n"

    await query.message.reply_text(review_text, parse_mode="Markdown")

    # 2. Show image if present
    image_path = data.get("__poultry_image")
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as img:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=img,
                caption="🖼️ Uploaded image of infected poultry."
            )

    # 3. Re-show main menu checklist
    await send_checklist(user_id, query.message.reply_text)
    return SELECTING_DATA

def load_incomplete_data(user_id):
    conn = sqlite3.connect("../poultry_data.db")
    c = conn.cursor()

    # Find latest case_id (even if fully filled form) for user
    c.execute('''
        SELECT case_id FROM (
            SELECT case_id, timestamp FROM biosecurity_form WHERE user = ?
            UNION ALL
            SELECT case_id, timestamp FROM mortality_form WHERE user = ?
            UNION ALL
            SELECT case_id, timestamp FROM health_status_form WHERE user = ?
        )
        ORDER BY timestamp DESC LIMIT 1
    ''', (str(user_id), str(user_id), str(user_id)))

    row = c.fetchone()

    if not row:
        conn.close()
        return {}  # No forms at all

    case_id = row[0]

    # Helper to detect if a form is incomplete
    def is_form_incomplete(table, fields, prefix="", has_image=False):
        query = f"SELECT {', '.join(fields)}"
        if has_image:
            query += ", image_path"
        query += f" FROM {table} WHERE case_id = ? AND user = ? ORDER BY timestamp DESC LIMIT 1"
        c.execute(query, (case_id, str(user_id)))
        row = c.fetchone()
        if not row:
            return None
        field_data = row[:-1] if has_image else row
        if any(f is None or f == "" for f in field_data):
            session = {"__case_id": case_id, "__current_form": prefix}
            for i, f in enumerate(field_data):
                if f:
                    if prefix == "biosecurity":
                        session[BIOSECURITY_FIELDS[i]] = {"value": f}
                    elif prefix == "mortality":
                        session[MORTALITY_FIELDS[i]] = {"value": f}
                    elif prefix == "health_status":
                        session[HEALTH_STATUS_FIELDS[i]] = {"value": f}
            if has_image and row[-1]:
                session["__poultry_image"] = row[-1]
            return session
        return None

    # Priority: resume incomplete form
    bio = is_form_incomplete("biosecurity_form", [
        "farm_entry_protocols", "disinfectant_used", "footbath_availability",
        "protective_clothing", "frequency_of_disinfection", "biosecurity_breach"
    ], prefix="biosecurity")
    if bio:
        conn.close()
        return bio

    mort = is_form_incomplete("mortality_form", [
        "number_of_deaths", "age_group_affected", "date_of_first_death", "pattern_of_deaths"
    ], prefix="mortality")
    if mort:
        conn.close()
        return mort

    health = is_form_incomplete("health_status_form", [
        "general_flock_health", "visible_symptoms", "feed_water_intake",
        "vaccination_status", "other_health_concerns"
    ], prefix="health_status", has_image=True)
    if health:
        conn.close()
        return health

    # If no incomplete forms, but not all 3 are done → offer resume prompt
    c.execute('SELECT 1 FROM biosecurity_form WHERE case_id = ?', (case_id,))
    bio_done = bool(c.fetchone())
    c.execute('SELECT 1 FROM mortality_form WHERE case_id = ?', (case_id,))
    mort_done = bool(c.fetchone())
    c.execute('SELECT 1 FROM health_status_form WHERE case_id = ?', (case_id,))
    health_done = bool(c.fetchone())

    conn.close()

    if sum([bio_done, mort_done, health_done]) < 3:
        return {
            "__case_id": case_id,
            "__resume_prompt": True,
            "biosecurity_done": bio_done,
            "mortality_done": mort_done,
            "health_status_done": health_done
        }

    return {}

# Main
def main():
    init_db()
    os.makedirs("images", exist_ok=True)
    bot_token = "7685786328:AAEilDDS65J7-GB43i1LlaCJWJ3bx3i7nWs"
    app = Application.builder().token(bot_token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            RESUME_OR_NEW: [
                CallbackQueryHandler(handle_resume_decision, pattern="resume_case"),
                CallbackQueryHandler(handle_resume_decision, pattern="new_case")
            ],
            SELECTING_DATA: [
                CallbackQueryHandler(handle_form_selection, pattern="^form_biosecurity$"),
                CallbackQueryHandler(handle_form_selection, pattern="^form_mortality$"),
                CallbackQueryHandler(handle_form_selection, pattern="^form_health_status$"),
                CallbackQueryHandler(select_data, pattern=f"^({'|'.join(BIOSECURITY_FIELDS + MORTALITY_FIELDS + HEALTH_STATUS_FIELDS)})$"),
                CallbackQueryHandler(cancel_entry, pattern="^cancel_entry$"),
                CallbackQueryHandler(show_confirmation, pattern="^finish_review$"),
                CallbackQueryHandler(handle_image_option, pattern="^upload_image_option$"),
                CallbackQueryHandler(send_back_to_main_menu, pattern="^back_to_menu$"),
                CallbackQueryHandler(review_callback, pattern="review_data"),
                CallbackQueryHandler(confirm_save, pattern="confirm_save"),
                CallbackQueryHandler(end_session, pattern="^finish_session$"),
            ],
            ENTERING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_value)],
            UPLOADING_IMAGE: [
                MessageHandler(filters.PHOTO, upload_image),
                CommandHandler("skip", skip_image),
                CallbackQueryHandler(send_back_to_main_menu, pattern="^back_to_menu$"),
                CallbackQueryHandler(review_callback, pattern="review_data"),
            ],
            CONFIRMING: [
                CallbackQueryHandler(confirm_save, pattern="confirm_save"),
                CallbackQueryHandler(cancel_entry, pattern="cancel_entry"),
                # CallbackQueryHandler(start, pattern="add_more"),
                # CallbackQueryHandler(review_callback, pattern="review_data"),
                # CallbackQueryHandler(show_confirmation, pattern="finish_review"),
                CallbackQueryHandler(send_back_to_main_menu, pattern="^back_to_menu$"),
                CallbackQueryHandler(handle_next_step_callback, pattern="^(add_more|review_data|finish_review)$"),
                CallbackQueryHandler(select_data, pattern=f"^({'|'.join(BIOSECURITY_FIELDS + MORTALITY_FIELDS + HEALTH_STATUS_FIELDS)})$"),
                CallbackQueryHandler(handle_image_option, pattern="^upload_image_option$"),
            ],
            CONFIRM_CANCEL: [
                CallbackQueryHandler(cancel_confirmed, pattern="cancel_confirmed"),
                CallbackQueryHandler(cancel_abort, pattern="cancel_abort"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
