from services import search_and_extract_by_keyword

def run_scraper_test():
    print("Initiating YouTube bulk extraction...")
    query = "breaking news live"
    
    result = search_and_extract_by_keyword(query, max_videos=5)
    
    print("\n--- FULL EXTRACTION RESULT ---")
    print(f"Total Characters Pulled: {len(result)}")
    
    # Print the entire transcript without any slicing
    print(result)

if __name__ == "__main__":
    run_scraper_test()