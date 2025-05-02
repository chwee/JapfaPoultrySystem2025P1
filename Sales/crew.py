import os
import sqlite3
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
from crewai.tools import BaseTool
from collections import defaultdict
from crewai_tools import NL2SQLTool
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

# Load .env variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

os.environ["CREWAI_TELEMETRY_ENABLED"] = "FALSE"

class SQLiteTool(BaseTool):
    name: str = "SQLiteTool"
    description: str = "Run SQL queries against the poultry database."
    db_path: str

    def __init__(self, db_path: str):
        super().__init__(db_path=db_path)
        self.db_path = db_path

    def _run(self, query: str) -> str:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                if query.strip().lower().startswith("select"):
                    rows = cursor.fetchall()
                    if not rows:
                        return "No results found."
                    return "\n".join([str(row) for row in rows])  # Return results as formatted string
                else:
                    conn.commit()
                    return "Query executed successfully."
        except Exception as e:
            return f"Error running query: {e}"

    async def _arun(self, query: str) -> str:
        return self._run(query)
    
class PatchedNL2SQLTool(NL2SQLTool):
    def _fetch_available_tables(self):
        # Use SQLAlchemy's inspector to get table names in SQLite
        engine = create_engine(self.db_uri)
        inspector = inspect(engine)
        return [{"table_name": name} for name in inspector.get_table_names()]

    def _fetch_all_available_columns(self, table_name):
        # Use SQLAlchemy inspector to get columns for each table
        engine = create_engine(self.db_uri)
        inspector = inspect(engine)
        columns = inspector.get_columns(table_name)
        return [{"column_name": col["name"], "data_type": col["type"]} for col in columns]

# Replace this with your schema
schema = """
Tables:
- biosecurity_form(id, case_id, farm_location, breach_type, affected_area, summary, timestamp)
- mortality_form(id, case_id, number_dead, cause_of_death, summary, timestamp)
- health_status_form(id, case_id, symptoms_observed, vet_comments, summary, timestamp)
- issues(id, title, description, farm_name, status, assigned_team, case_id, created_at, updated_at)
- farmer_problem(id, case_id, problem_description, timestamp)
"""

nl2sql_tool = PatchedNL2SQLTool(
    db_uri="sqlite:///poultry_data.db",
    schema=schema
)

# NotificationTool
class NotificationTool(BaseTool):
    name: str = "NotificationTool"
    description: str = "Simulates sending notifications to Sales or Technical teams."

    def _run(self, input_text: str) -> str:
        print(f"[NOTIFICATION]: {input_text}")  # Simulate sending a notification
        return f"Notification sent: '{input_text}'"

    async def _arun(self, input_text: str) -> str:
        return self._run(input_text)

sqlite_tool = SQLiteTool(db_path="poultry_data.db")
notification_tool = NotificationTool()

def fetch_row(q):
    with sqlite3.connect("poultry_data.db") as conn:
        cur = conn.cursor()
        cur.execute(q)
        return cur.fetchone()
    
def fetch_all(q):
    with sqlite3.connect("poultry_data.db") as conn:
        cur = conn.cursor()
        cur.execute(q)
        return cur.fetchall()

# AGENTS
issue_management_agent = Agent(
    role="Issue Management Agent",
    goal="Generate case summaries, form reports, and system statistics.",
    backstory="An expert agent responsible for reviewing cases and forms to help the sales and technical teams.",
    tools=[sqlite_tool, nl2sql_tool],
    allow_delegation=True,
    llm=ChatOpenAI(model_name="gpt-4o", temperature=0.3)  # lower temp for more factual outputs
)

status_update_agent = Agent(
    role="Status Update Agent",
    goal="Help Sales/Technical team mark issues as 'Closed' or 'Needs Tech Help'.",
    backstory="An expert in updating issue statuses and generating appropriate SQL queries to reflect changes.",
    tools=[sqlite_tool],
    allow_delegation=False,
    llm=ChatOpenAI(model_name="gpt-4o", temperature=0.3)
)

notification_agent = Agent(
    role="Notification Agent",
    goal="Alert Sales/Technical team when issues require action.",
    backstory="An agent dedicated to notifying the appropriate teams about issue statuses and updates.",
    tools=[notification_tool],
    allow_delegation=False,
    llm=ChatOpenAI(model_name="gpt-4o", temperature=0.3)
)

# TASKS
def generate_individual_case_summary(case_id):
    bio_data = fetch_row(f"SELECT * FROM biosecurity_form WHERE case_id = {case_id} LIMIT 1;")
    mort_data = fetch_row(f"SELECT * FROM mortality_form WHERE case_id = {case_id} LIMIT 1;")
    health_data = fetch_row(f"SELECT * FROM health_status_form WHERE case_id = {case_id} LIMIT 1;")

    raw_data_str = f"""
    Biosecurity Form: {bio_data}
    Mortality Form: {mort_data}
    Health Status Form: {health_data}
    """

    case_summary_task = Task(
        description=(
            "For case_id 123, generate a high-level summary of the following forms:\n"
            f"{raw_data_str}\n\n"
            "- biosecurity_form\n"
            "- mortality_form\n"
            "- health_status_form\n\n"
            "Format the output exactly like this:\n\n"
            "Case #<case_id>:\n\n"
            "Biosecurity Form: <short summary>\n"
            "Mortality Form: <short summary>\n"
            "Health Status Form: <short summary>\n"
            "Do not include any extra commentary, formatting, or explanations."
        ),
        agent=issue_management_agent,
        expected_output="Concise natural language summaries of the forms for case_id 123.",
        output_file="formatted_case_summary.txt"
    )

    crew = Crew(
    agents=[case_summary_task.agent],
    tasks=[case_summary_task],
    verbose=True
    )
    return crew.kickoff()

def generate_report_for_forms(case_id):
    # Fetch each form's data and the farmer problem manually
    bio_data_full = fetch_row(f"SELECT * FROM biosecurity_form WHERE case_id = {case_id} LIMIT 1;")
    mort_data_full = fetch_row(f"SELECT * FROM mortality_form WHERE case_id = {case_id} LIMIT 1;")
    health_data_full = fetch_row(f"SELECT * FROM health_status_form WHERE case_id = {case_id} LIMIT 1;")
    problem_desc = fetch_row(f"SELECT problem_description FROM farmer_problem WHERE case_id = {case_id} LIMIT 1;")

    full_report_data_str = f"""
    Biosecurity Form: {bio_data_full}
    Mortality Form: {mort_data_full}
    Health Status Form: {health_data_full}
    Farmer's Problem: {problem_desc[0] if problem_desc else "No problem description found."}
    """

    report_forms_with_farmer_task = Task(
        description=(
            "Use the following data to generate a report for case_id 123:\n\n"
            f"{full_report_data_str}\n\n"
            "Format the output strictly like this (DO NOT wrap the output in triple backticks):\n\n"
            "Biosecurity Form for Case #123:\n"
            "- Field Name 1 — Value 1\n"
            "- Field Name 2 — Value 2\n"
            "...\n\n"
            "Mortality Form for Case #123:\n"
            "- Field Name 1 — Value 1\n"
            "...\n\n"
            "Health Status Form for Case #123:\n"
            "- Field Name 1 — Value 1\n"
            "...\n\n"
            "Farmer's Problem:\n"
            "<problem_description>\n\n"
            "Do not include commentary, markdown, or formatting beyond what's specified. Do not wrap the output in any code blocks."
        ),
        agent=issue_management_agent,
        expected_output="Full detailed listing of forms and farmer comments, without wrapping the output in triple backticks.",
        tools=[sqlite_tool],
        output_file="full_forms_report.txt"
    )

    crew = Crew(
    agents=[report_forms_with_farmer_task.agent],
    tasks=[report_forms_with_farmer_task],
    verbose=True
    )
    return crew.kickoff()

def generate_summary_of_all_issues():
    total_cases = fetch_row("SELECT COUNT(*) FROM issues;")[0]
    open_cases = fetch_row("SELECT COUNT(*) FROM issues WHERE status = 'Open';")[0]
    closed_cases = fetch_row("SELECT COUNT(*) FROM issues WHERE status = 'Closed';")[0]

    # Format using bullet points
    issue_summary_str = (
        f"- Total Cases: {total_cases}\n"
        f"  - Open Cases: {open_cases}\n"
        f"  - Closed Cases: {closed_cases}\n"
    )

    # --- Per-Farm Breakdown ---
    cases = fetch_all("SELECT farm_name, status FROM issues;")

    farm_summary = defaultdict(lambda: {"Total": 0, "Open": 0, "Closed": 0, "Needs Tech Help": 0})
    for farm_name, status in cases:
        farm_summary[farm_name]["Total"] += 1
        if status in farm_summary[farm_name]:
            farm_summary[farm_name][status] += 1

    # Format farm summary as a monospaced table
    farm_summary_str = "Case Summary by Farm:\n"
    farm_summary_str += f"{'Farm Name':<20} {'Total':<6} {'Open':<6} {'Closed':<8} {'Needs Tech Help':<17}\n"
    farm_summary_str += "-" * 60 + "\n"
    for farm, counts in farm_summary.items():
        farm_summary_str += f"{farm:<20} {counts['Total']:<6} {counts['Open']:<6} {counts['Closed']:<8} {counts['Needs Tech Help']:<17}\n"

    # Combine all parts
    final_report = issue_summary_str + "\n<pre>" + farm_summary_str.strip() + "</pre>"

    summary_all_issues_task = Task(
        description=(
            "Here is the pre-fetched issue summary across all farms and statuses:\n\n"
            f"{final_report}\n\n"
            "Reprint this report exactly as shown above.\n"
            "Do not modify the content or formatting.\n"
            "Your output must include:\n"
            "- Total, Open, and Closed case counts\n"
            "- Per-farm breakdown table with case statuses\n"
            "No additional commentary or explanations are allowed."
        ),
        agent=issue_management_agent,
        expected_output="Full database case summary with farm-level breakdown.",
        tools=[sqlite_tool],
        output_file="issues_summary.txt"
    )

    crew = Crew(
    agents=[summary_all_issues_task.agent],
    tasks=[summary_all_issues_task],
    verbose=True
    )
    return crew.kickoff()

# Task for Status Update
def execute_generated_sql(sql: str):
    conn = sqlite3.connect("poultry_data.db")
    cursor = conn.cursor()
    cursor.execute(sql)
    conn.commit()
    conn.close()

def execute_generated_sql(sql: str):
    """Execute a dynamically generated SQL statement."""
    try:
        conn = sqlite3.connect("poultry_data.db")
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Error executing SQL: {e}")

def check_case_exists(case_id: str) -> bool:
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect("poultry_data.db")  # Make sure to adjust the path if necessary
        cursor = conn.cursor()
        
        # Check if the case_id exists in your case-related table (assuming 'issues' table here)
        cursor.execute("SELECT COUNT(*) FROM issues WHERE case_id = ?", (case_id,))
        result = cursor.fetchone()
        
        conn.close()
        
        # Return True if the case_id exists, otherwise False
        return result[0] > 0
    except Exception as e:
        print(f"Error checking case ID in DB: {e}")
        return False

def manually_update_case(case_id: str, reason: str):
    """Update the status of a case directly in the database."""
    sql = f"""
        UPDATE issues 
        SET status = 'Closed', close_reason = '{reason}' 
        WHERE case_id = {case_id};
    """
    execute_generated_sql(sql)  # Use execute_generated_sql to run the query

def close_case_with_reason(case_id: str, reason: str) -> str:
    """Close the case with a provided reason."""
    try:
        # Manually update the case in the database
        manually_update_case(case_id, reason)
        return f"Case {case_id} has been closed successfully with reason: {reason}"
    except Exception as e:
        return f"❌ Error: {e}"
    
def execute_case_closing(case_id: str, reason: str) -> str:
    """Close a case using CrewAI's task execution flow."""
    close_task = Task(
        description=f"Close case {case_id} with the reason: {reason}",
        agent=status_update_agent,
        expected_output="Case closed confirmation",
        tools=[sqlite_tool],
        output_file="closed_case_confirmation.txt"
    )

    crew = Crew(
        agents=[status_update_agent],
        tasks=[close_task],
        verbose=True
    )
    return crew.kickoff()

# Task for Notification
send_notification_task = Task(
    description=(
        "Send a notification to the appropriate team when an issue is marked 'Closed' or 'Needs Tech Help'.\n"
        "Your response must strictly follow this format:\n\n"
        "Notification sent to <team>: ID <id> has been marked as '<new_status>'.\n"
    ),
    agent=notification_agent,
    expected_output="A confirmation that notification was sent to the appropriate team."
)