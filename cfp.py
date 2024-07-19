import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import sqlite3

# URL of the conference listing
base_url = "http://www.wikicfp.com"
search_url = "/cfp/call?conference=computer%20science"

# Function to parse the conference data from a single page
def parse_conferences(soup):
    main_table = soup.find('table', {'cellpadding': '3'})
    rows = main_table.find_all('tr')[1:]  # Skipping the header row

    conferences = []
    i = 0
    while i < len(rows):

        main_row = rows[i]
        try:
            sub_row = rows[i + 1]
        except:
            pass
        
        conference_link_tag = main_row.find('a')
        try:
            conference_name = conference_link_tag.text.strip()
        except:
            i += 1
            continue
        print(conference_name)
        conference_link = base_url + conference_link_tag['href']
        additional_details = main_row.find_all('td')[1].text.strip()
        details = sub_row.find_all('td')
        when = details[0].text.strip()
        where = details[1].text.strip()
        deadline_text = details[2].text.strip()
        
        deadline_text = deadline_text.replace("(", "").replace(")", "").strip()

        try:
            deadline_date = datetime.strptime(deadline_text, '%b %d, %Y')
        except ValueError:
            # Skip the row if the date format is incorrect
            i += 2
            continue

        conferences.append([conference_name, conference_link, additional_details, when, where, deadline_text])
        i += 2

    return conferences, True

# Function to fetch and parse conference data from multiple pages
def fetch_all_conferences(base_url, search_url):
    current_page = 1
    all_conferences = []
    more_pages = True
    prev_conf = None

    while more_pages:
        url = f"{base_url}{search_url}&page={current_page}"
        print(url)
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        conferences, more_pages = parse_conferences(soup)
        if prev_conf == conferences:
            break
        prev_conf = conferences
        all_conferences.extend(conferences)
        current_page += 1

    return all_conferences

# Fetch all conferences and store them in a DataFrame
all_conferences = fetch_all_conferences(base_url, search_url)
df = pd.DataFrame(all_conferences, columns=['Conference Name', 'Link', 'Additional Details', 'When', 'Where', 'Deadline'])

# Connect to SQLite database
conn = sqlite3.connect('conferences.db')
c = conn.cursor()

# Create table with unique constraints if it doesn't exist
c.execute('''
    CREATE TABLE IF NOT EXISTS conferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conference_name TEXT,
        link TEXT,
        additional_details TEXT,
        when_date TEXT,
        where_location TEXT,
        deadline TEXT,
        deleted INTEGER DEFAULT 0,
        UNIQUE(conference_name, deadline)
    )
''')

# Insert data into the table, ignoring duplicates and skipping deleted conferences
for _, row in df.iterrows():
    c.execute('''
        INSERT OR IGNORE INTO conferences (conference_name, link, additional_details, when_date, where_location, deadline)
        SELECT ?, ?, ?, ?, ?, ?
        WHERE NOT EXISTS (
            SELECT 1 FROM conferences WHERE conference_name = ? AND deadline = ? AND deleted = 1
        )
    ''', (row['Conference Name'], row['Link'], row['Additional Details'], row['When'], row['Where'], row['Deadline'],
          row['Conference Name'], row['Deadline']))

# Commit the changes and close the connection
conn.commit()
conn.close()

# Display the DataFrame
print(df)
