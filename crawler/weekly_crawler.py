import asyncio
import json
import re
from crawl4ai import AsyncWebCrawler
from your_gemini_wrapper import gemini_extract_links, gemini_summarize_batched, gemini_extract_companies
from email_sender import send_json_email

LISTING_URLS = [
    "https://femtechinsider.com/category/news/",
    "https://femtechinsider.com/category/news/page/2/",
    "https://www.femtechworld.co.uk/latest-news/"
]

async def crawl_markdown(crawler, url: str) -> str:
    result = await crawler.arun(url=url)
    return result.markdown.raw_markdown if result.success else ""

async def main():
    all_article_markdowns = []

    async with AsyncWebCrawler() as crawler:
        for listing_url in LISTING_URLS:
            print(f"🔎 Crawling listing: {listing_url}")
            listing_md = await crawl_markdown(crawler, listing_url)

            print("🤖 Extracting article links with Gemini...")
            article_urls = gemini_extract_links(listing_md)
            print(f"🔗 Found {len(article_urls)} articles")

            for url in article_urls[:15]:
                print(f"📰 Crawling article: {url}")
                article_md = await crawl_markdown(crawler, url)
                if article_md:
                    all_article_markdowns.append(article_md)

    if all_article_markdowns:
        print("📦 Sending all article markdowns to Gemini for summarization (batched)...")
        summary = gemini_summarize_batched(all_article_markdowns, batch_size=8)

        # Remove code block markers if present
        summary_clean = re.sub(r"^```json\s*|\s*```$", "", summary.strip(), flags=re.DOTALL)

        # Parse JSON
        summary_json = json.loads(summary_clean)

        # Optionally extract company names and add to summary_json
        companies = gemini_extract_companies(summary)
        summary_json["companies"] = companies

        # Save JSON to file (optional)
        with open("weekly_summary.json", "w", encoding="utf-8") as f:
            json.dump(summary_json, f, indent=2)

        print("✅ Saved final summary with companies to weekly_summary.json")

        # Send email using the new function
        send_json_email(summary_json)

    else:
        print("⚠️ No articles were successfully crawled.")

if __name__ == "__main__":
    asyncio.run(main())                  # Run the full async crawl/summarize
  