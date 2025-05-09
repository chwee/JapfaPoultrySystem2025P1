#%pip install -q langchain-core langchain-community crewai[tools] langchain-groq


import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List, Tuple, Union

import pandas as pd
from crewai import Agent, Crew, Process, Task
from crewai.tools import tool
from langchain.schema import AgentFinish
from langchain.schema.output import LLMResult
from langchain_community.tools.sql_database.tool import (
    InfoSQLDatabaseTool,
    ListSQLDatabaseTool,
    QuerySQLCheckerTool,
    QuerySQLDataBaseTool,
)
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

import os
from dotenv import load_dotenv
load_dotenv()
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")
os.environ["CREWAI_TELEMETRY_DISABLED"] = "1"
# Step 3. Load Data and Save to SQLite Database
# Load your dataset into a DataFrame and save it to an SQLite database:

# Load the dataset
# df = pd.read_csv("ds_salaries.csv")
# df.head()

# Save the dataframe to an SQLite database
# connection = sqlite3.connect("../database/salaries.db")
# df.to_sql(name="salaries", con=connection)

# Step 4. Set Up Logging
# Configure a logger to track LLM prompts and responses:

@dataclass
class Event:
    event: str
    timestamp: str
    text: str

def _current_time() -> str:
    return datetime.now(timezone.utc).isoformat()

class LLMCallbackHandler(BaseCallbackHandler):
    def __init__(self, log_path: Path):
        self.log_path = log_path

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> Any:
        event = Event(event="llm_start", timestamp=_current_time(), text=prompts[0])
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(event)) + "\n")

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        generation = response.generations[-1][-1].message.content
        event = Event(event="llm_end", timestamp=_current_time(), text=generation)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(event)) + "\n")

# Step 5. Initialize the Language Model
# Set up the language model (LLM) with the logging callback:

# Replace this:
# llm = ChatGroq(api_key="YOUR_GROQ_API_KEY", ...)

# With this:
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    api_key="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",  # Or use environment variable
    model="gpt-4o",          # Or another OpenAI model
    temperature=0.2
)
       

# Step 6. Create SQL Tools
# Define the SQL tools using the @tool decorator:

# Establish a database connection
# db = SQLDatabase.from_uri("sqlite:///salaries.db")
db = SQLDatabase.from_uri("sqlite:///poultry_health.db")

# Tool 1: List all the tables in the database
@tool("list tables")
def list_tables() -> str:
    """List all tables in the database."""
    return ListSQLDatabaseTool(db=db).invoke("")

# Tool 2: Return the schema and sample rows for given tables
@tool("tables_schema")
def tables_schema(tables: str) -> str:
    """Return the schema and sample rows for given tables."""
    tool = InfoSQLDatabaseTool(db=db)
    return tool.invoke(tables)

# Tool 3: Executes a given SQL query
@tool("execute_sql")
def execute_sql(sql_query: str) -> str:
    """Execute a given SQL query and return the result."""
    return QuerySQLDataBaseTool(db=db).invoke(sql_query)

# Tool 4: Checks the SQL query before executing it
@tool("check_sql")
def check_sql(sql_query: str) -> str:
    """Check the SQL query for correctness before executing."""
    return QuerySQLCheckerTool(db=db, llm=llm).invoke({"query": sql_query})

result= check_sql.run("SELECT * WHERE salary > 10000 LIMIT 5 table = salaries")
print(result)

# Step 7. Create Agents
# Define the agents for different roles:

# Agent 1: Database Developer Agent
sql_dev = Agent(
    role="Senior Database Developer",
    goal="Construct and execute SQL queries based on a request",
    backstory=dedent(
        """
        You are an experienced database engineer who is master at creating efficient and complex SQL queries.
        Use the `list_tables` to find available tables.
        Use the `tables_schema` to understand the metadata for the tables.
        Use the `execute_sql` to execute queries.
        Use the `check_sql` to validate your queries.
        """
    ),
    llm=llm,
    tools=[list_tables, tables_schema, execute_sql, check_sql],
    allow_delegation=False,
)

# Agent 2: Data Analyst Agent
data_analyst = Agent(
    role="Senior Data Analyst",
    goal="Analyze the database data response and write a detailed response",
    backstory=dedent(
        """
        You have deep experience with analyzing datasets using Python.
        Your work is always based on the provided data and is clear,
        easy-to-understand and to the point. You have attention
        to detail and always produce very detailed work.
        """
    ),
    llm=llm,
    allow_delegation=False,
)

# Agent 3: Report Editor Agent
report_writer = Agent(
    role="Senior Report Editor",
    goal="Write an executive summary based on the analysis",
    backstory=dedent(
        """
        Your writing is known for clear and effective communication.
        Summarize long texts into concise bullet points with key details.
        """
    ),
    llm=llm,
    allow_delegation=False,
)


# Agent 4: Data Insert Validation Agent
data_insert_validator = Agent(
    role="Data Insert Validation Agent",
    goal="Validate that all required data for SQL insert is provided",
    backstory=dedent(
        """
        You are responsible for ensuring data integrity before any SQL insert operation.
        Your job is to check that all required fields from the user form are present and not missing.
        If any required field is missing, you must report which one and why.
        """
    ),
    llm=llm,
    allow_delegation=False,
)




# Step 8. Create Tasks
# Define the tasks for the agents:

# Task 1: Extract data required for the user query
extract_data = Task(
    description="Extract data that is required for the query {query}.",
    expected_output="Database result for the query",
    agent=sql_dev,
)

# Task 2: Analyze the data from the database
analyze_data = Task(
    description="Analyze the data from the database and write an analysis for {query}.",
    expected_output="Detailed analysis text",
    agent=data_analyst,
    context=[extract_data],
)

# Task 3: Write an executive summary of the analysis
write_report = Task(
    description=dedent(
        """
        Write an executive summary of the report from the analysis. The report
        must be less than 100 words.
        """
    ),
    expected_output="Markdown report",
    agent=report_writer,
    context=[analyze_data],
)

# Task: Validate Insert Data
validate_insert_data = Task(
    description=dedent(
        """
        Check that all required data from the user form {query} for SQL insert is provided and no data is missing.
        The objective is to ensure data completeness before insertion.
        """
    ),
    expected_output="Validation pass or fail with reason",
    agent=data_insert_validator,
    # context=[extract_data],  # Optionally, you can pass the extract_data task as context if needed
)

# Step 9. Setup The Crew
# Initialize the Crew with agents and tasks:

# crew = Crew(
#     agents=[sql_dev, data_analyst, report_writer],
#     tasks=[extract_data, analyze_data, write_report],
#     process=Process.sequential,
#     verbose=True,
#     memory=False,
#     output_log_file="crew.log",
# )
crew = Crew(
    agents=[sql_dev],
    tasks=[extract_data],
    process=Process.sequential,
    verbose=True,
    memory=False,
    output_log_file="crew.log",
)



# Step 10. Kickoff the Crew
# Run the Crew with different queries:

# inputs = {
#     "query": "Effects on salary (in USD) based on company location, size and employee experience"
# }
# result = crew.kickoff(inputs=inputs)
# print(result)
# print(">>>>>>>>>>>>>>>>>>>>>>>")

# inputs = {
#     "query": "How is the `Machine Learning Engineer` salary in USD affected by remote positions"
# }
# result = crew.kickoff(inputs=inputs)
# print("result.......................")
# print(result)


# print(">>>>>>>>>>>>>>>>>>>>>>>")
# inputs = {
#     "query": "How is the salary in USD based on employment type and experience level? "
# }
# result = crew.kickoff(inputs=inputs)
# print(result)

# inputs = {
#     "query": "How are Bio Security violations?"
# }
# result = crew.kickoff(inputs=inputs)
# print("result.......................")
# print(result)

# inputs = {
#     "query": "Insert into Bio Security record with Location = 'ttt777',violation= 'No yellow boot' and image_analysis = `Test image`"
# }
# result = crew.kickoff(inputs=inputs)
# print("result.......................")
# print(result)



# inputs = {
#     "query": "Give the poultry heath records where the symptom is `Cough`"
# }
# result = crew.kickoff(inputs=inputs)
# print("result.......................")
# print(result)


print("END------------------")




