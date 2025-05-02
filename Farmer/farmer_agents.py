# crew_sql_agent.py
from crewai import Agent, Task, Crew
from crewai.telemetry import Telemetry
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from IPython.display import Markdown
from typing import Dict, Any
import sqlite3
import os
import re

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
        "Protective Clothing": "What type of protective clothing is provided for visitors/workers? (e.g., Boots, coveralls, gloves)",
        "Frequency of Disinfection": "How often are animal enclosures disinfected? (e.g., Daily, once a week, after every batch)",
        "Biosecurity Breach": "Describe any recent biosecurity incident and your response. (e.g., Visitor entered without footbath, cleaned area immediately and disinfected)"
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
  
  
# ======================DB INITIALIZER AGENTS======================

def db_init_agent(form_def):
    # Format form def into schema text
    def format_form_dict(forms_dict):
        form_info = ""
        for form, fields in forms_dict.items():
            form_info += f"Form: {form}\nFields:\n"
            for field in fields:
                form_info += f"- {field}\n"
            form_info += "\n"
        return form_info

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
        {format_form_dict(form_def)}
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
    sqlbuilder_output = str(result)

    def extract_sql_block(result_text: str) -> str:
        if result_text.startswith("```sql"):
            return result_text.strip().removeprefix("```sql").removesuffix("```").strip()
        return result_text.strip()

    # Usage:
    clean_sql = extract_sql_block(sqlbuilder_output)
    print(clean_sql)
    return clean_sql

# ================================CREW DYNAMIC SQL GENERATOR=======================================

def to_sql_field_name(label):
    # Lowercase and replace non-alphanumeric characters with underscores
    return re.sub(r'\W+', '_', label.strip().lower())

# 2. Format form definition into readable schema text
def format_form_schema_text(form_defs): 
    shared_fields = [
        "- id INTEGER PRIMARY KEY AUTOINCREMENT",
        "- case_id TEXT",
        "- user TEXT",
        "- timestamp DATETIME DEFAULT CURRENT_TIMESTAMP"
    ]
    
    return "\n\n".join([
        f"Table `{form}` has the following fields:\n" +
        "\n".join(shared_fields + [f"- {to_sql_field_name(field)}" for field in fields.keys()])
        for form, fields in form_defs.items()
    ])

form_def_text = format_form_schema_text(form_definitions)
print(form_def_text)

# 3. User input
user_input = "Return a list of distinct case_ids from all form tables where the user matches a given user ID, ordered by most recent timestamp."
param_value = 123

# 4. Create SQL Agent
sql_agent = Agent(
    name="DynamicSQLAgent",
    role="Database SQL Generator and Validator",
    goal="Generate syntactically correct and secure SQL statements based on natural language instructions and known form schemas.",
    backstory="An AI assistant trained in SQL generation from flexible form structures. Skilled in crafting secure and valid queries dynamically.",
    llm=ChatOpenAI(model_name="gpt-4o")
)

# 5. Generate task dynamically
task_description = f"""
You are an SQL generation agent. Your job is to generate **parameterized SQL** statements to fulfill the following task:

--- USER INPUT ---
"{user_input}"
------------------

Instructions:
- Use the known form schemas listed below.
- Check all form tables listed.
- Each query must only return rows where *all fields are non-null and non-empty ('')*.
- Use a parameter placeholder `?` for the `case_id`, not a hardcoded value.
- Do NOT return explanations, only the SQL queries.
- Return the output in **JSON format** with keys as table names and values as SQL strings.
- Use lowercase snake_case field names exactly as defined in the schema (not display labels).

--- FORM SCHEMA ---
{form_def_text}
-------------------

Final Output Format (example):

```json
{{
  "biosecurity_form": "SELECT * FROM biosecurity_form WHERE case_id = ? AND field1 IS NOT NULL AND field1 != '' ...",
  "mortality_form": "...",
  "health_status_form": "..."
}}
"""

# 6. Create and run Crew
task = Task(
    description=task_description,
    agent=sql_agent,
    expected_output="A JSON dictionary mapping table names to SQL SELECT queries, parameterized with `?`, filtering by case_id and excluding null/empty fields."
)

crew = Crew(
    agents=[sql_agent],
    tasks=[task],
    verbose=True
)

result = crew.kickoff()
print(result)