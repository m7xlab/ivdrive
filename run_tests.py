import urllib.request
import json
import time

# Get token
login_req = urllib.request.Request(
    "http://localhost:8000/api/v1/auth/login", 
    data=json.dumps({"email":"m7xlab@gmail.com","password":"dY9BZ84GH47T4sDUS2r6SzilFQ_JQ"}).encode(), 
    headers={"Content-Type": "application/json"}
)
token = json.loads(urllib.request.urlopen(login_req).read())["access_token"]

questions = [
    "What is the battery capacity of JB RS?",
    "What color is BlackMagic?",
    "How many trips did BlackMagic make in May 2026?",
    "What is the total distance driven by BlackMagic in May 2026?",
    "How much energy was charged in BlackMagic in May 2026?",
    "What is the battery health (SOH) of BlackMagic?",
    "Are the doors locked on BlackMagic?",
    "Tell me the WLTP range of the Elroq.",
    "How many charging sessions did JB RS have?",
    "What is the average consumption (kWh/100km) for BlackMagic?",
    "What is the tire pressure of BlackMagic?",
    "Tell me about my Tesla.",
    "Did I charge the BlackMagic in 2020?",
    "What color is BlackMagic and how many km did it drive in May 2026?",
    "Compare the WLTP range of BlackMagic and JB RS.",
    "What was the longest trip for BlackMagic?",
    "How much money did I spend on charging BlackMagic?",
    "What is the max charging power for JB RS?",
    "What is the engine power of Elroq?",
    "When was the last trip recorded for BlackMagic?"
]

print("Running 20 queries against the RAG system...\n")
for i, q in enumerate(questions, 1):
    print(f"Q{i}: {q}")
    req = urllib.request.Request(
        "http://localhost:8000/api/v1/chat", 
        data=json.dumps({"message": q, "model": "gemini"}).encode(), 
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    )
    try:
        resp = json.loads(urllib.request.urlopen(req).read().decode())
        print(f"A{i}: {resp['answer'].strip()}")
        if 'sources' in resp and resp['sources']:
            sources = [s['type'] for s in resp['sources']]
            # Remove duplicates while preserving order
            seen = set()
            sources = [x for x in sources if not (x in seen or seen.add(x))]
            print(f"Sources: {', '.join(sources)}")
        else:
            print("Sources: (Agentic Fallback or No Sources)")
    except Exception as e:
        print(f"Error: {e}")
    print("-" * 60)
    time.sleep(1)
