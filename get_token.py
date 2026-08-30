from supabase import create_client

# Paste your URL and Anon Key from Step 2
url = "https://kvgipccoyrtkbutkvnfj.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt2Z2lwY2NveXJ0a2J1dGt2bmZqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODgwNjE4MDAsImV4cCI6MjEwMzYzNzgwMH0.jmwa1_2wPF98cmcQIeim05FYAtBdZ_PuZmdiPijw8uY"

supabase = create_client(url, key)

# Log in with the mock account you just created
response = supabase.auth.sign_in_with_password({
    "email": "agent1@ntro.gov",
    "password": "supersecure123"
})

print("\n--- YOUR SUPABASE JWT ---")
print(response.session.access_token)
print("-------------------------\n")