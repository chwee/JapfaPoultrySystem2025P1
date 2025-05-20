from langchain_community.document_loaders import TextLoader, PyPDFLoader
import os
import sqlite3
import json
from datetime import datetime
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
from Sales.streamlit_crew import generate_and_execute_sql

# === CONFIGURATION ===
UPLOAD_DIR = "uploads"
DB_PATH = "poultry_data.db"
os.makedirs(UPLOAD_DIR, exist_ok=True)

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

schema = """
Tables:
- flock_farm_information(id, case_id, type_of_chicken, age_of_chicken, housing_type, number_of_affected_flocks, feed_type, environment_information, timestamp)
- symptoms_performance_data(id, case_id, main_symptoms, daily_production_performance, pattern_of_spread_or_drop, timestamp)
- medical_diagnostic_records(id, case_id, vaccination_history, lab_data, pathology_findings_necropsy, current_treatment, management_questions, timestamp)
- issues(id, title, description, farm_name, status, close_reason, assigned_team, case_id, created_at, updated_at)
- farmer_problem(id, case_id, problem_description, timestamp)
- notifications(id, recipient_team, message, sent_at)
- issue_attachments(id, case_id, file_name, file_path, uploaded_at)
"""

# === DATABASE UTILS ===
# def save_attachment(case_id, file_name, file_path):
#     conn = sqlite3.connect(DB_PATH)
#     cursor = conn.cursor()
#     cursor.execute(
#         "INSERT INTO issue_attachments (case_id, file_name, file_path) VALUES (?, ?, ?)",
#         (case_id, file_name, file_path)
#     )
#     conn.commit()
#     conn.close()

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

def run_upload_analysis(case_id, file_path):
    file_name = os.path.basename(file_path)
    file_text = extract_text(file_path)
    generate_and_execute_sql(schema=schema, action_type="insert_attachment", case_id=case_id, file_path=file_path, file_name=file_name)

    # Adjust task to expect structured response
    relevance_task = Task(
        description=f"Check if this file is relevant to case {case_id}: {file_text[:1000]}. "
                    "Please provide the response as a JSON with 'is_relevant' (boolean) and 'explanation' (string).",
        agent=relevance_agent,
        expected_output="JSON with 'is_relevant' as a boolean and 'explanation' as a string",
        output_file="relevance.txt"
    )

    crew = Crew(
        agents=[relevance_agent],
        tasks=[relevance_task],
        verbose=True
    )

    return crew.kickoff()

# case_id = 123
# file_path = 'C:/Users/Jia Ying/Downloads/24S1_DList_Cert.pdf'

# run_upload_analysis(case_id, file_path)