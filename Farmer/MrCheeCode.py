import streamlit as st
import sqlite3
from datetime import datetime
from TestText2SQLAgent import sql_dev, extract_data, Crew, Process, data_analyst, analyze_data, data_insert_validator, validate_insert_data

# Database setup
# def init_db():
#     conn = sqlite3.connect('poultry_health.db')
#     c = conn.cursor()
    
#     # Create tables if they don't exist
#     c.execute('''CREATE TABLE IF NOT EXISTS poultry_health_records
#                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
#                   body_weight REAL,
#                   body_temperature REAL,
#                   vaccination_records TEXT,
#                   symptoms TEXT,
#                   image_analysis TEXT,
#                   created_at TIMESTAMP)''')
                  
#     c.execute('''CREATE TABLE IF NOT EXISTS biosecurity_records
#                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
#                   location TEXT,
#                   violation TEXT,
#                   image_analysis TEXT,
#                   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
#     conn.commit()
#     conn.close()

# # Initialize database
# init_db()

# Main app
st.title("Poultry Farm Management System")

# Sidebar navigation
menu = st.sidebar.selectbox("Select Function", 
                           ["Poultry Health Entry", 
                            "Biosecurity Entry", 
                            "Database Query"])

if menu == "Poultry Health Entry":
    st.header("Poultry Health Data Entry")
    with st.form("health_form"):
        body_weight = st.number_input("Body Weight (kg)", min_value=0.0)
        body_temp = st.number_input("Body Temperature (°C)", min_value=0.0)
        vaccines = st.text_input("Vaccination Records")
        symptoms = st.text_input("Symptoms")
        image_analysis = st.text_area("Image Analysis")
        submitted = st.form_submit_button("Submit")
        
        if submitted:
            query_prompt = f"""
            INSERT INTO poultry_health_records 
            (body_weight, body_temperature, vaccination_records, symptoms, image_analysis, created_at)
            VALUES 
            ({body_weight}, {body_temp}, '{vaccines}', '{symptoms}', '{image_analysis}', '{datetime.now()}');
            """
            
            # Initialize Crew with the query
            crew = Crew(
                agents=[sql_dev, data_insert_validator],
                tasks=[extract_data, validate_insert_data],
                process=Process.sequential,
                verbose=True,
                memory=False,
                output_log_file="crew.log",
            )
            
            # Execute the query through CrewAI
            inputs = {"query": query_prompt}
            result = crew.kickoff(inputs=inputs)
            
            st.success("Record processed successfully!")
            st.write("Query Result:")
            st.code(result)

elif menu == "Biosecurity Entry":
    st.header("Biosecurity Data Entry")
    with st.form("bio_form"):
        location = st.text_input("Location")
        violation = st.text_input("Violation")
        image_analysis = st.text_area("Image Analysis")
        submitted = st.form_submit_button("Submit")
        
        if submitted:
            query_prompt = f"""
            INSERT INTO biosecurity_records 
            (location, violation, image_analysis, created_at)
            VALUES 
            ('{location}', '{violation}', '{image_analysis}', '{datetime.now()}');
            """
            
            crew = Crew(
                agents=[sql_dev],
                tasks=[extract_data],
                process=Process.sequential,
                verbose=True,
                memory=False,
                output_log_file="crew.log",
            )
            
            inputs = {"query": query_prompt}
            result = crew.kickoff(inputs=inputs)
            
            st.success("Record processed successfully!")
            st.write("Query Result:")
            st.code(result)
            st.success("Record added successfully!")
            st.write(f"Added record: Location={location}, Violation={violation}")

elif menu == "Database Query":
    st.header("Database Query")
    query = st.text_area("Enter your query (SQL or natural language)")
    
    if st.button("Execute Query"):
        # Initialize Crew with the query
        crew = Crew(
            agents=[sql_dev, data_analyst],
            tasks=[extract_data, analyze_data],
            process=Process.sequential,
            verbose=True,
            memory=False,
            output_log_file="crew.log",
        )
        
        # Execute the query through CrewAI
        inputs = {"query": query}
        result = crew.kickoff(inputs=inputs)
        
        st.write("Query Results:")
        st.code(result)
        st.success("Query executed successfully!")
