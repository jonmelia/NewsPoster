# news_sources_config.py

news_sources_global = [
    {'name': 'The New York Times Politics', 'rss': 'https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml'},
    {'name': 'The Guardian Politics', 'rss': 'https://www.theguardian.com/politics/rss'},
    {'name': 'HuffPost Politics', 'rss': 'https://chaski.huffpost.com/us/auto/vertical/us-news'},
    {'name': 'Fox News Politics', 'rss': 'http://feeds.foxnews.com/foxnews/politics'},
    {'name': 'The Wall Street Journal Politics', 'rss': 'https://feeds.content.dowjones.io/public/rss/socialpoliticsfeed'},
    {'name': 'National Review', 'rss': 'https://www.nationalreview.com/feed/'},
    {'name': 'Breitbart Politics', 'rss': 'https://www.breitbart.com/politics/feed/'}
]

news_sources_uk = [
    {'name': 'BBC Politics', 'rss': 'http://feeds.bbci.co.uk/news/politics/rss.xml'},
    {'name': 'The Independent Politics', 'rss': 'https://www.independent.co.uk/news/politics/rss'},
    {'name': 'Daily Mail Politics', 'rss': 'https://www.dailymail.co.uk/news/uk-politics/index.rss'},
    {'name': 'The Sun Politics', 'rss': 'https://www.thesun.co.uk/news/politics/feed/'},
    {'name': 'Sky News Politics', 'rss': 'https://feeds.skynews.com/feeds/rss/politics.xml'},
    {'name': 'Financial Times Politics', 'rss': 'https://www.ft.com/politics?format=rss'}
]

news_sources_other_english = [
    {'name': 'BBC Politics', 'rss': 'http://feeds.bbci.co.uk/news/politics/rss.xml'},
    {'name': 'The Independent Politics', 'rss': 'https://www.independent.co.uk/news/politics/rss'},
    {'name': 'The Sun Politics', 'rss': 'https://www.thesun.co.uk/news/politics/feed/'},
    {'name': 'Sky News Politics', 'rss': 'https://feeds.skynews.com/feeds/rss/politics.xml'},
    {'name': 'Financial Times Politics', 'rss': 'https://www.ft.com/politics?format=rss'}
]

def get_all_news_sources(include_uk=True, include_other_english=False):
    sources = list(news_sources_global)
    if include_uk:
        sources += news_sources_uk
    if include_other_english:
        sources += news_sources_other_english
    return sources
