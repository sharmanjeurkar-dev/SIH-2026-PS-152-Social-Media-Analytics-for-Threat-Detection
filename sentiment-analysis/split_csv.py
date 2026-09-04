import pandas as pd
import os

# ==========================================
# CONFIGURATION
# ==========================================
# 1. Replace with the actual name of your 1.8 GB file
LARGE_CSV_FILE = "tweets.csv"  

# 2. Number of rows per output file (50,000 rows is approx 50-100 MB)
ROWS_PER_CHUNK = 50000  

# 3. Output directory name
OUTPUT_FOLDER = "split_chunks"

# ==========================================
# SPLITTING LOGIC
# ==========================================
if not os.path.exists(LARGE_CSV_FILE):
    print(f"❌ Error: Could not find '{LARGE_CSV_FILE}'. Check the file name and try again.")
    exit()

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

print(f"📂 Opening {LARGE_CSV_FILE} safely on Lenovo IdeaPad...")
print(f"✂️ Splitting into chunks of {ROWS_PER_CHUNK:,} rows each...\n")

# Process the file in chunks without loading all 1.8 GB into RAM at once
chunk_number = 1
for chunk in pd.read_csv(LARGE_CSV_FILE, chunksize=ROWS_PER_CHUNK, low_memory=False):
    output_filename = os.path.join(OUTPUT_FOLDER, f"chunk_{chunk_number}.csv")
    
    # Save the small CSV file
    chunk.to_csv(output_filename, index=False)
    
    print(f"  ✅ Created: {output_filename} ({len(chunk):,} rows)")
    chunk_number += 1

print(f"\n🎉 Done! Created {chunk_number - 1} smaller CSV files inside the '{OUTPUT_FOLDER}' folder.")