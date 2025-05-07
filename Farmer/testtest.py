import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)
from farmer_agents import dynamic_sql_agent
from farmer_agents import db_init_agent
import ast
import uuid
import re
import textwrap
import inspect

form_validation = {
    "flock_farm_information": {
        "Type of Chicken": lambda x: x.lower() in ["layer", "broiler", "breeder"],
        "Age of Chicken": lambda x: x.isdigit() and 0 < int(x) < 200,
        "Housing Type": lambda x: x.lower() in ["closed house", "opened-side", "open-sided", "open house"],
        "Number of Affected Flocks/Houses": lambda x: x.isdigit() and int(x) >= 0,
        "Feed Type": lambda x: x.lower() in ["complete feed", "self mix"],
        "Environment Information": lambda x: len(x.strip()) > 10
    },
    "symptoms_performance_data": {
        "Main Symptoms": lambda x: len(x.strip()) > 5,
        "Daily Production Performance": lambda x: len(x.strip()) > 5,
        "Pattern of Spread or Drop": lambda x: len(x.strip()) > 5
    },
    "medical_diagnostic_records": {
        "Vaccination History": lambda x: len(x.strip()) > 5,
        "Lab Data": lambda x: len(x.strip()) > 5,
        "Pathology Findings (Necropsy)": lambda x: len(x.strip()) > 5,
        "Current Treatment": lambda x: len(x.strip()) > 5,
        "Management Questions": lambda x: len(x.strip()) > 5
    }
}

def generate_validation_description_text(form_validation):
    output_lines = []

    for form_name, fields in form_validation.items():
        output_lines.append(f"{form_name.replace('_', ' ').title()} table")
        for field, validator in fields.items():
            try:
                src = textwrap.dedent(inspect.getsource(validator)).strip()

                description = "Unrecognized validation rule."

                # Numeric rules
                if "x.isdigit()" in src and "int(x)" in src:
                    rules = re.findall(r"int\(x\)\s*([<>]=?)\s*(\d+)", src)
                    if rules:
                        parts = []
                        for op, val in rules:
                            op_map = {
                                ">": f"more than {val}",
                                ">=": f"at least {val}",
                                "<": f"less than {val}",
                                "<=": f"at most {val}"
                            }
                            parts.append(op_map.get(op, f"{op} {val}"))
                        description = f"Must be a number {' and '.join(parts)}."
                    else:
                        description = "Must be a valid number."

                # Choice-based rules
                elif "x.lower()" in src and "in" in src:
                    options = re.findall(r"\[([^\]]+)\]", src)
                    if options:
                        opts = [o.strip().strip("'\"") for o in options[0].split(",")]
                        description = f"Must be one of the following: {', '.join(opts)}."

                # Text length
                elif "len(x.strip())" in src:
                    rules = re.findall(r"len\(x\.strip\(\)\)\s*([<>]=?)\s*(\d+)", src)
                    if rules:
                        parts = []
                        for op, val in rules:
                            op_map = {
                                ">": f"more than {val} characters",
                                ">=": f"at least {val} characters",
                                "<": f"less than {val} characters",
                                "<=": f"at most {val} characters"
                            }
                            parts.append(op_map.get(op, f"{op} {val} characters"))
                        description = f"Must be " + " and ".join(parts) + "."

                output_lines.append(f"- {field}: {description}")

            except Exception as e:
                output_lines.append(f"- {field}: Could not extract rule.")

        output_lines.append("")  # Add blank line between forms

    return "\n".join(output_lines)
  
  
print(generate_validation_description_text(form_validation))