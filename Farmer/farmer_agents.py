# crew_sql_agent.py
from crewai import Agent, Task, Crew
from crewai.telemetry import Telemetry
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from IPython.display import Markdown
from typing import Dict, Any
import sqlite3
import os

# Load API key from .env
load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
# os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

# telemetry connection fix
def noop(*args, **kwargs):
    # with open("./logfile.txt", "a") as f:
    #     f.write("Telemetry method called and noop'd\n")
    pass
for attr in dir(Telemetry):
    if callable(getattr(Telemetry, attr)) and not attr.startswith("__"):
        setattr(Telemetry, attr, noop)

# --- 1. Form Definition ---
form_definitions = {
    "biosecurity_form": {
        "Farm Entry Protocols": "What protocols are followed before someone can enter the farm? (e.g., Change boots and clothes, wash hands, register name)",
        "Disinfectant Used": "Which disinfectants do you use regularly? (e.g., Virkon S, bleach solution, iodine)",
        "Footbath Availability": "Is a footbath provided at all entrances to animal areas? (e.g., Yes / No / Not Reinforced)",
        "Protective Clothing Provided": "What type of protective clothing is provided for visitors/workers? (e.g., Boots, coveralls, gloves)",
        "Frequency of Disinfection": "How often are animal enclosures disinfected? (e.g., Daily, once a week, after every batch)",
        "Any Recent Biosecurity Breach": "Describe any recent biosecurity incident and your response. (e.g., Visitor entered without footbath, cleaned area immediately and disinfected)"
    },
    "mortality_form": {
        "Number of Deaths": "How many chickens died in the past 7 days? (e.g., 15)",
        "Age Group Affected": "What age group of the chickens were affected? (e.g., 0–2 weeks, 3–6 weeks, Layers, Breeders)",
        "Date of First Death": "When did the first death occur? (e.g., 3/4/2024)",
        "Pattern of Deaths": "Were deaths sudden or gradual over time? (e.g., Sudden / Gradual)"
    },
    "health_status_form": {
        "General Flock Health": "How would you describe the overall health of your flock today? (e.g., Good, Fair, Poor)",
        "Visible Symptoms": "What are the symptoms you observed? (e.g., Coughing, diarrhea, swollen eyes, weak legs)",
        "Feed and Water Intake": "Have you noticed any decrease in feed or water consumption? (Yes / No)",
        "Vaccination Status": "What are the vaccinations the chickens have taken? (e.g., Newcastle disease, Infectious bronchitis)",
        "Other Health Concerns": "Do you have any other health concerns about the chickens? (e.g., Sudden drop in egg production, feather loss)"
    }
}

# --- 2. Prompt Builder ---
# def build_prompt(forms_dict):
#     prompt = "You are a backend developer assistant. Generate SQL `CREATE TABLE IF NOT EXISTS` statements for each form below.\n"
#     prompt += "Each table must include:\n"
#     prompt += "- id INTEGER PRIMARY KEY AUTOINCREMENT\n"
#     prompt += "- case_id TEXT\n"
#     prompt += "- user TEXT\n"
#     prompt += "- timestamp DATETIME DEFAULT CURRENT_TIMESTAMP\n"
#     prompt += "Use `snake_case` for all field names.\n\n"
#     for form, fields in forms_dict.items():
#         prompt += f"Form: {form}\nFields:\n"
#         for field in fields:
#             prompt += f"- {field}\n"
#         prompt += "\n"
#     prompt += "Return only the SQL statements in one markdown code block"
#     return prompt
  
def format_form_dict(forms_dict):
    form_info = ""
    for form, fields in forms_dict.items():
      form_info += f"Form: {form}\nFields:\n"
      for field in fields:
          form_info += f"- {field}\n"
      form_info += "\n"
    return form_info
  
# ======================DB INITIALIZER AGENTS======================

# --- 3. Define the Agent ---
sql_create_agent = Agent(
    role="SQL Table Builder",
    goal="Generate SQLite table creation scripts based on form fields",
    backstory="You assist backend engineers by translating structured form definitions into clean SQL schema statements.",
    verbose=True,
    allow_delegation=False,
    llm=ChatOpenAI(model_name="gpt-4o")
)

# --- 4. Define the Task ---
sql_create_task = Task(
    description=f"""You are a backend developer assistant. Generate SQL `CREATE TABLE IF NOT EXISTS` statements for each form below.
    Each table must include:
    - id INTEGER PRIMARY KEY AUTOINCREMENT
    - case_id TEXT
    - user TEXT
    - timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    Use `snake_case` for all field names.
    {format_form_dict(form_definitions)}
    Return only the SQL statements in one markdown code block""",
    expected_output="SQL `CREATE TABLE` statements for each form in a single markdown code block like ```sql ...```",
    agent=sql_create_agent
)

# --- 5. Run the Crew ---
schema_builder_crew = Crew(
    agents=[sql_create_agent],
    tasks=[sql_create_task],
    verbose=False,
    memory=False
)

# Execute
result = schema_builder_crew.kickoff()
print(result)
sqlbuilder_output = str(result)

def extract_sql_block(result_text: str) -> str:
    if result_text.startswith("```sql"):
        return result_text.strip().removeprefix("```sql").removesuffix("```").strip()
    return result_text.strip()

# Usage:
clean_sql = extract_sql_block(sqlbuilder_output)
print(clean_sql)

# ======================CRUD HANDLER MAIN AGENT======================

# llm = ChatOpenAI(model_name="gpt-4o")

# create_agent = Agent(
#     role="Form Data Inserter",
#     goal="Insert new form records into the correct SQLite table",
#     backstory="You are responsible for creating new rows for submitted form data.",
#     verbose=True,
#     allow_delegation=False,
#     llm=llm
# )

# read_agent = Agent(
#     role="Form Data Reader",
#     goal="Retrieve form data from the database based on case ID or user ID.",
#     backstory="You help users or other agents by fetching stored data.",
#     verbose=True,
#     allow_delegation=False,
#     llm=llm
# )

# update_agent = Agent(
#     role="Form Data Updater",
#     goal="Update existing form records in the SQLite table",
#     backstory="You ensure data stays current by updating existing entries based on the case ID and user.",
#     verbose=True,
#     allow_delegation=False,
#     llm=llm
# )

# delete_agent = Agent(
#     role="Form Data Deleter",
#     goal="Delete form records based on the provided case ID or form name",
#     backstory="You handle removal of form data when a user cancels or resets a case.",
#     verbose=True,
#     allow_delegation=False,
#     llm=llm
# )

# custom_query_agent = Agent(
#     role="Natural Language Query Handler",
#     goal="Interpret dynamic instructions from frontend and generate precise SQL statements",
#     backstory="You understand natural-language prompts from the frontend and convert them into valid SQL for SQLite databases.",
#     verbose=True,
#     allow_delegation=False,
#     llm=llm
# )

# # ============================TASK==============================

# def generate_task(action, form_name=None, fields=None, data_dict=None, case_id=None, user_id=None, custom_prompt=None):
#     if action == "query":
#         return Task(
#             description=f"""You are a SQL assistant. Translate the following instruction into an accurate SQL query that works for SQLite:

# Instruction:
# {custom_prompt}

# Wrap the output in one SQL code block like ```sql ... ```""",
#             expected_output="SQL statement in a single markdown code block",
#             agent=custom_query_agent
#         )
    
#     field_lines = "\n".join([f"- {f}" for f in fields]) if fields else ""
#     data_lines = "\n".join([f"{k}: {v}" for k, v in data_dict.items()]) if data_dict else ""

#     base_description = f"""
# You are handling a {action.upper()} operation on the `{form_name}` table.
# The table has the following fields:
# {field_lines}

# Current user session:
# - case_id: {case_id}
# - user: {user_id}

# Here is the data received from the user:
# {data_lines}
# """

#     if action == "create":
#         return Task(
#             description=base_description + "\n\nGenerate a SQL `INSERT INTO` statement for the form.",
#             expected_output="A single `INSERT INTO` SQL statement wrapped in a markdown code block.",
#             agent=create_agent
#         )
#     elif action == "update":
#         return Task(
#             description=base_description + "\n\nGenerate a SQL `UPDATE` statement based on `case_id` and `user`.",
#             expected_output="A single `UPDATE` SQL statement wrapped in a markdown code block.",
#             agent=update_agent
#         )
#     elif action == "delete":
#         return Task(
#             description=base_description + "\n\nGenerate a SQL `DELETE FROM` statement for this form using `case_id`.",
#             expected_output="A single `DELETE FROM` SQL statement wrapped in a markdown code block.",
#             agent=delete_agent
#         )
#     elif action == "read":
#         return Task(
#             description=base_description + "\n\nGenerate a SQL `SELECT * FROM` query to retrieve the data.",
#             expected_output="A single `SELECT` SQL statement wrapped in a markdown code block.",
#             agent=read_agent
#         )
        
# # =================================CREW=====================================
        
# def run_form_crew(action, form_name, fields, data_dict, case_id, user_id):
#     task = generate_task(action, form_name, fields, data_dict, case_id, user_id)

#     crew = Crew(
#         agents=[task.agent],
#         tasks=[task],
#         verbose=True,
#         memory=False
#     )

#     result = crew.kickoff()
#     return result
  
  
# # Example input
# user_input = {
#     "form_name": "biosecurity_form",
#     "action": "create",  # can be create/update/delete/read
#     "data": {
#         "Farm Entry Protocols": "Yes",
#         "Disinfectant Used": "Bleach",
#         "Footbath Availability": "Yes",
#         "Protective Clothing Provided": "Yes",
#         "Frequency of Disinfection": "Weekly",
#         "Any Recent Biosecurity Breach": "None"
#     },
#     "case_id": "ABC123",
#     "user_id": "user_001"
# }

# # Run it
# result = run_form_crew(
#     action=user_input["action"],
#     form_name=user_input["form_name"],
#     fields=form_definitions[user_input["form_name"]],
#     data_dict=user_input["data"],
#     case_id=user_input["case_id"],
#     user_id=user_input["user_id"]
# )

# print(result)

sql_agent = Agent(
    name="SQLGeneratorAgent",
    role="SQL Query Expert",
    goal="Generate SQL statements from natural language instructions using form schema and known patterns",
)

form_def_text = "\n\n".join([
    f"{form}:\n" + "\n".join([f"- {field}" for field in fields])
    for form, fields in form_definitions.items()
])

user_input = "Get all forms with case_id = 123 and no null in any field"

task_description = f"""
You are a SQL expert agent. Your job is to generate SQL statements to fulfill user input using the provided schema.

User input: "{user_input}"

Here are the known forms and their fields:
{form_def_text}

The query must:
- Check all 3 forms (biosecurity_form, mortality_form, health_status_form)
- Only return records where all fields are non-null and non-empty
- Use WHERE case_id = 123

Generate one SQL SELECT query for each form.
Return SQL only.
"""

task = Task(
    description=task_description,
    agent=sql_agent
)

crew = Crew(
    agents=[sql_agent],
    tasks=[task],
    verbose=True
)

result = crew.kickoff()
print(result)