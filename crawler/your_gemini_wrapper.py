import re
from google.generativeai import GenerativeModel
from urllib.parse import urlparse
import os
from dotenv import load_dotenv
from datetime import date
import time
import json

# Load API key from .env
load_dotenv()
from google import generativeai as genai
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = GenerativeModel("gemini-2.0-flash")

# Define common substrings to filter
NON_ARTICLE_SUBSTRINGS = [
    "/category/", "/tag/", "/author/", "/about/",
    "/advertise/", "/media-kit/", "/contact/",
    "/events/", "/privacy", "/terms", "/faq", "/health-club-management-features/", "/property/",
    "/health-club-management-press-releases/", "/health-club-management-company-profile/"
]

today = date.today().strftime("%B %d, %Y")

def _generate_with_retry(prompt: str, *, max_retries: int = 6, base_delay_seconds: float = 2.0):
    """Call Gemini with exponential backoff on rate limits and transient errors.

    - Retries up to max_retries times
    - Exponential backoff with jitter
    - Returns response.text (trimmed)
    """
    attempt = 0
    while True:
        try:
            response = model.generate_content(prompt)
            # Some SDK versions return candidates without .text when blocked; guard it
            text = getattr(response, "text", "")
            return text.strip()
        except Exception as exc:  # Broad catch to be resilient across SDK versions
            attempt += 1
            is_last = attempt > max_retries
            message = str(exc)
            # Heuristic: backoff on 429 or quota/rate wording; otherwise rethrow unless not last try
            should_backoff = (
                "429" in message
                or "Rate" in message
                or "quota" in message.lower()
                or "exceeded" in message.lower()
                or "temporary" in message.lower()
                or "unavailable" in message.lower()
            )
            if not should_backoff and is_last:
                raise
            # Backoff
            delay = base_delay_seconds * (2 ** (attempt - 1))
            # Cap delay to something reasonable
            delay = min(delay, 30)
            # Add small jitter to reduce thundering herd
            delay += (0.25 * (1 + (attempt % 3)))
            time.sleep(delay)
            if is_last:
                # Out of retries
                raise

def gemini_extract_links(markdown: str) -> list:

    prompt = (
        "Below is markdown of a website listing recent articles.\n"
        "Please extract ONLY the URLs which are articles from the last 7 days, and avoid any other links, as well as promotions, or sponsored content. "
        "Return the list as plain text links (one per line, no bullets or formatting):\n\n"
        f"Today's date is {today}\n"
        f"{markdown}"
    )

    text = _generate_with_retry(prompt)

    # Extract URLs using regex
    urls = re.findall(r'https?://[^\s\)\]]+', text)

    # Filter out known non-article links
    filtered = [
        url for url in urls
        if not any(substr in url.lower() for substr in NON_ARTICLE_SUBSTRINGS)
    ]

    # Deduplicate
    return list(dict.fromkeys(filtered))

def gemini_summarize(article_markdowns: list) -> str:
    prompt = (
        f"You are given multiple full articles in markdown format, from two different websites:\n"
        "- Femtech World\n"
        "- Femtech Insider\n\n"
        "Please generate a weekly summary of articles in the following JSON format:\n"
        "{\n"
        "  \"date\": \"<Today's date>\",\n"
        "  \"sources\": [\n"
        "    {\n"
        "      \"site\": \"<Site Name>\",\n"
        "      \"articles\": [\n"
        "        {\n"
        "          \"title\": \"<Article Title>\",\n"
        "          \"summary\": \"<Brief summary (2 sentences, 50 words max)>\",\n"
        "          \"publication_date\": \"<Publication date if available>\",\n"
        "          \"url\": \"<URL to full article>\"\n"
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Group articles into sections by source. Only include articles posted within the last 7 days. Do not include any introduction or commentary outside the JSON.\n"
        f"Today's date is {today}\n"
        "Here are the articles:\n\n"
        + "\n\n---\n\n".join(article_markdowns)
    )

    return _generate_with_retry(prompt)

def gemini_summarize_batched(article_markdowns: list, batch_size: int = 8) -> str:
    """Summarize in batches to reduce tokens-per-minute pressure.

    Returns a JSON string matching the expected schema. We merge batches by site.
    """
    if not article_markdowns:
        return json.dumps({
            "date": today,
            "sources": []
        })

    partial_summaries = []
    for start in range(0, len(article_markdowns), batch_size):
        batch = article_markdowns[start:start + batch_size]
        prompt = (
            f"You are given multiple full articles in markdown format, from these websites (Femtech World, Femtech Insider).\n\n"
            "Produce ONLY valid JSON following this schema, with no extra commentary or code fences.\n"
            "{\n"
            "  \"date\": \"<Today's date>\",\n"
            "  \"sources\": [\n"
            "    {\n"
            "      \"site\": \"<Site Name>\",\n"
            "      \"articles\": [\n"
            "        {\n"
            "          \"title\": \"<Article Title>\",\n"
            "          \"summary\": \"<2 sentences, 50 words max>\",\n"
            "          \"publication_date\": \"<Publication date if available>\",\n"
            "          \"url\": \"<URL to full article>\"\n"
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "Only include articles from the last 7 days. Today's date is " + today + "\n\n"
            "Here are the articles in this batch:\n\n"
            + "\n\n---\n\n".join(batch)
        )
        text = _generate_with_retry(prompt)
        # Best-effort: strip accidental code-fence wrappers
        cleaned = re.sub(r"^```json\s*|\s*```$", "", text.strip(), flags=re.DOTALL)
        try:
            partial = json.loads(cleaned)
            partial_summaries.append(partial)
        except Exception:
            # If a single batch fails to parse, skip it rather than fail the entire run
            continue

    # Merge partials by site
    site_to_articles = {}
    for partial in partial_summaries:
        for src in partial.get("sources", []):
            site = src.get("site") or "Unknown"
            articles = src.get("articles", [])
            if site not in site_to_articles:
                site_to_articles[site] = []
            site_to_articles[site].extend(articles)

    merged_sources = [
        {"site": site, "articles": articles}
        for site, articles in site_to_articles.items()
    ]

    final_payload = {
        "date": today,
        "sources": merged_sources,
    }
    return json.dumps(final_payload, indent=2)

def gemini_extract_companies(summary_md: str) -> str:
    prompt = (
        "You are a research analyst reading the following weekly industry summary.\n\n"
        "Please extract a list of all companies mentioned in the summary.\n"
        "- Include company names only (no extra commentary).\n"
        "- Return a comma-separated (', ') plain text list.\n"
        "- Avoid duplicate names.\n\n"
        f"Here is the summary:\n\n{summary_md}"
    )

    return _generate_with_retry(prompt)