import sys
import pandas as pd
import torch
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification, TrainingArguments, Trainer

CSV_FILE = "tweets.csv"

print(f"📂 Loading dataset from '{CSV_FILE}'...")
try:
    df = pd.read_csv(CSV_FILE)
except FileNotFoundError:
    print(f"❌ Error: Could not find '{CSV_FILE}' in your project folder!")
    sys.exit(1)

# 1. LOCATE THE TEXT COLUMN
if "text" in df.columns:
    df["text"] = df["text"].astype(str)
elif "content" in df.columns:
    df["text"] = df["content"].astype(str)
elif "hashtags" in df.columns:
    print("⚠️ 'text' column not found. Using 'hashtags' column as text...")
    df["text"] = df["hashtags"].astype(str)
else:
    print("❌ Error: Could not find any text or hashtags column in your CSV!")
    sys.exit(1)

# 2. LOCATE THE LABEL COLUMN
if "label" in df.columns:
    pass
elif "threat_category" in df.columns:
    df["label"] = df["threat_category"]
elif "category" in df.columns:
    df["label"] = df["category"]
else:
    print("\n" + "="*65)
    print("⚠️ MISSING LABELS: 'tweets.csv' is a raw, unlabelled dataset.")
    print("="*65)
    print(f"Columns found in '{CSV_FILE}':\n{list(df.columns)}\n")
    print("Fine-tuning requires a target category column (like 'threat_category')")
    print("so the AI knows what answers to learn from.\n")
    print("👉 HOW TO PROCEED:")
    print("Run your Zero-Shot batch pipeline first:")
    print("   python run_batch_chunks.py")
    print("\nThis will run zero-shot AI classification on 'tweets.csv' and create")
    print("processed CSV files in 'split_chunks_output/' containing assigned labels!")
    print("="*65 + "\n")
    sys.exit(1)

# Clean missing rows
df = df.dropna(subset=['text', 'label'])

# Convert string categories to numbers for GPU training
unique_labels = df['label'].unique().tolist()
label_to_id = {label: i for i, label in enumerate(unique_labels)}
id_to_label = {i: label for label, i in label_to_id.items()}
df['label'] = df['label'].map(label_to_id)

dataset = Dataset.from_pandas(df)

print("🧠 Loading Tokenizer...")
model_name = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
tokenizer = AutoTokenizer.from_pretrained(model_name)

def tokenize_function(examples):
    return tokenizer(examples["text"], padding="max_length", truncation=True, max_length=128)

print("⚙️ Tokenizing data for GPU...")
tokenized_datasets = dataset.map(tokenize_function, batched=True)

print("🚀 Loading Model into GPU...")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using hardware device: {device}")

model = AutoModelForSequenceClassification.from_pretrained(
    model_name, 
    num_labels=len(unique_labels), 
    id2label=id_to_label, 
    label2id=label_to_id, 
    ignore_mismatched_sizes=True
)

training_args = TrainingArguments(
    output_dir="./results", 
    learning_rate=2e-5, 
    per_device_train_batch_size=16,
    num_train_epochs=3, 
    weight_decay=0.01, 
    fp16=True, 
    save_strategy="epoch",
)

trainer = Trainer(model=model, args=training_args, train_dataset=tokenized_datasets)

print("🔥 STARTING FINE-TUNING ON RTX 4060 GPU...")
trainer.train()

trainer.save_model("./my_custom_threat_model")
tokenizer.save_pretrained("./my_custom_threat_model")
print("✅ DONE! Your fine-tuned model is saved in the 'my_custom_threat_model' folder.")