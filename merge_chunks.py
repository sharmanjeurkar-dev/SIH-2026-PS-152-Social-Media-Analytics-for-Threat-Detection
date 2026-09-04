import os
import glob
import pandas as pd

# 1. Define where the chunks are located
output_dir = "split_chunks_output"

# 2. Find all the processed CSV files inside that folder
all_files = glob.glob(os.path.join(output_dir, "chunk_*_processed.csv"))

print(f"📦 Found {len(all_files)} chunk files. Starting the merge process...")

df_list = []

# 3. Read every chunk into memory
for file in all_files:
    try:
        df = pd.read_csv(file)
        df_list.append(df)
    except Exception as e:
        print(f"⚠️ Could not read {file}: {e}")

# 4. Combine them and save the master file
if df_list:
    print("🔄 Combining files together. This might take a few seconds...")
    master_df = pd.concat(df_list, ignore_index=True)
    
    output_filename = "master_processed_threats.csv"
    master_df.to_csv(output_filename, index=False)
    
    print(f"🎉 Success! All chunks merged into '{output_filename}'")
    print(f"📊 Total rows processed and saved: {len(master_df)}")
else:
    print("❌ No files found to merge! Check if 'split_chunks_output' has CSVs inside.")