from langchain_community.document_loaders import TextLoader, PyPDFLoader
import os
import sqlite3
import json
from datetime import datetime
from dotenv import load_dotenv
from crewai import Agent, Task, Crew

# === CONFIGURATION ===
UPLOAD_DIR = "uploads"
DB_PATH = "poultry_data.db"
os.makedirs(UPLOAD_DIR, exist_ok=True)

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# === DATABASE UTILS ===
def save_attachment(case_id, file_name, file_path):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO issue_attachments (case_id, file_name, file_path) VALUES (?, ?, ?)",
        (case_id, file_name, file_path)
    )
    conn.commit()
    conn.close()

# === FILE PROCESSING ===
def extract_text(file_path):
    # Implement text extraction based on file type (e.g., PDF or plain text)
    if file_path.endswith('.pdf'):
        loader = PyPDFLoader(file_path)
    else:
        loader = TextLoader(file_path)
    docs = loader.load()
    return "\n".join([doc.page_content for doc in docs])[:3000]

# === AGENTS AND TASKS ===
relevance_agent = Agent(
    role="Relevance Checker",
    goal="Check if the uploaded file is relevant to the issue description",
    backstory="You are responsible for validating whether uploads are useful to resolving issues.",
    verbose=True,
    allow_delegation=False
)

summary_agent = Agent(
    role="Summary Writer",
    goal="Summarize uploaded technical files with context to the reported issue",
    backstory="You are responsible for summarizing and highlighting key evidence in uploads for technical reviews.",
    verbose=True,
    allow_delegation=False
)

def run_upload_analysis(case_id, file_path):
    file_name = os.path.basename(file_path)
    file_text = extract_text(file_path)
    save_attachment(case_id, file_name, file_path)

    # Adjust task to expect structured response
    relevance_task = Task(
        description=f"Check if this file is relevant to case {case_id}: {file_text[:1000]}. "
                    "Please provide the response as a JSON with 'is_relevant' (boolean) and 'explanation' (string).",
        agent=relevance_agent,
        expected_output="JSON with 'is_relevant' as a boolean and 'explanation' as a string",
        output_file="relevance.txt"
    )

    # summary_task = Task(
    #     description=f"Summarize this file in the context of case {case_id}: {file_text[:1000]}. "
    #                 "Please provide the summary as a string.",
    #     agent=summary_agent,
    #     expected_output="A short paragraph summarizing the file's content and its relevance",
    #     output_file="summary.txt"
    # )

    crew = Crew(
        agents=[relevance_agent, summary_agent],
        tasks=[relevance_task],
        verbose=True
    )

    return crew.kickoff()

# case_id = 123
# file_path = 'C:/Users/Jia Ying/Downloads/24S1_DList_Cert.pdf'

# result = run_upload_analysis(case_id, file_path)