import scrapetube
from youtube_transcript_api import YouTubeTranscriptApi

def test_youtube_scraper(query: str, max_results: int = 5):
    print("=" * 60)
    print(f"Testing YouTube Scraping Engine for Query: '{query}'")
    print("=" * 60)

    try:
        # 1. Search YouTube without API quota
        videos = scrapetube.get_search(query=query, limit=max_results, sort_by="upload_date")
        
        found_any = False
        for idx, video in enumerate(videos, start=1):
            found_any = True
            vid_id = video.get('videoId')
            
            # Extract video title safely
            title = "Unknown Title"
            if 'title' in video and 'runs' in video['title']:
                title = video['title']['runs'][0]['text']

            print(f"\n[{idx}] Video Found: {title}")
            print(f"    ID : {vid_id}")
            print(f"    URL: https://www.youtube.com/watch?v={vid_id}")

            # 2. Extract Transcript
            try:
                transcript_data = YouTubeTranscriptApi().fetch(vid_id, languages=['en', 'hi'])
                full_text = " ".join([chunk['text'] for chunk in transcript_data])
                
                print("    Status: SUCCESS (Transcript Available)")
                print(f"    Transcript Snippet (First 150 chars): \"{full_text[:150]}...\"")
                print(f"    Total Characters Extracted: {len(full_text)}")
                
            except Exception as e:
                print(f"    Status: SKIPPED (Captions unavailable/disabled: {e})")

        if not found_any:
            print("\nNo videos returned for this query.")

    except Exception as general_err:
        print(f"\nScraping pipeline encountered an error: {general_err}")

if __name__ == "__main__":
    # Test with an active topic or known creator content
    test_youtube_scraper(query="breaking updates live", max_results=3)