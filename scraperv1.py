import time
import os
import re
import requests
import pandas as pd
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys  # at top if not already imported
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def login_to_screener(driver):
    """Login to Screener.in using credentials from .env file"""
    print("\n" + "="*70)
    print("LOGGING IN TO SCREENER.IN")
    print("="*70 + "\n")
    
    username = os.getenv('SCRUSER')
    password = os.getenv('SCRPASSWORD')
    
    if not username or not password:
        print("⚠️  WARNING: No credentials found in .env file")
        print("⚠️  Create a .env file with:")
        print("   SCRUSER=your_email")
        print("   SCRPASSWORD=your_password\n")
        return False
    
    try:
        # Go to login page
        driver.get("https://www.screener.in/login/")
        time.sleep(2)
        
        # Wait for and fill username
        username_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "id_username"))
        )
        username_field.clear()
        username_field.send_keys(username)
        
        # Fill password
        password_field = driver.find_element(By.ID, "id_password")
        password_field.clear()
        password_field.send_keys(password)
        
        # Click login button
        login_button = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
        login_button.click()
        
        # Wait for login to complete
        time.sleep(3)
        
        # Check if login was successful
        if "login" not in driver.current_url.lower():
            print("✓ Login successful!\n")
            return True
        else:
            print("✗ Login failed - still on login page\n")
            return False
            
    except Exception as e:
        print(f"✗ Login error: {e}\n")
        return False

def clean_filename(text):
    """Clean text to make it suitable for filenames."""
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    text = re.sub(r'\s+', '_', text.strip())
    text = text.replace('/', '_').replace('\\', '_')
    return text[:150]

def download_file(url, save_path):
    """Download a file from URL to save_path.

    - If the response is a real PDF (content-type/application), keep the extension as .pdf.
    - If the response is HTML or other text, save as .html rather than .pdf/.aspx.
    """
    try:
        # Special handling for India Ratings press releases to preserve formatting
        if 'indiaratings.co.in' in url and 'pressrelease' in url.lower():
            print(f"    [IndiaRatings] Detected press release URL: {url}")
            try:
                from india_ratings_scraper import scrape_india_ratings_press_release

                # Use the target folder (parent of save_path) for outputs
                output_folder = save_path.parent
                print(f"    [IndiaRatings] Output folder: {output_folder}")
                result = scrape_india_ratings_press_release(url, output_folder)

                print(f"    ✓ India Ratings press release scraped with formatting: {result['markdown_file'].name}")
                return True
            except Exception as e:
                print(f"    ! India Ratings scraper failed: {type(e).__name__}: {e}")
                # fall through to normal download
                # Special handling for CRISIL HTML rationales
        if 'crisil.com' in url and url.lower().endswith('.html'):
            try:
                from crisil_scraper import scrape_crisil_rationale
                output_folder = save_path.parent
                result = scrape_crisil_rationale(url, output_folder)
                print(f"    ✓ CRISIL rationale scraped with formatting: {result['markdown_file'].name}")
                return True
            except Exception as e:
                print(f"    ! CRISIL scraper failed ({e}); falling back to normal download...")


        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        # First try a HEAD request to inspect content-type quickly
        try:
            head_resp = requests.head(url, timeout=10, allow_redirects=True, headers=headers)
            content_type = head_resp.headers.get('Content-Type', '').lower()
            is_pdf = 'application/pdf' in content_type
        except Exception:
            content_type = ''

        # Adjust extension based on real content type
        if save_path.suffix.lower() not in ['.pdf', '.html', '.htm']:
            # If it's really a PDF by content-type, force .pdf
            if is_pdf:
                save_path = save_path.with_suffix('.pdf')
            else:
                # fall back: .html for text/html, keep .zip, etc.
                if 'text/html' in content_type or save_path.suffix.lower() in ['.aspx', '.php', '']:
                    save_path = save_path.with_suffix('.html')
                # else leave other binary types alone
        elif save_path.suffix.lower() in ['.aspx', '.php']:
            # Never keep .aspx/.php; map to .pdf or .html
            new_suffix = '.pdf' if is_pdf else '.html'
            save_path = save_path.with_suffix(new_suffix)

        response = requests.get(url, timeout=30, stream=True, headers=headers)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # If it's not a PDF and is very small, or looks like an error page, drop it
        if save_path.stat().st_size < 500:
            try:
                with open(save_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()
                    if any(word in content for word in ['error', 'not found', '404', 'access denied']):
                        save_path.unlink()
                        return False
            except Exception:
                # If we can't read as text, just keep it
                pass
        
        return True
    except Exception as e:
        print(f"    Error: {e}")
        return False

def check_paywall(soup):
    """Heuristic paywall check – now only logs *severe* blocks, never stops scraping."""
    page_text = soup.get_text().lower()

    # Remove 'upgrade to premium' and 'get a free account' from hard paywall triggers
    paywall_phrases = [
        'login to view',
        'sign in to access',
        'subscribe to view',
        'premium members only',
        'access denied',
        'this page is only available to'
    ]

    for phrase in paywall_phrases:
        if phrase in page_text:
            # Only return True for really blocked pages
            return True, f"Paywall: '{phrase}'"

    # Drop the "insufficient tables" heuristic – it was generating false positives
    return False, None

def expand_all_accordions(driver):
    """Click all plus symbols and expand all accordion sections - ENHANCED VERSION."""
    print("Expanding all accordion sections...")
    
    time.sleep(2)
    
    # Strategy 1: Click all elements with plus symbol or expand indicators
    print("  Looking for expand buttons...")
    
    # Enhanced selectors for expand buttons
    expand_selectors = [
        "button.button-plain",
        "span.icon-plus",
        "i.icon-plus", 
        "[class*='plus']",
        "[class*='expand']",
        "button[title*='expand']",
        "button[title*='Expand']",
        "a[onclick*='expand']",
        ".toggle",
        "[data-toggle='collapse']",
        "button:has(.icon-plus)",  # Buttons containing plus icons
        "button[aria-expanded='false']",  # ARIA expanded buttons
    ]
    
    total_clicked = 0
    
    for selector in expand_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            
            for elem in elements:
                try:
                    if elem.is_displayed() and elem.is_enabled():
                        # Scroll into view
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                        time.sleep(0.2)
                        
                        # Try to click
                        try:
                            elem.click()
                        except:
                            driver.execute_script("arguments[0].click();", elem)
                        
                        total_clicked += 1
                        time.sleep(0.3)
                except:
                    pass
        except Exception as e:
            pass
    
    print(f"  Clicked {total_clicked} expand buttons")
    
    # Strategy 2: Execute JavaScript to expand all hidden rows
    print("  Executing JavaScript to show hidden content...")
    
    js_expand = """
    // Find all table rows that might be hidden
    var rows = document.querySelectorAll('tr');
    var expanded = 0;
    
    rows.forEach(function(row) {
        // Check if row has onclick or is clickable
        if (row.onclick || row.getAttribute('onclick')) {
            try {
                row.click();
                expanded++;
            } catch(e) {}
        }
        
        // Show if hidden
        if (row.style.display === 'none' || row.style.display === '') {
            row.style.display = 'table-row';
            row.style.visibility = 'visible';
        }
        
        // Remove collapsed class
        row.classList.remove('collapsed');
        row.classList.remove('hidden');
    });
    
    // Show all elements with 'sub' class (Screener.in pattern)
    document.querySelectorAll('.sub').forEach(function(el) {
        el.style.display = 'table-row';
        el.style.visibility = 'visible';
    });
    
    // Expand all collapse elements
    document.querySelectorAll('.collapse').forEach(function(el) {
        el.classList.add('show');
        el.style.display = 'block';
    });
    
    return expanded;
    """
    
    try:
        expanded_count = driver.execute_script(js_expand)
        print(f"  JavaScript expanded {expanded_count} rows")
    except Exception as e:
        print(f"  JavaScript error: {e}")
    
    time.sleep(2)
    
    # Strategy 3: Find and click parent rows in tables
    print("  Clicking parent rows in tables...")
    
    parent_clicked = 0
    try:
        tables = driver.find_elements(By.TAG_NAME, "table")
        for table in tables:
            rows = table.find_elements(By.TAG_NAME, "tr")
            for row in rows:
                try:
                    # Check if row has children or is expandable
                    class_name = row.get_attribute('class') or ''
                    onclick = row.get_attribute('onclick') or ''
                    
                    if 'parent' in class_name or onclick or row.get_attribute('data-key'):
                        driver.execute_script("arguments[0].click();", row)
                        parent_clicked += 1
                        time.sleep(0.1)
                except:
                    pass
    except Exception as e:
        print(f"  Error clicking parent rows: {e}")
    
    print(f"  Clicked {parent_clicked} parent rows")
    
    # Final wait
    time.sleep(2)
    
    # Count visible rows
    try:
        total_rows = len(driver.find_elements(By.CSS_SELECTOR, "tr"))
        print(f"\n  Total table rows found: {total_rows}")
    except:
        pass
    
    print("  ✓ Expansion complete\n")

def extract_section_heading(element):
    """Extract the section heading before a table."""
    for _ in range(10):
        prev = element.find_previous(['h2', 'h3', 'h4', 'h5'])
        if prev:
            text = prev.get_text(strip=True)
            if text and len(text) < 50:
                return text
        element = element.parent
        if not element:
            break
    return None

def click_show_more_buttons(driver):
    """Click all 'show more' buttons to reveal hidden content."""
    print("  Clicking 'show more' buttons...")
    
    clicks = 0
    max_attempts = 5
    
    for attempt in range(max_attempts):
        try:
            # Find all buttons/links with "show more" text
            show_more_buttons = driver.find_elements(By.XPATH, 
                "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more') or "
                "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show all')]"
            )
            
            if not show_more_buttons:
                break
                
            for button in show_more_buttons:
                try:
                    if button.is_displayed() and button.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                        time.sleep(0.5)
                        button.click()
                        clicks += 1
                        time.sleep(1)
                except:
                    pass
        except:
            break
    
    print(f"  Clicked {clicks} 'show more' buttons")
    return clicks

def extract_concalls_comprehensive(driver, soup, base_url):
    """
    Extract concalls using BOTH Selenium (for current DOM) and BeautifulSoup.
    Handles buttons, links, and dynamic content.
    """
    concalls = []
    
    print("  [Concalls] Extracting using comprehensive method...")
    
    # 1. Find the Concalls container
    concall_container = None
    for div in soup.find_all("div", class_=lambda c: c and "documents" in c and "concalls" in c):
        h3 = div.find("h3")
        if h3 and "concall" in h3.get_text(strip=True).lower():
            concall_container = div
            break

    if not concall_container:
        print("  [Concalls] Concalls container not found via BeautifulSoup")
        print("  [Concalls] Total concalls extracted: 0")
        return concalls

    ul = concall_container.find("ul", class_="list-links")
    if not ul:
        print("  [Concalls] No list-links <ul> found under Concalls")
        print("  [Concalls] Total concalls extracted: 0")
        return concalls

    for li in ul.find_all("li"):
        quarter_div = li.find("div")
        quarter_text = quarter_div.get_text(strip=True) if quarter_div else None

        # All concall-link elements inside this li
        for el in li.find_all(class_="concall-link"):
            tag_name = el.name.lower()
            link_text = el.get_text(strip=True)
            href = el.get("href")

            # We only download actual URLs; some entries like "PPT" might be plain <div>
            if not href or not link_text:
                continue

            doc_name = f"{quarter_text}_{link_text}" if quarter_text else link_text

            concalls.append({
                "category": "concalls",
                "text": doc_name,
                "url": urljoin(base_url, href),
                "quarter": quarter_text,
                "type": link_text.lower()
            })

    print(f"  [Concalls] Total concalls extracted: {len(concalls)}")
    return concalls

def extract_documents_links(soup, base_url):
    """
    Extract links from the Documents section (Announcements, Annual reports, Credit ratings).
    NOTE: Concalls are now handled separately by extract_concalls_comprehensive()
    """
    docs = []

    # 1. Find the "Documents" heading
    docs_heading = None
    for tag in soup.find_all(['h2', 'h3', 'h4']):
        if 'documents' in tag.get_text(strip=True).lower():
            docs_heading = tag
            break

    if not docs_heading:
        print("  [Docs] Documents heading not found")
        return docs

    # 2. Find the nearest *robust* container that holds the document sections
    #    We walk up several ancestors and pick the one with the most links.
    best_container = None
    best_link_count = 0
    container = docs_heading
    for _ in range(10):
        container = container.parent
        if not container or container.name == 'body':
            break

        links_in_container = container.find_all('a', href=True)
        link_count = len(links_in_container)
        if link_count > best_link_count:
            best_link_count = link_count
            best_container = container

    container = best_container
    if not container:
        print("  [Docs] Container for Documents not found")
        return docs

    # 3. Collect all document sections (EXCLUDING concalls - handled separately)
    sections = []

    # Find all h3/h4 headings within the Documents container
    for heading_tag in container.find_all(['h3', 'h4']):
        title = heading_tag.get_text(strip=True).lower()

        # Map heading to category (SKIP concalls)
        if 'concall' in title:
            continue  # Skip concalls - handled by extract_concalls_comprehensive
        elif 'announce' in title:
            category = 'announcements'
        elif 'annual' in title:
            category = 'annual'
        elif 'credit' in title:
            category = 'credit_ratings'
        else:
            category = 'other'

        # Collect all siblings until the next h3/h4
        section_nodes = []
        sibling = heading_tag.next_sibling
        while sibling:
            if getattr(sibling, 'name', None) in ['h3', 'h4']:
                break
            section_nodes.append(sibling)
            sibling = sibling.next_sibling

        # Wrap the collected nodes in a temporary container for uniform searching
        if section_nodes:
            wrapper = soup.new_tag('div')
            for node in section_nodes:
                wrapper.append(node)
            sections.append((category, wrapper))

    if not sections:
        print("  [Docs] No document sections found under Documents")
        return docs

    print(f"  [Docs] Found {len(sections)} document sections (excluding concalls)")

    # 4. Extract all links from each section
    for category, section in sections:
        for a in section.find_all('a', href=True):
            text = a.get_text(strip=True)
            href = a['href']
            
            # Skip if it's just navigation or empty
            if not text or text.lower() in ['all', 'show more', 'show all', 'add missing']:
                continue
                
            full_url = urljoin(base_url, href)
            
            docs.append({
                'category': category,
                'text': text,
                'href': href,
                'url': full_url,
            })

    print(f"  [Docs] Total links collected (excluding concalls): {len(docs)}")
    return docs


def extract_text_content(soup, company_folder: Path):
    """Extract important textual content from Screener page (About, Pros/Cons, etc.)."""
    sections = []

    # About section (paragraphs following an 'About' label)
    about_texts = []
    for label in soup.find_all(string=lambda t: isinstance(t, str) and 'about' in t.strip().lower()):
        parent = label.parent
        # Walk a few siblings after the label to capture paragraphs
        sib = parent.find_next_sibling()
        limit = 0
        while sib and limit < 10:
            limit += 1
            if sib.name == 'p':
                txt = sib.get_text(" ", strip=True)
                if txt and len(txt) > 40:
                    about_texts.append(txt)
            sib = sib.find_next_sibling() if hasattr(sib, 'find_next_sibling') else None
        if about_texts:
            break

    if about_texts:
        sections.append(("About", "\n\n".join(about_texts)))

    # Pros and Cons lists
    def collect_list_after_heading(keyword):
        items = []
        for p in soup.find_all('p'):
            if keyword in p.get_text(strip=True).lower():
                ul = p.find_next_sibling('ul')
                if ul:
                    for li in ul.find_all('li'):
                        txt = li.get_text(" ", strip=True)
                        if txt:
                            items.append(txt)
                break
        return items

    pros = collect_list_after_heading('pros')
    if pros:
        sections.append(("Pros", "\n".join(f"- {p}" for p in pros)))

    cons = collect_list_after_heading('cons')
    if cons:
        sections.append(("Cons", "\n".join(f"- {c}" for c in cons)))

    if not sections:
        return

    md_lines = ["# Textual content from Screener.in", ""]
    for title, content in sections:
        md_lines.append(f"## {title}")
        md_lines.append("")
        md_lines.append(content)
        md_lines.append("")

    text_file = company_folder / "text_content.md"
    text_file.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"✓ Saved text content: {text_file.name}")


def extract_key_metrics(soup, company_folder: Path):
    """Extract key metrics (Market Cap, P/E, ROE, etc.) into a CSV file."""
    metrics = []

    # Heuristic: find a list that contains common metric labels
    candidate_uls = soup.find_all('ul')
    for ul in candidate_uls:
        lis = ul.find_all('li')
        if not lis:
            continue
        labels = [li.get_text(" ", strip=True).lower() for li in lis]
        if any('market cap' in lbl for lbl in labels) and any('current price' in lbl for lbl in labels):
            # This looks like the key metrics block
            for li in lis:
                parts = [span.get_text(" ", strip=True) for span in li.find_all('span') if span.get_text(strip=True)]
                if len(parts) >= 2:
                    name, value = parts[0], parts[1]
                else:
                    # Fallback: split by double space
                    txt = li.get_text(" ", strip=True)
                    if ':' in txt:
                        name, value = [x.strip() for x in txt.split(':', 1)]
                    else:
                        continue
                if name and value:
                    metrics.append({'metric': name, 'value': value})
            break

    if not metrics:
        return

    df = pd.DataFrame(metrics).drop_duplicates()
    out = company_folder / "key_metrics.csv"
    df.to_csv(out, index=False)
    print(f"✓ Saved key metrics: {out.name}")

def extract_quarterly_result_pdfs(soup, base_url):
    """Extract quarterly result PDF links from the 'Raw PDF' row in quarterly results table."""
    pdfs = []
    
    # Find the quarterly results table
    for table in soup.find_all('table'):
        # Check if this is the quarterly results table by looking for "Raw PDF" row
        raw_pdf_rows = table.find_all('tr')
        for row in raw_pdf_rows:
            cells = row.find_all(['td', 'th'])
            if cells and 'raw pdf' in cells[0].get_text(strip=True).lower():
                # This is the Raw PDF row
                for cell in cells[1:]:  # Skip first cell which contains "Raw PDF" text
                    link = cell.find('a', href=True)
                    if link:
                        href = link['href']
                        full_url = urljoin(base_url, href)
                        
                        # Try to extract quarter info from the URL or surrounding context
                        quarter_info = "Quarterly_Result"
                        
                        # Look for date info in previous header row
                        table_headers = table.find_all('tr')[0].find_all(['th', 'td'])
                        cell_index = cells.index(cell)
                        if cell_index < len(table_headers):
                            quarter_info = table_headers[cell_index].get_text(strip=True)
                        
                        pdfs.append({
                            'category': 'quarterly_results',
                            'text': f'Quarterly Result PDF - {quarter_info}',
                            'url': full_url,
                            'quarter': quarter_info,
                            # Flag these so we can force .pdf later regardless of content-type
                            'force_pdf': True
                        })
    
    print(f"  [PDFs] Found {len(pdfs)} quarterly result PDFs")
    return pdfs

def scrape_screener_company(symbol):
    """Scrape company data from Screener.in - ENHANCED VERSION"""
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    
    company_folder = Path(symbol)
    company_folder.mkdir(exist_ok=True)
    
    folders = {
        'tables': company_folder / 'financial_tables',
        'annual': company_folder / 'annual_reports',
        'concalls': company_folder / 'concalls',
        'announcements': company_folder / 'announcements',
        'credit_ratings': company_folder / 'credit_ratings',
        'quarterly_results': company_folder / 'quarterly_result_pdfs',
        'other': company_folder / 'other_documents',
    }
    for folder in folders.values():
        folder.mkdir(exist_ok=True)
    
    chrome_options = Options()
    # chrome_options.add_argument("--headless")  # Commented out for debugging
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # LOGIN FIRST
        login_success = login_to_screener(driver)
        
        if not login_success:
            print("⚠️  Continuing without login - data may be limited\n")
        
        print(f"\n{'='*70}")
        print(f"SCRAPING: {symbol}")
        print(f"{'='*70}\n")
        print(f"URL: {url}\n")
        
        driver.get(url)
        
        # Wait for page load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )
        print("✓ Page loaded\n")
        
        # Scroll to load lazy content - ENHANCED
        print("Scrolling to load content...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        # Expand all accordions
        expand_all_accordions(driver)

        # Click all "show more" buttons to reveal hidden content
        click_show_more_buttons(driver)

        # Slow scroll through page to trigger lazy-loaded links - ENHANCED
        print("Slow scrolling through page to load all document links...")
        scroll_height = driver.execute_script("return document.body.scrollHeight")
        current = 0
        step = scroll_height // 10 if scroll_height > 0 else 500  # More granular scrolling

        while current < scroll_height:
            driver.execute_script(f"window.scrollTo(0, {current});")
            time.sleep(1)  # Increased wait time for lazy loading
            current += step

        # One final scroll to bottom and wait longer
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        
        # Scroll back to Documents section and wait
        print("Scrolling to Documents section...")
        driver.execute_script("""
            var docsSection = Array.from(document.querySelectorAll('h2')).find(h => h.textContent.includes('Documents'));
            if (docsSection) {
                docsSection.scrollIntoView({behavior: 'smooth', block: 'center'});
            }
        """)
        time.sleep(2)

        # Extract concall notes via Selenium before freezing the HTML
        extract_concall_notes(driver, company_folder)

        # Now capture final page source
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Check paywall – log only, never change behavior
        paywall_detected = False
        is_paywalled, msg = check_paywall(soup)
        if is_paywalled:
            print(f"\n⚠️  PAYWALL TEXT SEEN: {msg}")
            print("⚠️  Ignoring and scraping everything visible on the page...\n")
            paywall_detected = True
        
        # Extract company name
        company_name = soup.find('h1')
        company_name = company_name.text.strip() if company_name else symbol
        print(f"Company: {company_name}\n")
        
        # Save HTML
        with open(company_folder / 'full_page.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print(f"✓ Saved: full_page.html\n")

        # Extract textual content and key metrics
        extract_text_content(soup, company_folder)
        extract_key_metrics(soup, company_folder)
        
        # Extract tables
        print("Extracting financial tables...")
        print("-" * 70)
        
        all_tables = soup.find_all('table')
        tables_saved = {}
        
        for idx, table in enumerate(all_tables):
            try:
                section = extract_section_heading(table)
                df = pd.read_html(str(table))[0]
                
                if df.shape[0] < 2 or df.shape[1] < 2:
                    continue
                
                # Determine table name
                if section:
                    base_name = clean_filename(section)
                else:
                    first_col_text = ' '.join(df.iloc[:, 0].astype(str).tolist()[:5]).lower()
                    
                    if any(k in first_col_text for k in ['sales', 'revenue', 'operating profit', 'expenses']):
                        base_name = "Profit_Loss"
                    elif any(k in first_col_text for k in ['equity', 'reserves', 'assets', 'liabilities', 'borrowings']):
                        base_name = "Balance_Sheet"
                    elif any(k in first_col_text for k in ['cash from operating', 'cash from investing', 'cash from financing']):
                        base_name = "Cash_Flows"
                    elif any(k in first_col_text for k in ['debtor days', 'roce', 'roe', 'working capital']):
                        base_name = "Ratios"
                    elif 'sep' in first_col_text or 'dec' in first_col_text or 'jun' in first_col_text:
                        base_name = "Quarterly_Results"
                    elif 'promoter' in first_col_text or 'fii' in first_col_text or 'dii' in first_col_text:
                        base_name = "Shareholding_Pattern"
                    else:
                        base_name = f"Table_{idx}"
                
                # Handle duplicates
                name = base_name
                counter = 1
                while name in tables_saved:
                    name = f"{base_name}_{counter}"
                    counter += 1
                
                # Save
                filepath = folders['tables'] / f"{name}.csv"
                df.to_csv(filepath, index=False)
                tables_saved[name] = df.shape
                
                print(f"  ✓ {name:40} ({df.shape[0]:3} rows × {df.shape[1]:2} cols)")
                
            except Exception as e:
                print(f"  ✗ Table {idx}: {e}")
        
        print(f"\n{'='*70}")
        print(f"Tables extracted: {len(tables_saved)}")
        print(f"{'='*70}\n")
        
        # Download documents
        print("Downloading documents...")
        print("-" * 70)

        download_stats = {
            'annual': 0,
            'concalls': 0,
            'announcements': 0,
            'credit_ratings': 0,
            'quarterly_results': 0,
            'other': 0,
        }

        # Extract document links from Documents section (excluding concalls)
        doc_links = extract_documents_links(soup, url)
        print(f"  Found {len(doc_links)} links in Documents section (excluding concalls)")
        
        # Extract concalls separately using comprehensive method
        concall_links = extract_concalls_comprehensive(driver, soup, url)
        print(f"  Found {len(concall_links)} concall links")
        
        # Extract quarterly result PDFs
        quarterly_pdfs = extract_quarterly_result_pdfs(soup, url)
        print(f"  Found {len(quarterly_pdfs)} quarterly result PDFs")
        
        # Combine all document links
        all_doc_links = doc_links + concall_links + quarterly_pdfs

        for item in all_doc_links:
            category = item['category']
            text = item['text'] or ''
            full_url = item['url']
            force_pdf = item.get('force_pdf', False)

            # Rewrite ICRA credit rating rationale HTML pages to direct PDF endpoint
            if category == 'credit_ratings' and 'icra.in/Rationale/ShowRationaleReport' in full_url:
                try:
                    parsed = urlparse(full_url)
                    query = parsed.query or ''
                    match = re.search(r"[?&]Id=(\d+)", '?' + query)
                    if match:
                        icra_id = match.group(1)
                        full_url = f"https://www.icra.in/Rating/GetRationalReportFilePdf?Id={icra_id}"
                        force_pdf = True
                except Exception:
                    pass

            # Map category to folder
            folder_key = category
            if folder_key not in folders:
                folder_key = 'other'

            # Decide extension more intelligently
            parsed_ext = os.path.splitext(urlparse(full_url).path)[1].lower()

            if force_pdf:
                # User explicitly wants quarterly result links treated as PDFs
                ext = '.pdf'
            else:
                if parsed_ext in ['.pdf']:
                    ext = '.pdf'
                elif parsed_ext in ['.htm', '.html']:
                    ext = '.html'
                elif parsed_ext in ['.aspx', '.php', '']:
                    # Guess based on URL containing .pdf, otherwise treat as HTML page
                    ext = '.pdf' if '.pdf' in full_url.lower() else '.html'
                else:
                    # Keep any other extension as-is (zip, etc.)
                    ext = parsed_ext

            # Build filename
            filename = clean_filename(text or f"{category}_{download_stats.get(folder_key, 0)}")

            # Try to append year or FY/Q info if present
            date_match = re.search(r'(20\d{2}|19\d{2}|FY\d{2}|Q\d)', text)
            if date_match and date_match.group() not in filename:
                filename = f"{filename}_{date_match.group()}"

            filename = filename + ext
            save_path = folders.get(folder_key, folders['other']) / filename

            if save_path.exists():
                continue

            print(f"  Downloading [{category}]: {filename[:80]} ...")
            print(f"    [Debug] URL: {full_url}")
            if download_file(full_url, save_path):
                download_stats[category] = download_stats.get(category, 0) + 1

        print(f"\n{'='*70}")
        print("Documents downloaded:")
        print(f"  Annual Reports: {download_stats.get('annual', 0)}")
        print(f"  Concalls: {download_stats.get('concalls', 0)}")
        print(f"  Announcements: {download_stats.get('announcements', 0)}")
        print(f"  Credit Ratings: {download_stats.get('credit_ratings', 0)}")
        print(f"  Quarterly Results PDFs: {download_stats.get('quarterly_results', 0)}")
        print(f"  Other: {download_stats.get('other', 0)}")
        print(f"{'='*70}\n")
        
        # Create summary
        summary = {
            'Company Name': company_name,
            'Symbol': symbol,
            'URL': url,
            'Scrape Date': time.strftime('%Y-%m-%d %H:%M:%S'),
            'Login': 'Yes' if login_success else 'No',
            'Paywall': 'Yes (Text seen)' if paywall_detected else 'No',
            'Tables': len(tables_saved),
            'Annual Reports': download_stats['annual'],
            'Concalls': download_stats['concalls'],
            'Announcements': download_stats['announcements'],
            'Credit Ratings': download_stats['credit_ratings'],
            'Quarterly Result PDFs': download_stats['quarterly_results'],
            'Other Docs': download_stats['other'],
        }
        
        summary_df = pd.DataFrame([summary])
        summary_df.to_csv(company_folder / 'summary.csv', index=False)
        
        table_info = pd.DataFrame([
            {'Table': name, 'Rows': shape[0], 'Columns': shape[1]}
            for name, shape in tables_saved.items()
        ])
        table_info.to_csv(folders['tables'] / '_table_index.csv', index=False)
        
        print(f"✓ Summary saved\n")
        
        if paywall_detected:
            print(f"⚠️  WARNING: Paywall may have limited data access")
            print(f"⚠️  Check the downloaded data for completeness\n")
        
        print(f"{'='*70}")
        print(f"SCRAPING COMPLETE")
        print(f"Output folder: {company_folder}/")
        print(f"{'='*70}\n")
        
        return company_folder, tables_saved, download_stats
        
    finally:
        print("Closing browser in 3 seconds...")
        time.sleep(3)
        driver.quit()


def extract_concall_notes(driver, company_folder: Path):
    """
    Use Selenium to click each 'Notes' button in the Concalls section,
    scrape the right-side modal text, and save as markdown files.
    """
    notes_folder = company_folder / "concall_notes"
    notes_folder.mkdir(exist_ok=True)

    wait = WebDriverWait(driver, 10)

    print("  [Concalls] Extracting Notes from modal/offcanvas...")

    # Helper to close any open right-side dialog, if present
    def close_any_open_dialog():
        try:
            open_dialogs = driver.find_elements(
                By.CSS_SELECTOR, "dialog.modal.modal-right[open]"
            )
            if not open_dialogs:
                return
            dlg = open_dialogs[0]
            try:
                close_btn = dlg.find_element(
                    By.XPATH,
                    ".//button[.//i[contains(@class,'icon-cancel') or contains(@class,'icon-cancel-thin')]]"
                )
                close_btn.click()
            except Exception:
                try:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                except Exception:
                    pass
            # Wait until dialog is gone
            try:
                wait.until(EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, "dialog.modal.modal-right[open]")
                ))
            except Exception:
                pass
        except Exception:
            pass

    # Make sure we start with no dialog blocking clicks
    close_any_open_dialog()

    # Locate all concall Notes buttons
    try:
        notes_buttons = driver.find_elements(
            By.XPATH,
            "//button[contains(@class,'concall-link') and normalize-space()='Notes']"
        )
    except Exception as e:
        print(f"  [Concalls] Error locating Notes buttons: {e}")
        return

    print(f"  [Concalls] Found {len(notes_buttons)} 'Notes' buttons (button.concall-link)")

    if not notes_buttons:
        return

    for idx in range(len(notes_buttons)):
        try:
            # Re-find buttons each time to avoid stale references
            notes_buttons = driver.find_elements(
                By.XPATH,
                "//button[contains(@class,'concall-link') and normalize-space()='Notes']"
            )
            if idx >= len(notes_buttons):
                break

            btn = notes_buttons[idx]

            # Build a title from data-title or row text
            title = None
            try:
                title = btn.get_attribute("data-title")
            except Exception:
                pass
            if not title:
                try:
                    row = btn.find_element(By.XPATH, "./ancestor::*[self::li or self::div][1]")
                    row_text = row.text.splitlines()[0].strip()
                    title = row_text or f"Concall_{idx+1}"
                except Exception:
                    title = f"Concall_{idx+1}"

            print(f"    [Concalls] Clicking Notes button #{idx+1}: {title}")

            # Ensure no old dialog is open before clicking
            close_any_open_dialog()

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.5)
            try:
                btn.click()
            except Exception as e:
                print(f"    [Concalls] Direct click failed: {e}; trying JS click")
                driver.execute_script("arguments[0].click();", btn)

            # Wait for a right-side dialog to appear
            try:
                dialog = wait.until(
                    EC.visibility_of_element_located(
                        (By.CSS_SELECTOR, "dialog.modal.modal-right[open]")
                    )
                )
            except Exception as e:
                print(f"    [Concalls] Modal did not appear after clicking Notes #{idx+1}: {e}")
                continue

            # Within the dialog, get the modal-body and article/sub text
            text = ""
            try:
                modal_body = dialog.find_element(By.CSS_SELECTOR, "div.modal-body")
            except Exception:
                modal_body = dialog

            try:
                article = modal_body.find_element(By.CSS_SELECTOR, "article.sub, article")
                text = article.text.strip()
            except Exception:
                text = (modal_body.text or "").strip()

            if not text:
                print(f"    [Concalls] Modal for #{idx+1} had no text, skipping save")
            else:
                safe_name = clean_filename(f"{title}_concall_notes")
                out_path = notes_folder / f"{safe_name}.md"
                out_path.write_text(text, encoding="utf-8")
                print(f"    ✓ Saved notes: {out_path.name}")

            # Close this dialog and wait for it to go away
            try:
                close_btn = dialog.find_element(
                    By.XPATH,
                    ".//button[.//i[contains(@class,'icon-cancel') or contains(@class,'icon-cancel-thin')]]"
                )
                close_btn.click()
            except Exception:
                try:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                except Exception:
                    pass

            try:
                wait.until(EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, "dialog.modal.modal-right[open]")
                ))
            except Exception:
                pass

            time.sleep(0.3)

        except Exception as e:
            print(f"    ✗ Error extracting notes #{idx+1}: {e}")
            close_any_open_dialog()

if __name__ == "__main__":
    symbol = input("Enter company symbol (e.g., TCS): ").strip().upper()
    
    if not symbol:
        symbol = "TCS"
    
    try:
        company_folder, tables, docs = scrape_screener_company(symbol)
        print(f"\n✅ SUCCESS! All data saved in: {company_folder}/")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()