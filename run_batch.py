pythoimport pandas as pd
import json
from member2_pipeline import process_member1_payload
import member2_pipeline

# Disable external APIs locally to prevent rate limits
member2_pipeline.NEWS_API_KEY = "DISABLED"
member2_pipeline.YOUTUBE_API_KEY = "DISABLED"

print("📂 Loading split_chunks/chunk_1.csv safely...")
df = pd.read_csv("split_chunks/chunk_1.csv")

results = []
print(f"⚙️ Processing {len(df)} rows through the NLP intelligence engine...")

# Process a safe sample of the first 50 row
for index, row in df.head(50).iterrows():
    mock_payload = {
        "post_id": f"chunk1_row_{index}",
        "timestamp": "2026-09-03T12:00:00Z",
        "platform": "WhatsApp_Import",
        "text": str(row['date']),  # Ensure 'text' matches your column name
        "author": {"user_id": "u_unknown", "handle": "unknown"}
    }
    
    output = process_member1_payload(mock_payload)
    results.append(output)

# Save output for Member 3 and Member 4
with open("team_handoff_output.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=4)

print("✅ Success! Generated 'team_handoff_output.json' for your teammates.")