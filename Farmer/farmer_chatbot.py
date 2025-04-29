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

# States
SELECTING_DATA, ENTERING_VALUE, UPLOADING_IMAGE, CONFIRMING = range(4)

DATA_FIELDS = [
    "Farm Entry Protocols",
    "Disinfectant Used",
    "Footbath Availability",
    "Protective Clothing Provided",
    "Frequency of Disinfection",
    "Biosecurity Breach"
]

RESUME_OR_NEW = 99  # New state before SELECTING_DATA

CONFIRM_CANCEL = 100

# In-memory user session data
user_session_data = {}

# DB Setup
def init_db():
    conn = sqlite3.connect("../poultry_data.db")
    print(f"DB Path: {os.path.abspath('../poultry_data.db')}")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS poultry_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        body_weight TEXT,
        body_temperature TEXT,
        vaccination_medication TEXT,
        infection_symptoms TEXT,
        image_path TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

# Start Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    previous_data = load_incomplete_data(user_id)

    # Determine if this is a message or a callback query
    if update.message:
        sender = update.message
        send = sender.reply_text
    elif update.callback_query:
        sender = update.callback_query.message
        await update.callback_query.answer()
        send = sender.reply_text
    else:
        return ConversationHandler.END  # fallback

    if user_id not in user_session_data and previous_data:
        # Ask user if they want to resume or start fresh
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Resume Previous Case", callback_data="resume_case")],
            [InlineKeyboardButton("🆕 Start New Case", callback_data="new_case")]
        ])
        await send(
            "🕵️ We detected an unfinished case from you.\nWould you like to continue where you left off?",
            reply_markup=keyboard
        )
        return RESUME_OR_NEW
    else:
        if user_id not in user_session_data:
            user_session_data[user_id] = previous_data
        await send_checklist(user_id, send)
        return SELECTING_DATA
    
async def handle_resume_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "resume_case":
        user_session_data[user_id] = load_incomplete_data(user_id)
        await send_checklist(user_id, query.message.edit_text)

    elif query.data == "new_case":
        # 🧹 Delete previously detected case from DB
        try:
            conn = sqlite3.connect("../poultry_data.db")
            c = conn.cursor()
            c.execute('''DELETE FROM poultry_health
                         WHERE id = (SELECT id FROM poultry_health WHERE user = ? ORDER BY timestamp DESC LIMIT 1)''',
                      (str(user_id),))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ Error deleting previous case: {e}")

        user_session_data[user_id] = {}
        await query.message.edit_text("🆕 Starting a new case...")
        await send_checklist(user_id, query.message.reply_text)

    return SELECTING_DATA

async def send_checklist(user_id, send_func):
    if user_id not in user_session_data:
        user_session_data[user_id] = {}

    session = user_session_data[user_id]
    checklist = "📋 Please provide the following information to help track poultry health.\n\n"
    checklist += "✅ = Filled, ❌ = Missing\n\n"

    for field in DATA_FIELDS:
        filled = "✅" if field in session else "❌"
        checklist += f"{filled} {field}\n"

    # ✅ Add image status below the main data
    image_uploaded = "✅ Uploaded" if "__poultry_image" in session else "❌ Not Uploaded"
    checklist += f"\n🖼️ Infection Image (Optional): {image_uploaded}\n"

    checklist += "\nTap a button below to enter or update a field:"

    # Buttons for each field
    keyboard = [[InlineKeyboardButton(field, callback_data=field)] for field in DATA_FIELDS]

    # Optional image upload
    keyboard.append([InlineKeyboardButton("📷 Upload Symptom Image (Optional)", callback_data="upload_image_option")])

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

    # Dictionary of full questions with examples
    full_questions = {
        "Farm Entry Protocols": "🛡️ *What protocols are followed before someone can enter the farm?*\n_(eg: Change boots and clothes, wash hands, register name)_",
        "Disinfectant Used": "🧴 *Which disinfectants do you use regularly?*\n_(eg: Virkon S, bleach solution, iodine)_",
        "Footbath Availability": "🚿 *Is a footbath provided at all entrances to animal areas?*\n_(eg: Yes / No / Not Reinforced)_",
        "Protective Clothing Provided": "🧥 *What type of protective clothing is provided for visitors/workers?*\n_(eg: Boots, coveralls, gloves)_",
        "Frequency of Disinfection": "🧹 *How often are animal enclosures disinfected?*\n_(eg: Daily, once a week, after every batch)_",
        "Biosecurity Breach": "🚨 *Describe any recent biosecurity incident and your response.*\n_(eg: Visitor entered without footbath, cleaned area immediately and disinfected)_"
    }

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
        print(f"Saving session_data for user {user_id}: {session_data}")

        conn = sqlite3.connect("../poultry_data.db")
        c = conn.cursor()

        body_weight = session_data.get("Body Weight", {}).get("value")
        body_temperature = session_data.get("Body Temperature", {}).get("value")
        vaccination_med = session_data.get("Vaccination/Medication", {}).get("value")
        infection_symptoms = session_data.get("Infection Symptoms", {}).get("value")
        image_path = session_data.get("__poultry_image")
        case_id = session_data.pop("__case_id", None)
        
        if case_id:
            # Update existing case
            c.execute('''
                UPDATE poultry_health SET 
                    body_weight = ?, 
                    body_temperature = ?, 
                    vaccination_medication = ?, 
                    infection_symptoms = ?, 
                    image_path = ?
                WHERE id = ?
            ''', (
                body_weight, body_temperature, vaccination_med, infection_symptoms, image_path, case_id
            ))
        else:
            # Insert new case
            c.execute('''
                INSERT INTO poultry_health (
                    user, body_weight, body_temperature,
                    vaccination_medication, infection_symptoms, image_path
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                str(user_id), body_weight, body_temperature,
                vaccination_med, infection_symptoms, image_path
            ))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ DB Write Error: {e}")

    if len(session_data) < len(DATA_FIELDS):
        await query.edit_message_text("📝 Your incomplete case has been saved for future completion.")
    else:
        await query.edit_message_text("✅ Case saved successfully.")
    user_session_data.pop(user_id, None)
    return ConversationHandler.END

# Cancel handler
async def cancel_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Yes, cancel and delete", callback_data="cancel_confirmed")],
        [InlineKeyboardButton("🔙 No, go back", callback_data="cancel_abort")]
    ])
    
    await query.edit_message_text(
        "⚠️ Are you sure you want to cancel and delete all progress?\nThis will remove your latest case.",
        reply_markup=keyboard
    )
    return CONFIRM_CANCEL

async def cancel_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Delete uploaded image if it exists
    image_path = user_session_data.get(user_id, {}).get("__poultry_image")
    if image_path and os.path.exists(image_path):
        try:
            os.remove(image_path)
            print(f"🗑️ Deleted image at {image_path}")
        except Exception as e:
            print(f"❌ Failed to delete image: {e}")

    # Remove in-memory data
    user_session_data.pop(user_id, None)

    # Delete latest case from DB
    try:
        conn = sqlite3.connect("../poultry_data.db")
        c = conn.cursor()
        c.execute('''DELETE FROM poultry_health
                     WHERE id = (SELECT id FROM poultry_health WHERE user = ? ORDER BY timestamp DESC LIMIT 1)''',
                  (str(user_id),))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Error deleting case from DB: {e}")

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
    c.execute('''SELECT id, body_weight, body_temperature, vaccination_medication, infection_symptoms, image_path 
                 FROM poultry_health 
                 WHERE user = ? 
                 ORDER BY timestamp DESC LIMIT 1''', (str(user_id),))
    row = c.fetchone()
    conn.close()

    if not row:
        return {}

    # Extract fields
    row_id, body_weight, body_temp, vacc_med, infection_symptoms, image_path = row

    # Only resume if at least one REQUIRED field is missing
    if all([body_weight, body_temp, vacc_med, infection_symptoms]):
        return {}  # No need to resume, it's complete

    session_data = {"__case_id": row_id}

    field_map = {
        "Body Weight": body_weight,
        "Body Temperature": body_temp,
        "Vaccination/Medication": vacc_med,
        "Infection Symptoms": infection_symptoms
    }

    for field, value in field_map.items():
        if value:
            session_data[field] = {"value": value}

    if image_path:
        session_data["__poultry_image"] = image_path

    return session_data

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
                CallbackQueryHandler(select_data, pattern=f"^({'|'.join(DATA_FIELDS)})$"),
                CallbackQueryHandler(cancel_entry, pattern="^cancel_entry$"),
                CallbackQueryHandler(show_confirmation, pattern="^finish_review$"),
                CallbackQueryHandler(handle_image_option, pattern="^upload_image_option$"),
                CallbackQueryHandler(send_back_to_main_menu, pattern="^back_to_menu$"),
                CallbackQueryHandler(review_callback, pattern="review_data"),
                CallbackQueryHandler(confirm_save, pattern="confirm_save"),
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
                CallbackQueryHandler(select_data, pattern=f"^({'|'.join(DATA_FIELDS)})$"),
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
