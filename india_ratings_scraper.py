"""
India Ratings Press Release Scraper
Scrapes credit rating press releases while preserving formatting
"""

import time
import re
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import html2text


def scrape_india_ratings_press_release(url, output_folder=None):
    """
    Scrape India Ratings press release and save with formatting preserved.
    
    Args:
        url: URL of the press release (e.g., https://www.indiaratings.co.in/pressrelease/79399)
        output_folder: Path to save output (default: current directory)
    
    Returns:
        dict with paths to saved files
    """
    
    # Setup output folder
    if output_folder is None:
        output_folder = Path.cwd()
    else:
        output_folder = Path(output_folder)
    output_folder.mkdir(exist_ok=True)
    
    # Extract press release ID from URL
    press_id = url.split('/')[-1]
    
    # Setup Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        print(f"Fetching: {url}")
        driver.get(url)
        
        # Wait for main content to load
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "main")))
        time.sleep(2)
        
        # Get page source
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Extract main content area
        main_content = soup.find('main')
        if not main_content:
            print("Warning: Could not find main content area")
            main_content = soup
        
        # Find the actual press release content (excluding header/footer)
        content_div = main_content.find('div', class_=lambda c: c and 'content' in c.lower()) or main_content
        
        # Extract title
        title = soup.find('h1')
        title_text = title.get_text(strip=True) if title else f"Press Release {press_id}"
        
        # Extract metadata (date, category)
        metadata = {}
        meta_list = soup.find('ul', class_=lambda c: c and any(x in str(c).lower() for x in ['meta', 'info']))
        if meta_list:
            items = meta_list.find_all('li')
            for item in items:
                text = item.get_text(strip=True)
                if text and text != '|':
                    if any(month in text for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                                                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                        metadata['date'] = text
                    else:
                        metadata['category'] = text
        
        # METHOD 1: Save as Markdown (best for readability)
        markdown_content = convert_to_markdown(content_div, title_text, metadata)
        md_file = output_folder / f"india_ratings_{press_id}.md"
        md_file.write_text(markdown_content, encoding='utf-8')
        print(f"✓ Saved Markdown: {md_file.name}")
        
        # METHOD 2: Save as HTML (preserves exact formatting)
        html_content = create_clean_html(content_div, title_text, metadata)
        html_file = output_folder / f"india_ratings_{press_id}.html"
        html_file.write_text(html_content, encoding='utf-8')
        print(f"✓ Saved HTML: {html_file.name}")
        
        # METHOD 3: Save raw HTML (complete backup)
        raw_file = output_folder / f"india_ratings_{press_id}_raw.html"
        raw_file.write_text(driver.page_source, encoding='utf-8')
        print(f"✓ Saved Raw HTML: {raw_file.name}")
        
        return {
            'title': title_text,
            'metadata': metadata,
            'markdown_file': md_file,
            'html_file': html_file,
            'raw_file': raw_file
        }
        
    finally:
        driver.quit()


def convert_to_markdown(content_div, title, metadata):
    """Convert HTML content to well-formatted Markdown"""
    
    # Initialize markdown converter
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.ignore_emphasis = False
    h.body_width = 0  # No line wrapping
    h.single_line_break = False
    
    # Build markdown document
    lines = []
    lines.append(f"# {title}")
    lines.append("")
    
    # Add metadata
    if metadata:
        if 'date' in metadata:
            lines.append(f"**Date:** {metadata['date']}")
        if 'category' in metadata:
            lines.append(f"**Category:** {metadata['category']}")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # Convert main content
    # Remove unwanted sections
    for unwanted in content_div.find_all(['script', 'style', 'nav', 'footer']):
        unwanted.decompose()
    
    # Convert to markdown
    content_md = h.handle(str(content_div))
    
    # Clean up markdown
    content_md = re.sub(r'\n{3,}', '\n\n', content_md)  # Max 2 consecutive newlines
    content_md = content_md.strip()
    
    lines.append(content_md)
    
    return '\n'.join(lines)


def create_clean_html(content_div, title, metadata):
    """Create a clean, standalone HTML file with formatting preserved"""
    
    # Remove unwanted elements
    for unwanted in content_div.find_all(['script', 'style', 'nav', 'footer']):
        unwanted.decompose()
    
    # Build HTML document
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
            background: #fff;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}
        h2, h3, h4 {{
            color: #34495e;
            margin-top: 1.5em;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
            font-size: 0.9em;
        }}
        th {{
            background-color: #3498db;
            color: white;
            padding: 10px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            border: 1px solid #ddd;
            padding: 8px;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .metadata {{
            background: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .metadata p {{
            margin: 5px 0;
        }}
        ul, ol {{
            margin: 1em 0;
            padding-left: 2em;
        }}
        li {{
            margin: 0.5em 0;
        }}
        a {{
            color: #3498db;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        p {{
            margin: 1em 0;
            text-align: justify;
        }}
        .section {{
            margin: 2em 0;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
"""
    
    # Add metadata
    if metadata:
        html += '    <div class="metadata">\n'
        if 'date' in metadata:
            html += f'        <p><strong>Date:</strong> {metadata["date"]}</p>\n'
        if 'category' in metadata:
            html += f'        <p><strong>Category:</strong> {metadata["category"]}</p>\n'
        html += '    </div>\n'
    
    # Add main content
    html += f'    <div class="content">\n{str(content_div)}\n    </div>\n'
    
    html += """</body>
</html>"""
    
    return html


def scrape_india_ratings_from_screener_link(link_url, company_folder):
    """
    Integration function for use in your main scraper.
    Handles India Ratings links found in credit_ratings section.
    
    Args:
        link_url: The India Ratings URL
        company_folder: Path object for company folder
    
    Returns:
        Path to saved markdown file
    """
    credit_folder = company_folder / "credit_ratings"
    credit_folder.mkdir(exist_ok=True)
    
    result = scrape_india_ratings_press_release(link_url, credit_folder)
    return result['markdown_file']


if __name__ == "__main__":
    # Example usage
    url = "https://www.indiaratings.co.in/pressrelease/79399"
    result = scrape_india_ratings_press_release(url)
    
    print(f"\n{'='*70}")
    print(f"SCRAPING COMPLETE")
    print(f"{'='*70}")
    print(f"Title: {result['title']}")
    print(f"Metadata: {result['metadata']}")
    print(f"\nFiles saved:")
    print(f"  - {result['markdown_file']}")
    print(f"  - {result['html_file']}")
    print(f"  - {result['raw_file']}")
    print(f"{'='*70}\n")
