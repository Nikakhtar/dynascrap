from flask import Flask, request, jsonify
import json
import os
import scrapy
import pandas as pd
import sqlite3
import asyncio
from scrapy.crawler import CrawlerRunner
from scrapy.utils.project import get_project_settings
from twisted.internet import reactor, defer
import nest_asyncio
from io import StringIO
import multiprocessing
from multiprocessing import Manager

from spiders.dynamic_news_spider import DynamicNewsSpider

app = Flask(__name__)
scrapy_process = None  # This will hold the process running Scrapy

# Fix async issues in Google Colab
nest_asyncio.apply()

# Function to create a clean filename
def sanitize_filename(url):
    return f"articles_{url.replace('https://', '').replace('http://', '').replace('/', '_').replace('.', '_')}.json"

# Function to run multiple spiders in the same process
def run_multiple_spiders(websites, file_name):
    settings = get_project_settings()
    runner = CrawlerRunner(settings)

    @defer.inlineCallbacks
    def crawl(websites, file_name):
        for site in websites:
            # Pass settings properly before running Scrapy
            settings.set('FEEDS', {file_name: {'format': 'json', 'encoding': 'utf8'}})
            print(f"Starting Scrapy for {site['website_url']} → Saving to {file_name}")

            # Run Scrapy spider
            yield runner.crawl(DynamicNewsSpider,
                               website_url=site["website_url"],
                               list_rules_json=site["scraping_rules"],
                               item_rules_json=site["scraping_rules"],
                               search_keyword=site["search_keyword"],
                               file_name=file_name,
                               max_pagination=site["max_pagination"],
                               pagination_urls=site["pagination_urls"])

        reactor.stop()

    crawl(websites, file_name)
    reactor.run()

    wait_for_file(file_name)
    process_data(file_name)

# Function to restart Scrapy process
def restart_scraper(websites, file_name):
    global scrapy_process

    if scrapy_process and scrapy_process.is_alive():
        print("Stopping existing Scrapy process...")
        scrapy_process.terminate()
        scrapy_process.join()

    print("Starting new Scrapy process...")
    scrapy_process = multiprocessing.Process(target=run_multiple_spiders, args=(websites, file_name))
    scrapy_process.start()

# Function to wait for JSON file to be fully saved
def wait_for_file(file_name, timeout=60):
    import time
    start_time = time.time()

    while not os.path.exists(file_name):
        if time.time() - start_time > timeout:
            print(f"Timeout: File {file_name} not found after {timeout} seconds!")
            return
        time.sleep(2)  # Wait 2 seconds before checking again

# Function to process JSON data and store it in SQLite
def process_data(file_name):
    if not os.path.exists(file_name):
        print(f"File {file_name} not found! Skipping...")
        return

    print(f"Processing {file_name} and storing in database...")

    try:
        # Read and fix the JSON file
        with open(file_name, 'r+', encoding='utf-8') as f:
            data = f.read()

            # Fix broken JSON list structure
            fixed_data = data.replace('][', ',')

            # Write back the corrected JSON data
            f.seek(0)  # Move to the beginning of the file
            f.write(fixed_data)
            f.truncate()  # Remove any remaining old content

        # Load fixed JSON into pandas
        df = pd.read_json(StringIO(fixed_data))

    except (ValueError, json.JSONDecodeError) as e:
        print(f"Error reading or parsing JSON from {file_name}: {e}")
        return

    conn = sqlite3.connect("dynascrap.db")
    cursor = conn.cursor()

    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_title TEXT,
            article_author TEXT,
            article_source_name TEXT,
            article_summary TEXT,
            article_content TEXT,
            article_subject TEXT,
            article_tags TEXT,
            article_main_pic TEXT,
            article_publish_date TEXT,
            article_url TEXT
        )
        """)
    conn.commit()

    # Insert data dynamically
    for _, row in df.iterrows():
        cursor.execute("""
            INSERT INTO articles (article_title, article_author, article_source_name, article_summary,
            article_content, article_subject, article_tags, article_main_pic, article_publish_date, article_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row.get('article_title', "-"),
                row.get('article_author', "-"),
                row.get('article_source_name', "-"),
                row.get('article_summary', "-"),
                row.get('article_content', "-"),
                row.get('article_subject', "-"),
                ','.join(row.get('article_tags', [])),
                row.get('article_main_pic', "-"),
                row.get('article_publish_date', "-"),
                row.get('article_url', "-")
            )
        )

    conn.commit()
    conn.close()

# Route to receive scraping rules via POST request
@app.route('/scrape', methods=['POST'])
def receive_scraping_rules():

    global websites
    global file_name

    if not isinstance(request.get_json(), list):
        return jsonify({"error": "Expected a list of website scraping rules"}), 400

    websites = request.get_json()
    file_name = 'output.json'
    for site in websites:
        site["max_pagination"] = site.get("max_pagination", 2)

    restart_scraper(websites, file_name)
    #wait_for_file()
    #process_data()

    return jsonify({"message": "Scraping started and data will be stored...!"}), 200

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)