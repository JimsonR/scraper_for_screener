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
        print("   SCREENER_USERNAME=your_email")
        print("   SCREENER_PASSWORD=your_password\n")
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
    """Download a file from URL to save_path."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, timeout=30, stream=True, headers=headers)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        if save_path.stat().st_size < 1000:
            with open(save_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().lower()
                if any(word in content for word in ['error', 'not found', '404', 'access denied']):
                    save_path.unlink()
                    return False
        
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
    """Click all plus symbols and expand all accordion sections."""
    print("Expanding all accordion sections...")
    
    time.sleep(2)
    
    # Strategy 1: Click all elements with plus symbol or expand indicators
    print("  Looking for expand buttons...")
    
    # Common selectors for expand buttons
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
        "[data-toggle='collapse']"
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

def extract_documents_links(soup, base_url):
    """
    Extract links from the Documents section (Announcements, Annual reports,
    Concalls, etc.). Tries to be robust to layout differences.
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

    # 2. Find the nearest container that holds the four columns under Documents
    # Usually the parent or grandparent div
    container = docs_heading
    for _ in range(4):  # climb a few levels up to find a big container
        container = container.parent
        if not container or container.name == 'body':
            break
        # Heuristic: container has a lot of links
        if len(container.find_all('a', href=True)) > 10:
            break

    if not container:
        print("  [Docs] Container for Documents not found")
        return docs

    # 3. Collect potential column blocks: descendants that contain an h3/h4
    columns = []
    for div in container.find_all('div', recursive=True):
        heading_tag = div.find(['h3', 'h4'])
        if heading_tag:
            title = heading_tag.get_text(strip=True).lower()
            if any(k in title for k in ['announcement', 'annual', 'concall', 'credit']):
                columns.append((title, div))

    if not columns:
        print("  [Docs] No document columns found under Documents")
        return docs

    print(f"  [Docs] Found {len(columns)} document columns: {[t for t,_ in columns]}")

    for col_title, col in columns:
        if 'announce' in col_title:
            category = 'announcements'
        elif 'annual' in col_title:
            category = 'annual'
        elif 'concall' in col_title:
            category = 'concalls'
        elif 'credit' in col_title:
            category = 'credit_ratings'
        else:
            category = 'other'

        # 4. Get all <a> tags inside this column
        for a in col.find_all('a', href=True):
            text = a.get_text(strip=True)
            href = a['href']
            full_url = urljoin(base_url, href)
            docs.append(
                {
                    'category': category,
                    'text': text,
                    'href': href,
                    'url': full_url,
                }
            )

    print(f"  [Docs] Total links collected from Documents: {len(docs)}")
    return docs

def scrape_screener_company(symbol):
    """Scrape company data from Screener.in"""
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    
    company_folder = Path(symbol)
    company_folder.mkdir(exist_ok=True)
    
    folders = {
        'tables': company_folder / 'financial_tables',
        'annual': company_folder / 'annual_reports',
        'concalls': company_folder / 'concalls',
        'announcements': company_folder / 'announcements',
        'credit_ratings': company_folder / 'credit_ratings',
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
        
        # Scroll to load lazy content
        print("Scrolling to load content...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        # Expand all accordions
        expand_all_accordions(driver)

        # Slow scroll through page to trigger lazy-loaded links (announcements, AR, concalls)
        print("Slow scrolling through page to load all document links...")
        scroll_height = driver.execute_script("return document.body.scrollHeight")
        current = 0
        step = scroll_height // 8 if scroll_height > 0 else 800

        while current < scroll_height:
            driver.execute_script(f"window.scrollTo(0, {current});")
            time.sleep(0.8)
            current += step

        # One final scroll to bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

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
            'other': 0,
        }

        # Use the structured Documents section instead of all <a> tags
        doc_links = extract_documents_links(soup, url)
        print(f"  Found {len(doc_links)} links in Documents section")

        for item in doc_links:
            category = item['category']
            text = item['text'] or ''
            full_url = item['url']

            # Map category to folder
            folder_key = category
            if folder_key not in folders:
                folder_key = 'announcements'  # fallback

            # Decide extension (if missing, default to .pdf)
            parsed_ext = os.path.splitext(urlparse(full_url).path)[1]
            ext = parsed_ext if parsed_ext else '.pdf'

            # Build filename
            filename = clean_filename(text or f"{category}_{download_stats.get(folder_key, 0)}")

            # Try to append year or FY/Q info if present
            date_match = re.search(r'(20\d{2}|19\d{2}|FY\d{2}|Q\d)', text)
            if date_match and date_match.group() not in filename:
                filename = f"{filename}_{date_match.group()}"

            filename = filename + ext
            save_path = folders.get(folder_key, folders['announcements']) / filename

            if save_path.exists():
                continue

            print(f"  Downloading [{category}]: {filename[:80]} ...")
            if download_file(full_url, save_path):
                download_stats[category] = download_stats.get(category, 0) + 1

        print(f"\n{'='*70}")
        print("Documents downloaded:")
        print(f"  Annual Reports: {download_stats.get('annual', 0)}")
        print(f"  Concalls: {download_stats.get('concalls', 0)}")
        print(f"  Announcements: {download_stats.get('announcements', 0)}")
        print(f"  Credit Ratings: {download_stats.get('credit_ratings', 0)}")
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
            print(f"⚠️  Check PAYWALL_WARNING.txt for details\n")
        
        print(f"{'='*70}")
        print(f"SCRAPING COMPLETE")
        print(f"Output folder: {company_folder}/")
        print(f"{'='*70}\n")
        
        return company_folder, tables_saved, download_stats
        
    finally:
        print("Closing browser in 3 seconds...")
        time.sleep(3)
        driver.quit()


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