import re

with open("backend/app/services/ai_embeddings.py", "r") as f:
    content = f.read()

# Fix the search_types array
content = content.replace(
    '        "charging_session_summary", "location"\n    ]',
    '        "charging_session_summary", "climate_penalty_summary", "location"\n    ]'
)

with open("backend/app/services/ai_embeddings.py", "w") as f:
    f.write(content)

print("Patch applied to ai_embeddings.py")
