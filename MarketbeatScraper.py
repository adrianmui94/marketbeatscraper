#!/usr/bin/env python
# coding: utf-8

# # Marketbeat Scraper
# 
# Redone as a class object. For practice.
# 
# Iterates through the stock analyst upgrades/downgrades on marketbeat.com by day and pulls the into a csv file.

# In[1]:


# Assert selenium chromedriver is up to date
from webdriver_manager.chrome import ChromeDriverManager

# Web scraping libraries 
from selenium import webdriver 
from selenium.webdriver.common.keys import Keys 

# BeautifulSoup 
import bs4 

# Common libraries 
import os 
import re
from pprint import pprint 
from tqdm import tqdm
import datetime as dt 
import time
import csv


# In[6]:


class MarketbeatScraper():
    def __init__(self, initial_date = dt.datetime.today().strftime("%m/%d/%Y"), cwd = os.getcwd()):
        """
        Creates a 
        """
        self.initial_date = initial_date
        # Initialize webdriver
        self.wb = webdriver.Chrome(ChromeDriverManager().install())
        url = 'https://www.marketbeat.com/ratings/'
        self.wb.get(url)
        self.handle_first_popup()
        self.change_date(initial_date)
        
        # Make csv file if doesn't exist
        if 'marketbeat_analyst_data.csv' not in os.listdir(cwd):
            with open('marketbeat_analyst_data.csv', 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['date', 'ticker', 'company', 'action', 'brokerage',
                                 'pt1', 'pt2', 'rating1', 'rating2', 'impact'])
                
        # Check scraped dates so we don't have to scrape them again.
        with open('marketbeat_analyst_data.csv', 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            self.completed_dates = set([row[0] for row in list(reader)[1:]])
    
    def handle_first_popup(self):
        '''
        Done to clear the first popup that happens.
        '''
        if self.wb.find_element_by_id('optinform-modal'):
            self.wb.find_element_by_class_name('x').click()

    def handle_other_popup(self):
        '''
        Other popups can occur during the scraping process.
        '''
        try:
            if self.wb.find_element_by_xpath('//*[@id="optinform-modal"]/div/span'):
                self.wb.find_element_by_xpath('//*[@id="optinform-modal"]/div/span').click()
        except:
            pass
        
    def change_date(self, date):
        '''
        Changes the date on the analyst website for Marketbeat.
        This is necessary because using clearing the datefield with clear() will reset to the previous date 
        since there is no cursor inside the field.
        --------------------------------------------------------------------------------------------------
        INPUT:
        date - the date in either datetime or string format


        OUTPUT:
        None
        '''
        if type(date) == type(dt.datetime.today().date()):
            date = date.strftime('%m/%d/%Y')
        # Submitting date information 

        # Click on the date field
        date_field = self.wb.find_element_by_name('ctl00$cphPrimaryContent$txtStartDate')
        date_field.click()

        # Backspace the current date 
        for _ in range(11):
            webdriver.ActionChains(self.wb).send_keys(Keys.BACKSPACE).perform()

        # Send a new date
        date_field.send_keys(date)
        webdriver.ActionChains(self.wb).send_keys(Keys.ENTER).perform()
        
    def scrape_values(self, html, page_date_str):
        '''
        Pulls the tabular analyst data from the current marketbeat analyst page using BeautifulSoup4
        --------------------------------------------------------------------------------------------------
        INPUT:
        html - Can be from selenium page source or via requests.

        OUTPUT:
        scraped - 2D array of scraped values.
        '''
        scraped = []
        soup = bs4.BeautifulSoup(html)

        # The rows of the table are enclosed within the 'tr' tag.
        table_rows =  soup.find_all('tr')

        # Iterate through the rows of the table, ignoring the header
        for row in table_rows[1:]:

            # Grab the ticker & company name
            try:
                ticker = row.select('.ticker-area')[0].text.strip().upper()
                company_name = row.select('.title-area')[0].text.strip().upper()

            # One row in this table is always an ad (?)
            except IndexError:
                continue

            # The remaining columns do not have unique names and are enclosed in the 'td' tag
            # The first td tag includes the things scraped above, so we ignore it
            action_description = row.find_all('td')[1:]

            # Clean the list of their tags
            cleaned = list(map(lambda x: x.text.strip(), action_description))[:-1] # Last item is useless
            del cleaned[2] # Current price is useless

            # Extract 0, 1, or 2 price targets
            clean_targets = self.handle_price_targets(cleaned[2]) 

            # Extract 1 or 2 price targets
            clean_ratings = self.handle_ratings(cleaned[-2])

            # Formatted row for appending to master rows
            scraped_row = [page_date_str, ticker, company_name] + cleaned[:2] + clean_targets + clean_ratings + [cleaned[-1]]
            scraped.append(scraped_row)
        
        return scraped
    
    def handle_price_targets(self, price_target):
        '''
        Marketbeat price target column can be empty, have one number, or two numbers.
        Use this function to return all the numbers in separate columns.
        --------------------------------------------------------------------------------------------------
        INPUT:
        price_target - string, targets in the format $\d\d.\d\d. Can include a '➝' character indicating a price change.

        OUTPUT:
        clean_targets - list of 2 floats or Nones. The previous price target and the new one.
        '''
        # Remove impurities 
        price_target = price_target.replace('$', '').replace(',', '')
        price_target = price_target.replace('(', '').replace(')', '')
        price_target = price_target.replace('0.0%', '')
        price_target = re.split('[+-]', price_target)[0]

        # Case 1: The field is blank.
        if price_target == '':
            clean_targets = [None, None]

        # Case 2: The price target has changed and is indicated by an arrow
        elif '➝' in price_target:
            clean_targets = price_target.split('➝')
            clean_targets = [float(ct.strip()) for ct in clean_targets]

        else:
            clean_targets = [None, float(price_target.strip())]

        return clean_targets
    
    def handle_ratings(self, ratings):
        '''
        Marketbeat upgrades/downgrades show a change of rating (e.g. Neutral ➝ Outperform) or just have a single
        rating present (Neutral)
        Use this function to grab one or both actions.
        --------------------------------------------------------------------------------------------------
        INPUT:
        ratings - string, either has 0, 1, or 2 ratings

        OUTPUT:
        clean_ratings - list containing two different ratings, or one None and one rating.
        '''
        ratings = ratings.split('➝')
        if len(ratings) == 2:
            ratings = [rating.strip().upper() for rating in ratings]
        else:
            ratings = [None, ratings[0].upper()]
            if ratings[1] == '': ratings[1] = None

        return ratings
        
    def scrape_marketbeat(self):
        '''
        The full scraping program
        '''

        page_date = dt.datetime.strptime(self.initial_date, '%m/%d/%Y')

        while page_date < (dt.datetime.today() + dt.timedelta(days=1)):
            # Handle weekends
            if page_date.strftime('%A') in ['Saturday', 'Sunday']:
                page_date += dt.timedelta(days=1)
                continue

            # Use try/except to deal with selenium issues 
            # i.e. page loading too fast and elements not loading
            try:
                page_date_str = page_date.strftime('%m/%d/%Y')
                if page_date_str in self.completed_dates:
                    page_date += dt.timedelta(days=1)
                    continue
            except:
            # Close other popup if exists
                self.handle_other_popup()
                time.sleep(1)
                continue

            self.change_date(page_date_str)
            time.sleep(1.5)
            html = self.wb.page_source
            scraped = self.scrape_values(html, page_date_str)

            # Create a file to save your analyst ratings if one doesn't exist
            if scraped != []:
                with open('marketbeat_analyst_data.csv', 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f, delimiter = ',')
                    for row in scraped:
                        writer.writerow(row)

            # Increment by 1 day after completion
            page_date += dt.timedelta(days=1)

        print('Finished.')
        self.wb.close()


# In[7]:


if __name__ == '__main__':
    print("Input initial date to start from. (MM/DD/YYYY). Leave blank for today.")
    initial_date = input()
    if initial_date:
        mbs = MarketbeatScraper(initial_date)
    else:
        mbs = MarketbeatScraper()
    mbs.scrape_marketbeat()


# In[ ]:




