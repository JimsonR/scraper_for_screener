# crisil_scraper.py
"""
CRISIL Rating Rationale Scraper
Scrapes CRISIL HTML rationale pages while preserving formatting.
"""

import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import html2text


def scrape_crisil_rationale(url: str, output_folder=None):
    """
    Scrape a CRISIL rating rationale HTML page and save:

    - Markdown (.md) for readability
    - Clean HTML (.html) for viewing
    - Raw HTML backup (.raw.html)

    Args:
        url: CRISIL rationale URL
        output_folder: directory to save files (Path or str)
    """
    if output_folder is None:
        output_folder = Path.cwd()
    else:
        output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    # Derive an id-ish slug from the URL
    slug = Path(url.split("?", 1)[0]).stem or "crisil_rationale"

    print(f"[CRISIL] Fetching: {url}")

    headers = {
        # Pretend to be a normal Chrome browser
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

    # Important: use the encoded URL; requests will handle the spaces you got from Screener
    resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")

    # Try to get a title from <title> or <h1>
    page_title = None
    if soup.title and soup.title.string:
        page_title = soup.title.string.strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        page_title = h1.get_text(strip=True)
    if not page_title:
        page_title = slug.replace("_", " ")

    # Heuristic main content: center column / article / body
    main = (soup.find("div", class_=lambda c: c and "content" in c.lower())
            or soup.find("article")
            or soup.body
            or soup)

    # Drop scripts/styles/nav/footers
    for bad in main.find_all(["script", "style", "nav", "footer"]):
        bad.decompose()

    # ---------- Markdown ----------
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_emphasis = False
    h.body_width = 0

    md_lines = [f"# {page_title}", ""]
    md_body = h.handle(str(main))
    md_body = re.sub(r"\n{3,}", "\n\n", md_body).strip()
    md_lines.append(md_body)

    md_path = output_folder / f"{slug}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[CRISIL] ✓ Saved Markdown: {md_path.name}")

    # ---------- Clean HTML ----------
    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{page_title}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      max-width: 900px;
      margin: 0 auto;
      padding: 20px;
      line-height: 1.6;
      background: #ffffff;
      color: #333;
    }}
    h1, h2, h3, h4 {{
      color: #1f3b4d;
      margin-top: 1.5em;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 1em 0;
      font-size: 0.9em;
    }}
    th, td {{
      border: 1px solid #ddd;
      padding: 6px 8px;
      text-align: left;
    }}
    th {{
      background: #003366;
      color: #fff;
    }}
    tr:nth-child(even) {{
      background: #f7f7f7;
    }}
    a {{ color: #0066cc; }}
  </style>
</head>
<body>
  <h1>{page_title}</h1>
  <div class="content">
    {str(main)}
  </div>
</body>
</html>
"""
    html_path = output_folder / f"{slug}.html"
    html_path.write_text(html_body, encoding="utf-8")
    print(f"[CRISIL] ✓ Saved HTML: {html_path.name}")

    # ---------- Raw HTML backup ----------
    raw_path = output_folder / f"{slug}_raw.html"
    raw_path.write_text(resp.text, encoding="utf-8")
    print(f"[CRISIL] ✓ Saved Raw HTML: {raw_path.name}")

    return {
        "title": page_title,
        "markdown_file": md_path,
        "html_file": html_path,
        "raw_file": raw_path,
    }


if __name__ == "__main__":
    test_url = "https://www.crisil.com/mnt/winshare/Ratings/RatingList/RatingDocs/AxisBankLimited_July%2014_%202025_RR_370711.html"
    res = scrape_crisil_rationale(test_url)
    print("\nDone:", res)