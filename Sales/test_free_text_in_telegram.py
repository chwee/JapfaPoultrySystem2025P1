import os
import sqlite3
import json
import re
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
from crewai.tools import BaseTool

# Load .env variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model_name="gpt-4o")

os.environ["CREWAI_TELEMETRY_DISABLED"] = "1"

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

# Replace this with your schema
schema = """
Tables:
- biosecurity_form(id, case_id, farm_location, breach_type, affected_area, timestamp)
- mortality_form(id, case_id, number_dead, cause_of_death, timestamp)
- health_status_form(id, case_id, symptoms_observed, vet_comments, timestamp)
- issues(id, title, description, farm_name, status, assigned_team, case_id, created_at, updated_at)
- farmer_problem(id, case_id, problem_description, timestamp)
"""

sqlite_tool = SQLiteTool(db_path="poultry_data.db")

# AGENTS
sql_agent = Agent(
    role="SQL Query Generator",
    goal="Generate safe, parameterized SQL queries to retrieve valid form records.",
    backstory="Expert database analyst that writes clean, secure SQL queries based on user input.",
    verbose=True,
    allow_delegation=False,
    llm=ChatOpenAI(model_name="gpt-4o", temperature=0.3)
)

issue_management_agent = Agent(
    role="Issue Management Agent",
    goal="Generate case summaries, form reports, and system statistics.",
    backstory="An expert agent responsible for reviewing cases and forms to help the sales and technical teams.",
    tools=[sqlite_tool],
    allow_delegation=True,
    llm=ChatOpenAI(model_name="gpt-4o", temperature=0.3)
)

status_update_agent = Agent(
    role="Status Update Agent",
    goal="Help Sales/Technical team mark issues as 'Closed' or 'Needs Tech Help'.",
    backstory="An expert in updating issue statuses and generating appropriate SQL queries to reflect changes.",
    allow_delegation=False,
    llm=ChatOpenAI(model_name="gpt-4o", temperature=0.3)
)

report_generation_agent = Agent(
    role="Report Generator",
    goal="Format the SQL query results into a readable report.",
    backstory="A skilled report generator capable of transforming raw data into clear and concise reports.",
    verbose=True,
    allow_delegation=False,
    llm=ChatOpenAI(model_name="gpt-4o", temperature=0.3)
)

# TASKS
def generate_and_execute_sql(schema: str, db_path: str = "poultry_data.db", action_type: str = None, case_id: int = None, user_input:str = None) -> dict:
    if user_input is None:
        # Create the SQL generation prompt
        if action_type == "case_summary":
            user_input = f"Given the case_id {case_id}, show me ALL form fields and their respective data for ALL the tables in the database. Return the results."
        elif action_type == "generate_report":
            user_input = f"Generate a full report for case ID {case_id}."
        elif action_type == "view_all_issues":
            user_input = "Retrieve all issues from the issues table."
        else:
            raise ValueError("Unknown action_type")
    
    sql_prompt = f"""
You are an SQL generation agent. Your job is to generate **parameterized SQL** statements to fulfill the following task:

--- USER INPUT ---
"{user_input}"
------------------

Instructions:
- Use the known form schemas listed below.
- Check all tables listed.
- Each query must only return rows where *all fields are non-null and non-empty ('')*.
- Replace placeholders with provided values (e.g., case_id = 123).
- Do NOT return explanations, only the SQL queries.
- Return the output in **JSON format** with keys as table names and values as SQL strings.
- Use lowercase snake_case field names exactly as defined in the schema (not display labels).

--- FORM SCHEMA ---
{schema}
-------------------

Final Output Format (**EXAMPLE**):

```json
{{
  "biosecurity_form": "SELECT * FROM biosecurity_form WHERE case_id = ? AND farm_location IS NOT NULL AND farm_location != '' ...",
  "mortality_form": "...",
  "health_status_form": "...",
  "farmer_problem": "..."
}}
"""
    sql_task = Task(
    description=sql_prompt,
    agent=sql_agent,
    expected_output="JSON with parameterized SQL"
    )
    
    crew = Crew(agents=[sql_agent], tasks=[sql_task], verbose=True)
    result = crew.kickoff()
    print("SQL Generation Result:\n", result)

    # Extract JSON from output
    match = re.search(r'\{[\s\S]*\}', str(result))
    if not match:
        print("No JSON found in output.")
        return {}

    try:
        sql_queries = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        print("Failed to parse SQL JSON:", e)
        return {}

    # Execute queries
    execution_results = {}
    for table, query in sql_queries.items():
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                if case_id is not None:
                    cursor.execute(query, (case_id,))
                else:
                    cursor.execute(query)
                rows = cursor.fetchall()
                execution_results[table] = [dict(zip([col[0] for col in cursor.description], row)) for row in rows]
        except Exception as e:
            execution_results[table] = f"Error executing query: {e}"

    return execution_results

def generate_report_from_prompt(execution_results):
    report_prompt = f"""
    Below is the raw SQL query result data from multiple forms related to a poultry case.

    Your task is to write a professional, human-readable report summarizing the key findings from the data.

    Instructions:
    - Organize the report clearly by form/table.
    - Use complete sentences and avoid overly technical language.
    - Summarize observations, issues, and any notable entries.
    - Do not include raw SQL or technical field names.

    Raw Data:
    {json.dumps(execution_results, indent=2)}
    """

    report_task = Task(
        description=report_prompt,
        agent=report_generation_agent,
        expected_output="A clear and readable summary report.",
        output_file="report_from_prompt.txt"
    )

    report_crew = Crew(agents=[report_generation_agent], tasks=[report_task], verbose=True)
    return report_crew.kickoff()

def generate_individual_case_summary(case_id):
    case_summary_task_description = """
    You have been given the following results from SQL queries on case_id {case_id}. Your task is to generate a high-level summary of the following forms.

    --- SQL RESULTS ---
    Biosecurity Form Results:
    {biosecurity_form_results}

    Mortality Form Results:
    {mortality_form_results}

    Health Status Form Results:
    {health_status_form_results}

    Format the output as follows:
    "Case #{case_id}:\n\n"
    "Biosecurity Form: <short summary>\n"
    "Mortality Form: <short summary>\n"
    "Health Status Form: <short summary>\n"
    """

    execution_results_for_case_summary = generate_and_execute_sql(action_type='case_summary', case_id=case_id, schema=schema)

    # Generate the formatted report using the results from the SQL execution
    case_summary_task_description_filled = case_summary_task_description.format(
        case_id=case_id,
        biosecurity_form_results=execution_results_for_case_summary.get('biosecurity_form', 'No data available.'),
        mortality_form_results=execution_results_for_case_summary.get('mortality_form', 'No data available.'),
        health_status_form_results=execution_results_for_case_summary.get('health_status_form', 'No data available.')
    )

    case_summary_task = Task(
            description=case_summary_task_description_filled,
            agent=report_generation_agent,
            expected_output=f"Concise natural language summaries of the forms for case_id {case_id}.",
            output_file="formatted_case_summary.txt"
        )

    case_summary_crew = Crew(
        agents=[report_generation_agent],
        tasks=[case_summary_task],
        verbose=True
    )

    return case_summary_crew.kickoff()

def generate_report_for_forms(case_id):
    report_task_description = """
    You have been given the following results from SQL queries on case_id {case_id}. Your task is to generate a comprehensive report including the data from the forms.

    --- SQL RESULTS ---
    Biosecurity Form Results:
    {biosecurity_form_results}

    Mortality Form Results:
    {mortality_form_results}

    Health Status Form Results:
    {health_status_form_results}

    Farmer's Problem:
    {farmer_problem_results}

    Format the output as follows:
    Biosecurity Form for Case #{case_id}:
    - Field Name 1 — Value 1
    - Field Name 2 — Value 2
    ...

    Mortality Form for Case #{case_id}:
    - Field Name 1 — Value 1
    - Field Name 2 — Value 2
    ...

    Health Status Form for Case #{case_id}:
    - Field Name 1 — Value 1
    - Field Name 2 — Value 2
    ...

    Farmer's Problem:
    <problem_description>
    """

    execution_results_for_full_report = generate_and_execute_sql(action_type='generate_report', case_id=case_id, schema=schema)

    # Generate the formatted report using the results from the SQL execution
    report_task_description_filled = report_task_description.format(
        case_id=case_id,
        biosecurity_form_results=execution_results_for_full_report.get('biosecurity_form', 'No data available.'),
        mortality_form_results=execution_results_for_full_report.get('mortality_form', 'No data available.'),
        health_status_form_results=execution_results_for_full_report.get('health_status_form', 'No data available.'),
        farmer_problem_results=execution_results_for_full_report.get('farmer_problem', 'No data available.')
    )

    generate_full_report = Task(
        description=report_task_description_filled,
        agent=report_generation_agent,
        expected_output="Formatted report",
        output_file="report_output.txt"
    )

    report_crew = Crew(
        agents=[report_generation_agent],
        tasks=[generate_full_report],
        verbose=True
    )

    return report_crew.kickoff()

def generate_summary_of_all_issues():
    # Access 'issues' data from the 'execution_results'
    execution_results = generate_and_execute_sql(action_type='view_all_issues', schema=schema)
    issues_results = execution_results.get("issues", [])

    # Calculate totals
    total_cases = len(issues_results)
    open_cases = sum(1 for issue in issues_results if issue.get('status') == 'open')
    closed_cases = total_cases - open_cases
    farm_summary = {}

    for issue in issues_results:
        farm_name = issue.get('farm_name', 'Unknown')
        status = issue.get('status', 'open')

        if farm_name not in farm_summary:
            farm_summary[farm_name] = {"total": 0, "open": 0, "closed": 0, "needs_tech_help": 0}

        farm_summary[farm_name]["total"] += 1
        if status == "open":
            farm_summary[farm_name]["open"] += 1
        else:
            farm_summary[farm_name]["closed"] += 1

        # Example: Check if 'Needs Tech Help' based on certain criteria (could be modified)
        if 'tech' in issue.get('assigned_team', '').lower():
            farm_summary[farm_name]["needs_tech_help"] += 1

    # Format summary
    case_summary_by_farm = "\n".join(
        [f"{farm_name:<20} {summary['total']:>5} {summary['open']:>5} {summary['closed']:>5} {summary['needs_tech_help']:>15}" for farm_name, summary in farm_summary.items()]
    )

    # Prepare task description for summary
    summary_task_description = """
    You have been given the following results from SQL queries. Your task is to generate a comprehensive overview of all the issues in the database, using the format below.

    --- SQL RESULTS ---
    Issues Results:
    {issues_results}

    Format the output as follows:
    "Issues Summary:\n"
    "- Total Cases: {total_cases}"
    "  - Open Cases: {open_cases}"
    "  - Closed Cases: {closed_cases}\n"
    "\nCase Summary by Farm:\n"
    "Farm Name            Total  Open   Closed   Needs Tech Help\n"
    "------------------------------------------------------------\n"
    {case_summary_by_farm}
    """

    summary_task_description_filled = summary_task_description.format(
        issues_results=issues_results,
        total_cases=total_cases,
        open_cases=open_cases,
        closed_cases=closed_cases,
        case_summary_by_farm=case_summary_by_farm
    )

    # Create task to generate summary
    summary_task = Task(
        description=summary_task_description_filled,
        agent=report_generation_agent,
        expected_output=f"Summaries of the all the issues in the database, following the format given.",
        output_file="summary_of_all_issues.txt"
    )

    summary_crew = Crew(
        agents=[report_generation_agent],
        tasks=[summary_task],
        verbose=True
    )

    return summary_crew.kickoff()

# Task for Status Update
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
    execute_generated_sql(sql)

def close_case_with_reason(case_id: str, reason: str) -> str:
    """Close the case with a provided reason."""
    try:
        manually_update_case(case_id, reason)
        return f"Case {case_id} has been closed successfully with reason: {reason}"
    except Exception as e:
        return f"❌ Error: {e}"
    
def execute_case_closing(case_id: str, reason: str) -> str:
    """Close a case using CrewAI's task execution flow."""
    close_task = Task(
        description=f"Close case {case_id} with the close_reason as: {reason} in the issues table.",
        agent=status_update_agent,
        tools=[sqlite_tool],
        expected_output="Case closed confirmation"
    )

    crew = Crew(
        agents=[status_update_agent],
        tasks=[close_task],
        verbose=True
    )
    return crew.kickoff()

def get_case_info(case_id: str) -> str:
    conn = sqlite3.connect("poultry_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM issues WHERE case_id = ?", (case_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return "No case information found."

    columns = ["case_id", "status", "description", "close_reason", "created_at"]  # Update based on actual schema
    return "\n".join(f"{col}: {val}" for col, val in zip(columns, row))

# case_id = int(input("Enter the case ID: "))
# prompt = input("Enter the prompt: ")

# prompt_results = generate_and_execute_sql(schema=schema, case_id=case_id, user_input=prompt)
# generate_report_from_prompt(prompt_results)

# generate_report_for_forms(case_id)

# generate_individual_case_summary(case_id)

# generate_summary_of_all_issues()