import os
import pandas as pd
from member2_pipeline import process_member1_payload

INPUT_CSV = "tweets.csv"          
CHUNK_SIZE = 200                 
OUTPUT_DIR = "split_chunks_output" 
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"🚀 Starting chunked batch execution on {INPUT_CSV}...")

chunk_number = 1
for chunk_df in pd.read_csv(INPUT_CSV, chunksize=CHUNK_SIZE):
    processed_rows = []
    
    for index, row in chunk_df.iterrows():
        # Get the text (or hashtags), and fix Pandas "NaN" missing values
        raw_val = row.get("hashtags")
        post_text = str(raw_val) if pd.notna(raw_val) else ""
        post_text = post_text.strip()
        
        # Build the payload
        payload = {
            "post_id": str(row.get("tweetid", index)),
            "text": post_text,
        }
        
        row_dict = row.to_dict()
        row_dict["processed_text"] = post_text
        
        # SAFETY CHECK: If there is no text/hashtag, skip the AI so it doesn't crash
        if not post_text or post_text.lower() == "nan":
            row_dict["threat_category"] = "No Text Data"
            row_dict["threat_severity_score"] = 0.0
            processed_rows.append(row_dict)
            continue # Skip to the next row
            
        # If there is text, run the AI
        try:
            results = process_member1_payload(payload)
            h4 = results["handoff_to_member4"]
            
            row_dict["threat_category"] = h4.get("zero_shot_threat_category", "Error")
            row_dict["threat_severity_score"] = h4.get("threat_severity_score", 0.0)
            
            # Add any other scores you need here
            row_dict["compound_sentiment_score"] = h4.get("compound_sentiment_score", 0.0)
            
            processed_rows.append(row_dict)
        except Exception as e:
            # If it still crashes, loudly print EXACTLY why so we can see it
            print(f"\n🚨 CRASH ON ROW {index} 🚨")
            print(f"Text tried: '{post_text}'")
            print(f"Error: {e}\n")
            
            # Save it anyway with a failed status so the row isn't lost
            row_dict["threat_category"] = "AI Processing Failed"
            row_dict["threat_severity_score"] = 0.0
            processed_rows.append(row_dict)

    # Save the chunk
    output_chunk_df = pd.DataFrame(processed_rows)
    chunk_filename = os.path.join(OUTPUT_DIR, f"chunk_{chunk_number}_processed.csv")
    output_chunk_df.to_csv(chunk_filename, index=False)
    
    print(f"✅ Chunk {chunk_number} saved with {len(output_chunk_df)} rows: {chunk_filename}")
    chunk_number += 1
    
    # Let's just process 1 chunk first to test it!
    