from flask import Flask, render_template, request
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

app = Flask(__name__)

def scrape_event_page(url, headers):
    print(f"Attempting to scrape: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status code for {url}: {response.status_code}")
        if response.status_code != 200:
            print(f"Skipping {url} due to status {response.status_code}")
            return [], []
        soup = BeautifulSoup(response.text, 'html.parser')
        
        male_results = []
        female_results = []
        pre_tags = soup.find_all('pre')
        if not pre_tags:
            print(f"No <pre> tags found in {url}")
            return [], []

        for pre in pre_tags:
            text = pre.get_text()
            print(f"Raw text from {url}: {text[:500]}...")  # Print first 500 chars for debugging
            lines = text.strip().split('\n')
            current_section = []
            for line in lines:
                if line.strip().startswith('Event'):
                    if current_section:
                        section_text = '\n'.join(current_section)
                        male_res, female_res = process_section(section_text)
                        male_results.extend(male_res)
                        female_results.extend(female_res)
                    current_section = [line]
                else:
                    current_section.append(line)
            if current_section:
                section_text = '\n'.join(current_section)
                male_res, female_res = process_section(section_text)
                male_results.extend(male_res)
                female_results.extend(female_res)

        print(f"Extracted {len(male_results)} male and {len(female_results)} female results from {url}")
        return male_results, female_results
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return [], []

def process_section(section_text):
    lines = section_text.strip().split('\n')
    if not lines or len(lines) < 3:
        return [], []

    male_results = []
    female_results = []
    header = next((line for line in lines if line.strip().startswith('Event')), '')
    if not header:
        return [], []

    is_relay = 'Relay' in header
    gender = 'Men' if 'Men' in header else 'Women' if 'Women' in header else 'Mixed'
    age_group = 'Unknown'

    if is_relay:
        age_match = re.search(r'(\d+ & Over|\d+ - Over)', header)
        if age_match:
            age_group = age_match.group(1)
    else:
        age_match = re.search(r'(Men|Women) (\d+-\d+|\d+ & Over)', header)
        if age_match:
            age_group = age_match.group(2) if age_match.group(2) else '20 & Over'

    print(f"Processing section with header: {header}, gender: {gender}, age_group: {age_group}, Relay: {is_relay}")

    result_lines = [line for line in lines if line.strip() and not line.startswith('=') and not line.startswith(('Name', 'Team')) and re.match(r'^\s*\d', line)]
    print(f"Found {len(result_lines)} potential result lines: {result_lines[:3]}")

    for line in result_lines:
        parts = [p for p in line.split() if p]
        if not parts or not parts[0].isdigit():
            continue

        place = parts[0]
        if is_relay:
            club = parts[1]
            if len(parts) > 2 and parts[2] == "'A'":
                club = f"{parts[1]} A"
            name = club
            result = {'age_group': age_group, 'place': place, 'name': name, 'club': club, 'gender': gender}
            if gender == 'Men':
                male_results.append(result)
            elif gender == 'Women':
                female_results.append(result)
        else:
            age_idx = next((i for i, part in enumerate(parts) if part.isdigit() and 18 <= int(part) <= 94), -1)
            if age_idx > 0:
                name = ' '.join(parts[1:age_idx])
                club = parts[age_idx + 1] if age_idx + 1 < len(parts) else 'N/A'
            else:
                name = ' '.join(parts[1:3]) if len(parts) > 2 else parts[1]
                club = parts[-2] if len(parts) > 2 else 'N/A'
            result = {'age_group': age_group, 'place': place, 'name': name, 'club': club, 'gender': gender}
            if gender == 'Men':
                male_results.append(result)
            elif gender == 'Women':
                female_results.append(result)

    return male_results, female_results

def get_frame_urls(main_url, headers):
    try:
        response = requests.get(main_url, headers=headers, timeout=10)
        print(f"Main page status: {response.status_code}")
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            frame_urls = []
            for frame in soup.find_all('frame'):
                src = frame.get('src')
                if src:
                    full_url = main_url.rstrip('/') + '/' + src.lstrip('/')
                    frame_urls.append(full_url)
            print(f"Found frame URLs: {frame_urls}")
            return frame_urls
        return []
    except Exception as e:
        print(f"Error fetching frame URLs: {e}")
        return []

@app.route('/', methods=['GET', 'POST'])
def index():
    male_standings = None
    female_standings = None
    total_standings = None
    error = ""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Referer': 'https://www.esf-eg.org/'
    }
    if request.method == 'POST':
        url = request.form['url']
        print(f"Received URL: {url}")
        try:
            if url.endswith('.htm') or url.endswith('.html'):
                error = "Please provide the main directory URL, not an event file (e.g., https://www.esf-eg.org/images/results/masters/2025/results/)."
                return render_template('index.html', male_standings=male_standings, female_standings=female_standings, total_standings=total_standings, error=error)

            base_url = url.rstrip('/') + '/'
            date = '250529'
            print(f"Using base URL: {base_url} and date: {date}")

            all_male_results = []
            all_female_results = []
            frame_urls = get_frame_urls(base_url, headers)
            if frame_urls:
                for frame_url in frame_urls:
                    if 'evtindex' in frame_url.lower():
                        response = requests.get(frame_url, headers=headers, timeout=10)
                        soup = BeautifulSoup(response.text, 'html.parser')
                        event_links = [base_url + link.get('href') for link in soup.find_all('a', href=True) if link.get('href').endswith('.htm')]
                        print(f"Found event links from evtindex: {event_links}")
                        for event_url in event_links:
                            male_res, female_res = scrape_event_page(event_url, headers)
                            all_male_results.extend(male_res)
                            all_female_results.extend(female_res)

            if all_male_results or all_female_results:
                # Process male standings
                if all_male_results:
                    raw_male_df = pd.DataFrame(all_male_results)
                    raw_male_df['medal'] = raw_male_df['place'].map({'1': 'Gold', '2': 'Silver', '3': 'Bronze'})
                    male_medal_table = raw_male_df.groupby(['age_group', 'club', 'medal']).size().unstack(fill_value=0)
                    male_medal_table['Total'] = male_medal_table.sum(axis=1)
                    male_standings = male_medal_table.reset_index().sort_values(by="Total", ascending=False)

                # Process female standings
                if all_female_results:
                    raw_female_df = pd.DataFrame(all_female_results)
                    raw_female_df['medal'] = raw_female_df['place'].map({'1': 'Gold', '2': 'Silver', '3': 'Bronze'})
                    female_medal_table = raw_female_df.groupby(['age_group', 'club', 'medal']).size().unstack(fill_value=0)
                    female_medal_table['Total'] = female_medal_table.sum(axis=1)
                    female_standings = female_medal_table.reset_index().sort_values(by="Total", ascending=False)

                # Total standings
                combined_df = pd.concat([raw_male_df, raw_female_df])
                if not combined_df.empty:
                    combined_df['medal'] = combined_df['place'].map({'1': 'Gold', '2': 'Silver', '3': 'Bronze'})
                    total_medal_table = combined_df.groupby(['age_group', 'club', 'medal']).size().unstack(fill_value=0)
                    total_medal_table['Total'] = total_medal_table.sum(axis=1)
                    total_standings = total_medal_table.reset_index().sort_values(by="Total", ascending=False)
            else:
                error = "No valid data extracted from event pages."
        except Exception as e:
            error = f"Error processing URL: {str(e)}"
    return render_template('index.html', male_standings=male_standings, female_standings=female_standings, total_standings=total_standings, error=error)

if __name__ == '__main__':
    app.run(debug=True)