#!/usr/bin/env python3
"""
9anime.to Anime Scraper
Scrapes anime information from https://9animetv.to/
"""

import requests
from bs4 import BeautifulSoup
import json
import csv
import time
import re
from urllib.parse import urljoin, urlparse
import logging
from typing import List, Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NineAnimeScraper:
    def __init__(self):
        self.base_url = "https://9animetv.to"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        self.scraped_anime = []
    
    def get_page(self, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch a page with retry logic"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                return BeautifulSoup(response.content, 'html.parser')
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(2)
                else:
                    logger.error(f"Failed to fetch {url} after {retries} attempts")
                    return None
    
    def extract_anime_info(self, anime_element) -> Dict:
        """Extract anime information from a single anime element"""
        anime_info = {}
        
        try:
            # For 9anime, we need to look for specific patterns
            # The anime links have classes like 'film-poster-ahref' and 'dynamic-name'
            
            # Extract title - look for dynamic-name class first (this is the main title)
            title_element = anime_element.find(class_='dynamic-name')
            if not title_element:
                # Fallback to film-name class or other title selectors
                title_element = anime_element.find(class_='film-name')
            if not title_element:
                title_element = anime_element.find(['h3', 'h2', '.title', '.name', 'a'])
            
            if title_element:
                title = title_element.get_text(strip=True)
                # Skip if title is too short or looks like navigation
                if len(title) > 3 and title.lower() not in ['updated', 'added', 'ongoing', 'upcoming', 'home']:
                    anime_info['title'] = title
            
            # Extract link - look for dynamic-name link or any link with /watch/
            link_element = anime_element.find('a', class_='dynamic-name')
            if not link_element:
                link_element = anime_element.find('a', href=re.compile(r'/watch/'))
            if not link_element:
                link_element = anime_element.find('a', class_='film-poster-ahref')
            if not link_element:
                link_element = anime_element.find('a')
                
            if link_element and link_element.get('href'):
                href = link_element['href']
                if '/watch/' in href:  # Only process actual anime links
                    anime_info['url'] = urljoin(self.base_url, href)
                    anime_info['id'] = href.split('/')[-1] if href else None
                    
                    # Extract Japanese name if available
                    if link_element.get('data-jname'):
                        anime_info['japanese_name'] = link_element.get('data-jname')
            
            # Extract image - look for img within the same container
            img_element = anime_element.find('img')
            if not img_element and anime_element.parent:
                img_element = anime_element.parent.find('img')
            if not img_element and anime_element.parent and anime_element.parent.parent:
                img_element = anime_element.parent.parent.find('img')
                
            if img_element:
                anime_info['image_url'] = urljoin(self.base_url, img_element.get('src', ''))
                anime_info['alt_text'] = img_element.get('alt', '')
            
            # Extract additional info like episodes, status, etc.
            info_elements = anime_element.find_all(['span', 'div', 'p'], class_=re.compile(r'(episode|status|year|genre|rating|ep|type)'))
            for elem in info_elements:
                text = elem.get_text(strip=True)
                class_list = elem.get('class', [])
                
                if any('ep' in cls.lower() for cls in class_list) or 'Ep' in text:
                    anime_info['episodes'] = text
                elif 'status' in ' '.join(class_list).lower():
                    anime_info['status'] = text
                elif re.match(r'\d{4}', text):
                    anime_info['year'] = text
                elif 'type' in ' '.join(class_list).lower():
                    anime_info['type'] = text
            
            # Extract rating if available
            rating_element = anime_element.find(class_=re.compile(r'rating|score|star'))
            if rating_element:
                anime_info['rating'] = rating_element.get_text(strip=True)
            
            # Extract genres - 9anime may have different genre structure
            genre_elements = anime_element.find_all(class_=re.compile(r'genre|tag'))
            if genre_elements:
                genres = []
                for genre in genre_elements:
                    genre_text = genre.get_text(strip=True)
                    if genre_text and ',' in genre_text:
                        # Split genres if they're comma-separated
                        genres.extend([g.strip() for g in genre_text.split(',')])
                    else:
                        genres.append(genre_text)
                anime_info['genres'] = [g for g in genres if g]
            
            # Extract description if available
            desc_element = anime_element.find(['p', 'div'], class_=re.compile(r'desc|summary|synopsis'))
            if desc_element:
                anime_info['description'] = desc_element.get_text(strip=True)
            
        except Exception as e:
            logger.warning(f"Error extracting anime info: {e}")
        
        return anime_info
    
    def scrape_homepage_anime(self) -> List[Dict]:
        """Scrape anime from the homepage"""
        logger.info("Scraping homepage anime...")
        soup = self.get_page(self.base_url)
        if not soup:
            return []
        
        homepage_anime = []
        
        # Look for anime sections on homepage
        anime_sections = soup.find_all(['section', 'div'], class_=re.compile(r'anime|show|movie|trending|popular|latest'))
        
        for section in anime_sections:
            anime_elements = section.find_all(['div', 'article', 'li'], class_=re.compile(r'anime|item|card|show'))
            for element in anime_elements:
                anime_info = self.extract_anime_info(element)
                if anime_info and anime_info.get('title'):
                    anime_info['category'] = 'homepage'
                    homepage_anime.append(anime_info)
        
        logger.info(f"Found {len(homepage_anime)} anime from homepage")
        return homepage_anime
    
    def scrape_updated_anime(self) -> List[Dict]:
        """Scrape recently updated anime"""
        logger.info("Scraping updated anime...")
        
        # 9anime has an "Updated" section
        updated_url = f"{self.base_url}/updated"
        soup = self.get_page(updated_url)
        
        updated_anime = []
        if soup:
            anime_elements = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'anime|item|card|show'))
            for element in anime_elements:
                anime_info = self.extract_anime_info(element)
                if anime_info and anime_info.get('title'):
                    anime_info['category'] = 'updated'
                    updated_anime.append(anime_info)
        
        logger.info(f"Found {len(updated_anime)} updated anime")
        return updated_anime
    
    def scrape_added_anime(self) -> List[Dict]:
        """Scrape newly added anime"""
        logger.info("Scraping added anime...")
        
        added_url = f"{self.base_url}/added"
        soup = self.get_page(added_url)
        
        added_anime = []
        if soup:
            anime_elements = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'anime|item|card|show'))
            for element in anime_elements:
                anime_info = self.extract_anime_info(element)
                if anime_info and anime_info.get('title'):
                    anime_info['category'] = 'added'
                    added_anime.append(anime_info)
        
        logger.info(f"Found {len(added_anime)} added anime")
        return added_anime
    
    def scrape_ongoing_anime(self) -> List[Dict]:
        """Scrape ongoing anime"""
        logger.info("Scraping ongoing anime...")
        
        ongoing_url = f"{self.base_url}/ongoing"
        soup = self.get_page(ongoing_url)
        
        ongoing_anime = []
        if soup:
            anime_elements = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'anime|item|card|show'))
            for element in anime_elements:
                anime_info = self.extract_anime_info(element)
                if anime_info and anime_info.get('title'):
                    anime_info['category'] = 'ongoing'
                    ongoing_anime.append(anime_info)
        
        logger.info(f"Found {len(ongoing_anime)} ongoing anime")
        return ongoing_anime
    
    def scrape_upcoming_anime(self) -> List[Dict]:
        """Scrape upcoming anime"""
        logger.info("Scraping upcoming anime...")
        
        upcoming_url = f"{self.base_url}/upcoming"
        soup = self.get_page(upcoming_url)
        
        upcoming_anime = []
        if soup:
            # Look for anime containers, avoiding navigation elements
            anime_elements = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'anime|item|card|show|movie'))
            for element in anime_elements:
                # Skip navigation elements
                if element.find('a', href=re.compile(r'/(home|updated|added|ongoing|upcoming)$')):
                    continue
                    
                anime_info = self.extract_anime_info(element)
                if anime_info and anime_info.get('title') and len(anime_info.get('title', '')) > 3:
                    anime_info['category'] = 'upcoming'
                    upcoming_anime.append(anime_info)
        
        logger.info(f"Found {len(upcoming_anime)} upcoming anime")
        return upcoming_anime
    
    def scrape_by_genre(self, genre: str) -> List[Dict]:
        """Scrape anime by specific genre"""
        logger.info(f"Scraping {genre} anime...")
        
        # Convert genre to URL format
        genre_url = genre.lower().replace(' ', '-').replace('&', 'and')
        genre_url = f"{self.base_url}/genre/{genre_url}"
        
        soup = self.get_page(genre_url)
        
        genre_anime = []
        if soup:
            anime_elements = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'anime|item|card|show|movie'))
            for element in anime_elements:
                anime_info = self.extract_anime_info(element)
                if anime_info and anime_info.get('title') and len(anime_info.get('title', '')) > 3:
                    anime_info['category'] = f'genre_{genre.lower()}'
                    anime_info['genre'] = genre
                    genre_anime.append(anime_info)
        
        logger.info(f"Found {len(genre_anime)} {genre} anime")
        return genre_anime
    
    def scrape_recently_updated(self) -> List[Dict]:
        """Scrape recently updated anime"""
        logger.info("Scraping recently updated anime...")
        
        updated_url = f"{self.base_url}/recently-updated"
        soup = self.get_page(updated_url)
        
        updated_anime = []
        if soup:
            anime_elements = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'anime|item|card|show|movie'))
            for element in anime_elements:
                # Skip navigation elements
                if element.find('a', href=re.compile(r'/(home|updated|added|ongoing|upcoming)$')):
                    continue
                    
                anime_info = self.extract_anime_info(element)
                if anime_info and anime_info.get('title') and len(anime_info.get('title', '')) > 3:
                    anime_info['category'] = 'recently_updated'
                    updated_anime.append(anime_info)
        
        logger.info(f"Found {len(updated_anime)} recently updated anime")
        return updated_anime
    
    def scrape_recently_added(self, page: int = 1) -> List[Dict]:
        """Scrape recently added anime from a specific page"""
        logger.info(f"Scraping recently added anime from page {page}...")
        
        if page == 1:
            added_url = f"{self.base_url}/recently-added"
        else:
            added_url = f"{self.base_url}/recently-added?page={page}"
            
        soup = self.get_page(added_url)
        
        added_anime = []
        if soup:
            # Look for film-detail elements which contain the anime information
            anime_elements = soup.find_all('div', class_='film-detail')
            
            for element in anime_elements:
                anime_info = self.extract_anime_info(element)
                if anime_info and anime_info.get('title') and len(anime_info.get('title', '')) > 3:
                    anime_info['category'] = 'recently_added'
                    anime_info['page'] = page
                    added_anime.append(anime_info)
        
        logger.info(f"Found {len(added_anime)} recently added anime on page {page}")
        return added_anime
    
    def scrape_recently_added_multiple_pages(self, max_pages: int = 5) -> List[Dict]:
        """Scrape recently added anime from multiple pages"""
        logger.info(f"Scraping recently added anime from {max_pages} pages...")
        
        all_anime = []
        for page in range(1, max_pages + 1):
            try:
                page_anime = self.scrape_recently_added(page)
                all_anime.extend(page_anime)
                time.sleep(1)  # Be respectful with requests
                logger.info(f"Completed page {page}/{max_pages}")
            except Exception as e:
                logger.warning(f"Failed to scrape page {page}: {e}")
        
        # Remove duplicates based on title and URL
        unique_anime = []
        seen_titles = set()
        seen_urls = set()
        
        for anime in all_anime:
            title = anime.get('title', '').lower()
            url = anime.get('url', '')
            
            if title not in seen_titles and url not in seen_urls and title and url:
                unique_anime.append(anime)
                seen_titles.add(title)
                seen_urls.add(url)
        
        logger.info(f"Total unique recently added anime found across {max_pages} pages: {len(unique_anime)}")
        return unique_anime
    
    def scrape_anime_details(self, anime_url: str) -> Dict:
        """Scrape detailed information for a specific anime"""
        soup = self.get_page(anime_url)
        if not soup:
            return {}
        
        details = {}
        
        try:
            # Extract detailed description
            desc_element = soup.find(['div', 'section'], class_=re.compile(r'description|summary|synopsis'))
            if desc_element:
                details['description'] = desc_element.get_text(strip=True)
            
            # Extract more detailed info
            info_sections = soup.find_all(['div', 'dl'], class_=re.compile(r'info|details|metadata'))
            for section in info_sections:
                labels = section.find_all(['dt', 'span'], class_=re.compile(r'label'))
                values = section.find_all(['dd', 'span'], class_=re.compile(r'value'))
                
                for label, value in zip(labels, values):
                    label_text = label.get_text(strip=True).lower()
                    value_text = value.get_text(strip=True)
                    details[label_text] = value_text
            
            # Extract episode list if available
            episodes = soup.find_all(['div', 'li'], class_=re.compile(r'episode'))
            if episodes:
                details['episode_count'] = len(episodes)
                details['episodes'] = []
                for ep in episodes[:10]:  # Limit to first 10 episodes
                    ep_info = {
                        'number': ep.find(class_=re.compile(r'number|ep')).get_text(strip=True) if ep.find(class_=re.compile(r'number|ep')) else '',
                        'title': ep.find(class_=re.compile(r'title')).get_text(strip=True) if ep.find(class_=re.compile(r'title')) else '',
                        'url': urljoin(self.base_url, ep.find('a')['href']) if ep.find('a') else ''
                    }
                    details['episodes'].append(ep_info)
        
        except Exception as e:
            logger.warning(f"Error extracting anime details from {anime_url}: {e}")
        
        return details
    
    def scrape_all(self) -> List[Dict]:
        """Scrape all available anime from different sections"""
        logger.info("Starting comprehensive anime scraping...")
        
        all_anime = []
        
        # Scrape different sections from 9anime
        all_anime.extend(self.scrape_homepage_anime())
        all_anime.extend(self.scrape_recently_updated())
        all_anime.extend(self.scrape_recently_added())
        all_anime.extend(self.scrape_ongoing_anime())
        all_anime.extend(self.scrape_upcoming_anime())
        
        # Scrape some popular genres
        popular_genres = ['Action', 'Comedy', 'Drama', 'Romance', 'Fantasy']
        for genre in popular_genres:
            try:
                genre_anime = self.scrape_by_genre(genre)
                all_anime.extend(genre_anime[:10])  # Limit to 10 per genre
                time.sleep(1)  # Be respectful with requests
            except Exception as e:
                logger.warning(f"Failed to scrape {genre} genre: {e}")
        
        # Remove duplicates based on title and URL
        unique_anime = []
        seen_titles = set()
        seen_urls = set()
        
        for anime in all_anime:
            title = anime.get('title', '').lower()
            url = anime.get('url', '')
            
            if title not in seen_titles and url not in seen_urls and title and url and len(title) > 3:
                unique_anime.append(anime)
                seen_titles.add(title)
                seen_urls.add(url)
        
        self.scraped_anime = unique_anime
        logger.info(f"Total unique anime found: {len(unique_anime)}")
        
        return unique_anime
    
    def save_to_json(self, filename: str = "9anime_anime.json"):
        """Save scraped data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.scraped_anime, f, indent=2, ensure_ascii=False)
        logger.info(f"Data saved to {filename}")
    
    def save_to_csv(self, filename: str = "9anime_anime.csv"):
        """Save scraped data to CSV file"""
        if not self.scraped_anime:
            logger.warning("No data to save")
            return
        
        # Get all unique keys from all anime entries
        all_keys = set()
        for anime in self.scraped_anime:
            all_keys.update(anime.keys())
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=sorted(all_keys))
            writer.writeheader()
            writer.writerows(self.scraped_anime)
        
        logger.info(f"Data saved to {filename}")
    
    def print_summary(self):
        """Print a summary of scraped data"""
        if not self.scraped_anime:
            print("No anime data found")
            return
        
        print(f"\n=== 9ANIME.TO SCRAPING SUMMARY ===")
        print(f"Total anime found: {len(self.scraped_anime)}")
        
        categories = {}
        for anime in self.scraped_anime:
            category = anime.get('category', 'unknown')
            categories[category] = categories.get(category, 0) + 1
        
        print(f"\nBy category:")
        for category, count in categories.items():
            print(f"  {category}: {count}")
        
        print(f"\nSample anime:")
        for i, anime in enumerate(self.scraped_anime[:5]):
            print(f"  {i+1}. {anime.get('title', 'Unknown')} - {anime.get('category', 'Unknown')}")
            if anime.get('type'):
                print(f"      Type: {anime.get('type')}")
            if anime.get('episodes'):
                print(f"      Episodes: {anime.get('episodes')}")
        
        if len(self.scraped_anime) > 5:
            print(f"  ... and {len(self.scraped_anime) - 5} more")

def main():
    """Main function to run the scraper"""
    scraper = NineAnimeScraper()
    
    try:
        # Scrape all anime
        anime_data = scraper.scrape_all()
        
        if anime_data:
            # Save data
            scraper.save_to_json()
            scraper.save_to_csv()
            
            # Print summary
            scraper.print_summary()
        else:
            print("No anime data could be scraped. The site structure might have changed.")
    
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
