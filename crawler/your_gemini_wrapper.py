import re
from google.generativeai import GenerativeModel
from urllib.parse import urlparse
import os
from dotenv import load_dotenv
from datetime import date

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

def gemini_extract_links(markdown: str) -> list:

    prompt = (
        "Below is markdown of a website listing recent articles.\n"
        "Please extract ONLY the URLs which are articles from the last 7 days, and avoid any other links, as well as promotions, or sponsored content. "
        "Return the list as plain text links (one per line, no bullets or formatting):\n\n"
        f"Today's date is {today}\n"
        f"{markdown}"
    )

    response = model.generate_content(prompt)
    text = response.text.strip()

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

    response = model.generate_content(prompt)
    return response.text.strip()

def gemini_extract_companies(summary_md: str) -> str:
    prompt = (
        "You are a research analyst reading the following weekly industry summary.\n\n"
        "Please extract a list of all companies mentioned in the summary.\n"
        "- Include company names only (no extra commentary).\n"
        "- Return a comma-separated (', ') plain text list.\n"
        "- Avoid duplicate names.\n\n"
        f"Here is the summary:\n\n{summary_md}"
    )

    response = model.generate_content(prompt)
    return response.text.strip()