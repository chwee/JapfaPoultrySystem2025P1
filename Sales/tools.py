from crewai.tools import BaseTool
import sqlite3

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

# NotificationTool
class NotificationTool(BaseTool):
    name: str = "NotificationTool"
    description: str = "Simulates sending notifications to Sales or Technical teams."

    def _run(self, input_text: str) -> str:
        print(f"[NOTIFICATION]: {input_text}")  # Simulate sending a notification
        return f"Notification sent: '{input_text}'"

    async def _arun(self, input_text: str) -> str:
        return self._run(input_text)
