# from telegram import Update
# from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
# import os
# from dotenv import load_dotenv
# from crew import sales_technical_chatbot_crew

# load_dotenv()
# TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # from .env

# # Define handler for start command
# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text('Hello! Send me your request.')

# # Define handler for messages
# async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_message = update.message.text

#     # Trigger CrewAI crew based on the message
#     print(f"Received message: {user_message}")

#     # You can customize what you want to pass to Crew
#     result = sales_technical_chatbot_crew.kickoff(
#         context={
#             "user_input": user_message  # optional if your Crew tasks are expecting dynamic input
#         }
#     )

#     await update.message.reply_text(f"Here is the result:\n{result}")

# # Main function
# def main():
#     app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

#     app.add_handler(CommandHandler('start', start))
#     app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

#     print("Bot is running...")
#     app.run_polling()

# if __name__ == '__main__':
#     main()

import os
from dotenv import load_dotenv
from crew import sales_technical_chatbot_crew

# Load environment variables
load_dotenv()
os.environ["CREWAI_TELEMETRY_ENABLED"] = "false"

def main():
    print("Welcome to the Sales/Technical CrewAI Chatbot!")

    while True:
        user_message = input("\nEnter your message (or type 'exit' to quit): ").strip()

        if user_message.lower() == "exit":
            print("Goodbye!")
            break

        # Execute the CrewAI Crew
        result = sales_technical_chatbot_crew.kickoff(
            context={"user_input": user_message}
        )

        print("\nResult from CrewAI:\n")
        print(result)

if __name__ == "__main__":
    main()