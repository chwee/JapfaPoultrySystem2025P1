import os
import sqlite3
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from crewai import Agent, Task, Crew



# Load .env variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

os.environ["CREWAI_TELEMETRY_ENABLED"] = "FALSE"

from Sales.tools import SQLiteTool, NotificationTool

sqlite_tool = SQLiteTool(db_path="Sales/poultry_data.db")
notification_tool = NotificationTool()

# Define the format function to format the case summary report
def format_case_report(biosecurity_data, mortality_data, health_status_data):
    report = "Case Report:\n\n"
    
    # Format Biosecurity Form Data
    if biosecurity_data:
        report += f"Biosecurity Form: {biosecurity_data[5]} (Location: {biosecurity_data[2]}, Breach Type: {biosecurity_data[3]})\n"
    else:
        report += "Biosecurity Form: No data available.\n"
    
    # Format Mortality Form Data
    if mortality_data:
        report += f"Mortality Form: {mortality_data[4]} (Number Dead: {mortality_data[2]}, Cause: {mortality_data[3]})\n"
    else:
        report += "Mortality Form: No data available.\n"
    
    # Format Health Status Form Data
    if health_status_data:
        report += f"Health Status Form: {health_status_data[4]} (Symptoms: {health_status_data[2]}, Vet Comments: {health_status_data[3]})\n"
    else:
        report += "Health Status Form: No data available.\n"
    
    return report

# Define Agents
issue_management_agent = Agent(
    role="Issue Management Agent",
    goal="Generate case summaries, form reports, and system statistics.",
    backstory="An expert agent responsible for reviewing cases and forms to help the sales and technical teams.",
    tools=[sqlite_tool],
    allow_delegation=True,
    llm=ChatOpenAI(model_name="gpt-4o", temperature=0.3)  # lower temp for more factual outputs
)

status_update_agent = Agent(
    role="Status Update Agent",
    goal="Help Sales/Technical team mark issues as 'Closed' or 'Needs Tech Help'.",
    backstory="An expert in updating issue statuses and generating appropriate SQL queries to reflect changes.",
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

# Define the Formatting Agent using CrewAI
# formatting_agent = Agent(
#     role="Formatting Agent",
#     goal="Format case summaries, form reports, and system statistics into a readable output.",
#     backstory="An agent responsible for formatting raw case data into structured and readable summaries for various reports.",
#     tools=[sqlite_tool],  # This will allow the agent to interact with the database if needed
#     llm=ChatOpenAI(model_name="gpt-4o", temperature=0.3)  # This ensures more factual and structured outputs
# )

# Task for Issue Management
fetch_issue_task = Task(
    description="Fetch the list of issues based on their open or closed status from the database.",
    agent=issue_management_agent,
    expected_output="List of open or closed issues with relevant fields (id, title, status)."
)

fetch_issue_details_task = Task(
    description="Fetch detailed information for a selected ID.",
    agent=issue_management_agent,
    expected_output="Full details of the issue including description, assigned team, and history."
)

generate_sql_task = Task(
    description="Generate a valid SQL query based on the provided natural language description of a reporting need.",
    agent=issue_management_agent,
    expected_output="A valid SQL query string."
)

case_summary_task = Task(
    description="Generate a summary report for case_id 123 using biosecurity_form, mortality_form, and health_status_form.",
    agent=issue_management_agent,
    expected_output="A formatted summary report for a given case.",
    output_file="formatted_case_summary.txt"
)

report_forms_with_farmer_task = Task(
    description=(
        "For case_id 123, fetch all fields from:\n"
        "- biosecurity_form\n"
        "- mortality_form\n"
        "- health_status_form\n"
        "Also fetch the 'problem_description' from the farmer_problem table.\n\n"
        "Format the output strictly like this:\n\n"
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
        "Do not include commentary or formatting beyond what's specified."
    ),
    agent=issue_management_agent,
    expected_output="Full detailed listing of forms and farmer comments.",
    tools=[sqlite_tool],
    output_file="full_forms_report.txt"
)

summary_all_issues_task = Task(
    description=(
        "Generate a summary report for all cases in the database.\n"
        "Fetch and calculate:\n"
        "- Total number of cases\n"
        "- Number of Open cases\n"
        "- Number of Closed cases\n"
        "- Percentage of cases related to Biosecurity, Mortality, and Health Status\n\n"
        "Output strictly as:\n\n"
        "Total Cases: <number>\n"
        "Open Cases: <number>\n"
        "Closed Cases: <number>\n"
        "Percentage of Biosecurity Cases: <number>%\n"
        "Percentage of Mortality Cases: <number>%\n"
        "Percentage of Health Status Cases: <number>%\n\n"
        "No other commentary or lines allowed."
    ),
    agent=issue_management_agent,
    expected_output="A simple count and breakdown of cases in a text format.",
    tools=[sqlite_tool],
    output_file="issues_summary.txt"
)


# Task for Status Update
update_issue_status_task = Task(
    description="Update the status of an issue in the database to 'Closed' or 'Needs Tech Help' based on user input.",
    agent=status_update_agent,
    expected_output="Database updated successfully with new status for the given id."
)

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

def _run(self, query: str) -> str:
    """Execute the query and return a formatted case report."""
    # Connect to the database
    connection = sqlite3.connect(self.db_path)
    cursor = connection.cursor()

    try:
        cursor.execute(query)
        result = cursor.fetchall()

        # Assuming the result contains data for biosecurity, mortality, and health status forms
        # Call the format_case_report method to generate the formatted report
        case_report = format_case_report(result[0], result[1], result[2])

        return case_report

    except Exception as e:
        return f"Error: {e}"

    finally:
        cursor.close()
        connection.close()

# Adding this _run method to your agent will enable it to generate a formatted report
issue_management_agent._run = _run

# Create Crew
sales_technical_chatbot_crew = Crew(
    agents=[
        issue_management_agent,
        status_update_agent,
        notification_agent
    ],
    tasks=[
        fetch_issue_task,
        fetch_issue_details_task,
        generate_sql_task,
        case_summary_task,
        report_forms_with_farmer_task,
        summary_all_issues_task,
        update_issue_status_task,
        send_notification_task
    ],
    verbose=True  # You can see detailed logs of what happens
)

result = sales_technical_chatbot_crew.kickoff()
print(result)