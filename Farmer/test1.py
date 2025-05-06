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

forms = []

for key in form_definitions:
  forms.append(key)

completed = {
    "biosecurity": False,
    "mortality": False,
    "health_status": False
}

completed2 = {
    forms[0]: False,
    forms[1]: False,
    forms[2]: False
}

completed3 = {}
for form in forms:
  completed3[form] = False
  

print("com", completed)
print("2", completed2)
print("3", completed3)
