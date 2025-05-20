import sqlite3
import os

def init_db():
    try:
        db_path = os.path.abspath("poultry_data.db")
        print(f"DB Path: {db_path}")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # === Core Tables ===

        c.execute('''
            CREATE TABLE IF NOT EXISTS flock_farm_information (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER,
                type_of_chicken TEXT,
                age_of_chicken INTEGER,
                housing_type TEXT,
                number_of_affected_flocks INTEGER,
                feed_type TEXT,
                environment_information TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS symptoms_performance_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER,
                main_symptoms TEXT,
                daily_production_performance TEXT,
                pattern_of_spread_or_drop TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS medical_diagnostic_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER,
                vaccination_history TEXT,
                lab_data TEXT,
                pathology_findings_necropsy TEXT,
                current_treatment TEXT,
                management_questions TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                farm_name TEXT,
                status TEXT CHECK(status IN ('Open', 'Closed', 'Needs Tech Help')) DEFAULT 'Open',
                close_reason TEXT,
                assigned_team TEXT,
                case_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS farmer_problem (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER,
                problem_description TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_team TEXT,
                message TEXT,
                sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS issue_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (case_id) REFERENCES issues(case_id)
            )
        ''')

        # === Sample Test Data ===

        # Example Insert into flock_farm_information
        c.execute('''
            INSERT INTO flock_farm_information (
                case_id, type_of_chicken, age_of_chicken, housing_type,
                number_of_affected_flocks, feed_type, environment_information
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            123, 'Layer', 1, 'Closed House', 2, 'Complete Feed', 'Humid, nearby farm within 1 km'
        ))

        # Example Insert into symptoms_performance_data
        c.execute('''
            INSERT INTO symptoms_performance_data (
                case_id, main_symptoms, daily_production_performance, pattern_of_spread_or_drop
            ) VALUES (?, ?, ?, ?)
        ''', (
            123, 'Coughing, sneezing', '{"mortality": 5, "HD%": 92, "feed intake": "low"}', 'Gradual drop in feed intake over 3 days'
        ))

        # Example Insert into medical_diagnostic_records
        c.execute('''
            INSERT INTO medical_diagnostic_records (
                case_id, vaccination_history, lab_data,
                pathology_findings_necropsy, current_treatment, management_questions
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            123, 'IBD, NDV vaccines given', 'Pending', 'Mild hemorrhaging in intestines', 'Tylosin added to water', 'Should we isolate the flock?'
        ))

        c.execute('''
            INSERT INTO issues (title, description, farm_name, status, assigned_team, case_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            'Fence breach and chick deaths resolved', 
            'Farm A reported chicks escaping due to fencing failure, 15 dead. Issue resolved after fencing repair.',
            'Farm A',
            'Open', 
            'Sales', 
            123
        ))

        c.execute('''
            INSERT INTO farmer_problem (case_id, problem_description)
            VALUES (?, ?)
        ''', (
            123, 'We noticed the chicks are getting out of the farm due to broken fencing.'
        ))

        conn.commit()
        print("✅ Tables created and test data inserted successfully!")

    except sqlite3.Error as e:
        print(f"❌ SQLite error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()