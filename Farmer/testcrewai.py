import os
from crewai import Agent, Task, Crew
from langchain_openai import ChatOpenAI

# Step 0: Set your OpenAI API key here
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"] 

# Define Route Report Agent
route_report_agent = Agent(
    role="Route Report agent",
    goal="Understand the detailed of the data and requirement of the report and get correct agent to complete task.",
    backstory="An expert report writer specializing in choosing summaries and reports based on patient data.",
    allow_delegation=True,
    llm=ChatOpenAI(model_name="gpt-4o", temperature=0.7)
)


# Define Clinical Report Agent
clinical_report_agent = Agent(
    role="Clinical Report Specialist",
    goal="Write detailed clinical reports when the task involves medical or clinical writing.",
    backstory="An expert medical writer specializing in creating clinical summaries and reports based on patient data.",
    allow_delegation=False,
    llm=ChatOpenAI(model_name="gpt-4o", temperature=0.7)
)

# Define Table Report Agent
table_report_agent = Agent(
    role="Data Table Specialist",
    goal="Format information into structured tables when the task involves tabular data presentation.",
    backstory="A meticulous analyst who structures information into field-value tables for easy data review.",
    allow_delegation=False,
    llm=ChatOpenAI(model_name="gpt-4o", temperature=0.7)
)

def select_agent_based_on_description(description):
    desc_lower = description.lower()
    if "clinical report" in desc_lower:
        return clinical_report_agent
    elif "table report" in desc_lower or "table" in desc_lower:
        return table_report_agent
    else:
        # Default to clinical report agent if not clear
        return clinical_report_agent


def main():
    print("=== Input Patient Data and Report Type ===")
    user_input = input(
        "Paste the patient data and specify the type of report you want "
        "(example: 'Create a clinical report for Patient Name: John Doe, Age: 45, Symptoms: Chest pain'):\n\n"
    )

    # Select agent based on input description
    selected_agent = select_agent_based_on_description(user_input)

    # Create the task dynamically from the user's input
    dynamic_task = Task(
        description=f"{user_input}",
        expected_output="Generate the report as per the requested report type and patient data.",
        agent = route_report_agent
    
    )

    # Both agents are available; CrewAI will pick the right one based on the user's description
    crew = Crew(
        agents=[route_report_agent, clinical_report_agent, table_report_agent],
        tasks=[dynamic_task]
    )

    # Kick off the work
    result = crew.kickoff()
    print("\n=== Final Result ===\n")
    print(result)

if __name__ == "__main__":
    main()