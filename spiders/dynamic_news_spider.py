import scrapy
import json

# Define Dynamic Scrapy Spider
class DynamicNewsSpider(scrapy.Spider):
    name = "dynascrap_news"

    def __init__(self, website_url, list_rules_json, item_rules_json, search_keyword, file_name, max_pagination, pagination_urls=None, *args, **kwargs):
        super(DynamicNewsSpider, self).__init__(*args, **kwargs)
        self.website_url = website_url
        self.search_keyword = search_keyword
        #self.list_rules = json.loads(list_rules_json)
        #self.item_rules = json.loads(item_rules_json)
        self.list_rules = list_rules_json if isinstance(list_rules_json, dict) else json.loads(list_rules_json)
        self.item_rules = item_rules_json if isinstance(item_rules_json, dict) else json.loads(item_rules_json)
        self.start_urls = [website_url] + (pagination_urls or [])
        self.max_pagination = max_pagination
        self.page_count = 0
        self.file_name = file_name  # Unique filename for each website

    # Scrapy will save output in this file
    custom_settings = {
        'FEEDS': {
            'output.json': {'format': 'json', 'encoding': 'utf8'}
        },
        'LOG_ENABLED': True  # Enable logging for debugging
    }
    def parse(self, response):

        if self.page_count >= self.max_pagination:
            self.log(f"Reached max pagination limit ({self.max_pagination}) for {self.website_url}. Stopping!")
            return

        self.page_count += 1

        # First, scrape the listing page to extract article URLs
        article_links = response.css(self.list_rules["item_url"]).getall()

        if not article_links:
            self.log(f"No article links found on {response.url}")
            return

        for article_url in article_links:
            absolute_url = response.urljoin(article_url)  # Convert relative URL to absolute
            print(f"----=----> {absolute_url}")
            #absolute_url = article_url
            yield response.follow(absolute_url, callback=self.parse_item)

        next_page_url = response.css(self.list_rules["next_page_url"]).get()
        if next_page_url:
            absolute_next_page_url = response.urljoin(next_page_url)
            print(f"----****----> NEXT PAGE {absolute_next_page_url}")
            yield response.follow(absolute_next_page_url, callback=self.parse)

    def parse_item(self, response):
        item = {}
        for key, selector in self.item_rules.items():
            item[key] = response.css(selector).get()

        item['article_url'] = response.url
        yield item