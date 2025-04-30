import sqlite3
import os

def init_db():
    try:
        db_path = os.path.abspath("poultry_data.db")
        print(f"DB Path: {db_path}")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Create tables
        c.execute('''
            CREATE TABLE IF NOT EXISTS biosecurity_form (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER,
                farm_location TEXT,
                breach_type TEXT,
                affected_area TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS mortality_form (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER,
                number_dead INTEGER,
                cause_of_death TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS health_status_form (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER,
                symptoms_observed TEXT,
                vet_comments TEXT,
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

        # Insert fake data
        c.execute('''
            INSERT INTO biosecurity_form (case_id, farm_location, breach_type, affected_area)
            VALUES (?, ?, ?, ?)
        ''', (
            123, 'New Zealand', 'Fencing failure', 'Southern pasture'
        ))

        c.execute('''
            INSERT INTO mortality_form (case_id, number_dead, cause_of_death)
            VALUES (?, ?, ?)
        ''', (
            123, 15, 'Unknown sudden death'
        ))

        c.execute('''
            INSERT INTO health_status_form (case_id, symptoms_observed, vet_comments)
            VALUES (?, ?, ?)
        ''', (
            123, 'No visible symptoms, but abnormal behavior', 'Observation required over next 48 hours.'
        ))

        c.execute('''
            INSERT INTO issues (title, description, farm_name, status, assigned_team, case_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            'Fence breach and chick deaths', 
            'Farm A reported chicks escaping due to fencing failure, 15 dead.', 
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

        # Commit the changes
        conn.commit()
        print("✅ Tables created and test data inserted successfully!")
    except sqlite3.Error as e:
        print(f"❌ SQLite error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
