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
import ast

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
        
# =================================================================================================================
        
intent_dict = {
    "get_fully_completed_forms_by_case_id": "Select all fields from each form table to determine if the form linked to the given case_id is fully completed.",
    
    "handle_resume_decision": "Delete an incomplete form entry from its respective table using the provided case_id.",
    
    "confirm_save_biosecurity": "Insert or update a biosecurity_form entry for the given user and case_id with the latest field values from the session.",
    "confirm_save_mortality": "Insert or update a mortality_form entry for the given user and case_id with the latest field values from the session.",
    "confirm_save_health_status": "Insert or update a health_status_form entry for the given user and case_id, including the optional image path if provided.",
    
    "get_forms_by_case_id": "Check whether each form table contains any row with the given case_id to determine form completion status.",
    
    "cancel_entry": "Select fields from each form table to verify if a form is fully filled for the given case_id.",
    
    "cancel_confirmed": "Delete all entries from biosecurity_form, mortality_form, and health_status_form where case_id matches the session's active case.",
    
    "load_incomplete_data": "Select the latest case_id submitted by the given user_id across all form tables, regardless of whether the form is fully completed, by combining and ordering all timestamps.",
    
    "is_form_incomplete": "Select all relevant fields (including image_path if present) from the latest entry in all the form tables for the given user and case_id. Do not exclude rows based on null or empty values. Order results by timestamp descending and limit to 1 row.",
    
    "fallback_resume_prompt_check": "Check if each form table has at least one row for the given case_id to decide whether to show a resume prompt."
}


# =================================================================================================================

# --- 1. Form Definition ---
form_definitions = {
    "1st_stage": {
        "Farm Entry Protocols": "What protocols are followed before someone can enter the farm? (e.g., Change boots and clothes, wash hands, register name)",
        "Disinfectant Used": "Which disinfectants do you use regularly? (e.g., Virkon S, bleach solution, iodine)",
        "Footbath Availability": "Is a footbath provided at all entrances to animal areas? (e.g., Yes / No / Not Reinforced)",
        "Protective Clothing": "What type of protective clothing is provided for visitors/workers? (e.g., Boots, coveralls, gloves)",
        "Frequency of Disinfection": "How often are animal enclosures disinfected? (e.g., Daily, once a week, after every batch)",
        "Biosecurity Breach": "Describe any recent biosecurity incident and your response. (e.g., Visitor entered without footbath, cleaned area immediately and disinfected)"
    },
    "2nd_stage": {
        "Number of Deaths": "How many chickens died in the past 7 days? (e.g., 15)",
        "Age Group Affected": "What age group of the chickens were affected? (e.g., 0–2 weeks, 3–6 weeks, Layers, Breeders)",
        "Date of First Death": "When did the first death occur? (e.g., 3/4/2024)",
        "Pattern of Deaths": "Were deaths sudden or gradual over time? (e.g., Sudden / Gradual)"
    },
    "3rd_stage": {
        "General Flock Health": "How would you describe the overall health of your flock today? (e.g., Good, Fair, Poor)",
        "Visible Symptoms": "What are the symptoms you observed? (e.g., Coughing, diarrhea, swollen eyes, weak legs)",
        "Feed and Water Intake": "Have you noticed any decrease in feed or water consumption? (Yes / No)",
        "Vaccination Status": "What are the vaccinations the chickens have taken? (e.g., Newcastle disease, Infectious bronchitis)",
        "Other Health Concerns": "Do you have any other health concerns about the chickens? (e.g., Sudden drop in egg production, feather loss)"
    }
}

forms = []
for key in form_definitions:
  forms.append(key)
  
  
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
        At the end of each table definition, include this constraint:
        - UNIQUE(case_id, user)
        
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
def dynamic_sql_agent(intent, form_def):
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

    form_def_text = format_form_schema_text(form_def)
    print(form_def_text)

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
    "{intent}"
    ------------------

    Instructions:
    - Use the known form schemas listed below.
    - Check all form tables listed.
    - Each query must only return rows where *all fields are non-null and non-empty ('')* UNLESS STATED OTHERWISE
    - Use a parameter placeholder `?` for the `case_id`, not a hardcoded value.
    - The final output should be in json format with all the forms as the key and the sql statements as the value
    - Respond with a single unified input only if specified in the user input
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
    ```
    OR
    ```json
    {{
    "unified_output": "SELECT case_id, timestamp FROM biosecurity_form WHERE user = ? UNION ALL SELECT case_id, timestamp FROM mortality_form WHERE user = ? ORDER BY timestamp DESC LIMIT 1"
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
    
    def extract_sql_block(result_text: str) -> str:
        if result_text.startswith("```json"):
            return result_text.strip().removeprefix("```json").removesuffix("```").strip()
        return result_text.strip()
    
    return(extract_sql_block(str(result)))

# agent_result = ast.literal_eval(dynamic_sql_agent(intent_dict["confirm_save_biosecurity"]))
# print(agent_result)
# completed = {}
# print("\n========================\n")
# for form in forms:
#     completed[form] = False
#     print("\n========================\n")
#     if not agent_result.get("unified_output"):
#         print(agent_result[form])
#     else:
#         print(agent_result['unified_output'])

  
# print("\n========================\n")
# print(completed)

# if not agent_result.get("unified_output"):
#     print(agent_result[form])
# else:
#     raise Exception