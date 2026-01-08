import feedparser
import curses
import webbrowser
import requests
from bs4 import BeautifulSoup
import textwrap
import re

# Change to your preferred RSS feed
FEED_URL = "https://www.rmf24.pl/feed"

def scrape_article(url):
    """Scrape the full article content from a URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove scripts, styles, and other unwanted elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'video', 'iframe', 'form', 'button']):
            element.decompose()
        
        # Remove ads and promotional content
        for element in soup.find_all(class_=lambda x: x and any(word in x.lower() for word in ['ad', 'promo', 'newsletter', 'subscribe'])):
            element.decompose()
        
        # Try CNN-specific and common article content selectors
        article_content = None
        selectors = [
            '[data-component="ArticleBody"]',
            '.zn-body__paragraph',
            '.l-container .zn-body__read-all',
            'div[data-module-name="ArticleBody"]',
            '.article__content',
            'article .content',
            '.story-body',
            '.entry-content', 
            '.post-content',
            'main article'
        ]
        
        for selector in selectors:
            try:
                content = soup.select(selector)
                if content:
                    text_preview = content[0].get_text().strip()
                    if len(text_preview) > 200:
                        article_content = content[0]
                        break
            except:
                continue
        
        if not article_content:
            paragraphs = soup.find_all('p')
            if paragraphs:
                good_paragraphs = []
                for p in paragraphs:
                    text = p.get_text().strip()
                    if (len(text) > 30 and 
                        not any(skip in text.lower() for skip in [
                            'cookie', 'privacy policy', 'terms of service', 
                            'subscribe', 'newsletter', 'follow us', 'share',
                            'copyright', '© 2024', 'all rights reserved'
                        ])):
                        good_paragraphs.append(p)
                
                if good_paragraphs:
                    article_content = soup.new_tag('div')
                    for p in good_paragraphs:
                        article_content.append(p)
        
        if article_content:
            # Extract text with proper spacing - THIS IS THE KEY FIX
            text = article_content.get_text(separator=' ', strip=True)
            
            # Normalize whitespace - remove all extra spaces and newlines
            text = re.sub(r'\s+', ' ', text)
            
            # Split into paragraphs at sentence endings followed by capital letters
            # This recreates proper paragraph breaks
            sentences = re.split(r'([.!?])\s*', text)
            paragraphs = []
            current_para = ""
            
            for i in range(0, len(sentences)-1, 2):
                sentence = sentences[i].strip()
                punct = sentences[i+1] if i+1 < len(sentences) else ""
                
                if sentence:
                    current_para += sentence + punct + " "
                    
                    # Start new paragraph if this looks like end of paragraph
                    # (sentence ends with period and next sentence starts with capital)
                    if (punct == '.' and i+2 < len(sentences) and 
                        sentences[i+2].strip() and sentences[i+2].strip()[0].isupper()):
                        paragraphs.append(current_para.strip())
                        current_para = ""
            
            # Add any remaining text
            if current_para.strip():
                paragraphs.append(current_para.strip())
            
            cleaned_text = '\n\n'.join(paragraphs)
            
            # Filter out noise lines
            lines = cleaned_text.split('\n')
            filtered_lines = []
            
            for line in lines:
                line = line.strip()
                if line and not any(phrase in line.lower() for phrase in [
                    'video ad feedback', 'now playing', 'source:', 'videos',
                    'watch the video', 'click to expand', 'advertisement',
                    'duration:', 'watch:', 'play video', 'sign up',
                    'newsletter', 'breaking news', 'live updates',
                    'get cnn', 'download the app', 'follow cnn'
                ]) and len(line) > 10:
                    filtered_lines.append(line)
            
            final_text = '\n\n'.join(filtered_lines).strip()
            
            if len(final_text) < 150:
                return "This appears to be primarily video/multimedia content. Use 'o' to open in browser."
            
            return final_text if final_text else "Could not extract meaningful content."
        
        return "Could not extract article content from this URL."
    
    except Exception as e:
        return f"Error loading article: {str(e)}"

def display_article(stdscr, title, content, width):
    """Display article content with scrolling"""
    lines = []
    lines.append("=" * min(width - 2, 80))
    lines.append(title)
    lines.append("=" * min(width - 2, 80))
    lines.append("")
    
    # Use a more generous wrap width to avoid awkward breaks
    wrap_width = min(width - 4, 100)  # Don't wrap too narrowly
    
    for paragraph in content.split('\n\n'):
        if paragraph.strip():
            # Use textwrap but with better parameters
            wrapped = textwrap.fill(
                paragraph.strip(), 
                width=wrap_width,
                break_long_words=False,  # Don't break words
                break_on_hyphens=True,   # But allow breaks on hyphens
                expand_tabs=False
            )
            lines.extend(wrapped.split('\n'))
            lines.append("")  # Blank line between paragraphs
    
    # Remove trailing blank line
    if lines and lines[-1] == "":
        lines.pop()
    
    lines.append("")
    lines.append("Press 'b' to go back, UP/DOWN to scroll, 'o' to open in browser")
    
    return lines

def main(stdscr):
    # Clear screen and get RSS entries
    stdscr.clear()
    feed = feedparser.parse(FEED_URL)
    entries = feed.entries

    if not entries:
        stdscr.addstr(0, 0, "No RSS entries found. Press any key to exit.")
        stdscr.refresh()
        stdscr.getch()
        return

    pos = 0  # Current selection
    scroll_offset = 0  # For scrolling when list is longer than screen
    view_mode = 'list'  # 'list' or 'article'
    article_scroll = 0
    article_lines = []
    current_article_url = ""

    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        
        if view_mode == 'list':
            # Display RSS feed list
            max_display_lines = height - 2
            
            stdscr.addstr(0, 0, "CNN RSS Headlines (UP/DOWN, ENTER for article, 'o' for browser, Q to quit):")
            
            start_idx = scroll_offset
            end_idx = min(len(entries), scroll_offset + max_display_lines)
            
            for i, idx in enumerate(range(start_idx, end_idx)):
                if i + 1 < height:
                    entry = entries[idx]
                    line_text = entry.title
                    
                    if len(line_text) > width - 3:
                        line_text = line_text[:width - 6] + "..."
                    
                    if idx == pos:
                        stdscr.addstr(i + 1, 0, '> ' + line_text, curses.A_REVERSE)
                    else:
                        stdscr.addstr(i + 1, 0, '  ' + line_text)
        
        elif view_mode == 'article':
            # Display article content
            if article_scroll < len(article_lines):
                display_end = min(len(article_lines), article_scroll + height)
                for i, line in enumerate(article_lines[article_scroll:display_end]):
                    if i < height:
                        display_line = line[:width-1] if len(line) > width-1 else line
                        try:
                            stdscr.addstr(i, 0, display_line)
                        except curses.error:
                            pass
        
        stdscr.refresh()

        key = stdscr.getch()
        
        if view_mode == 'list':
            if key == curses.KEY_UP and pos > 0:
                pos -= 1
                if pos < scroll_offset:
                    scroll_offset = pos
            elif key == curses.KEY_DOWN and pos < len(entries) - 1:
                pos += 1
                if pos >= scroll_offset + max_display_lines:
                    scroll_offset = pos - max_display_lines + 1
            elif key == ord('\n') or key == ord('\r'):
                # Load and display full article
                stdscr.clear()
                stdscr.addstr(0, 0, "Loading article...")
                stdscr.refresh()
                
                current_article_url = entries[pos].link
                article_content = scrape_article(current_article_url)
                article_lines = display_article(stdscr, entries[pos].title, article_content, width)
                article_scroll = 0
                view_mode = 'article'
            elif key == ord('o') or key == ord('O'):
                # Open in browser
                webbrowser.open(entries[pos].link)
        
        elif view_mode == 'article':
            if key == curses.KEY_UP and article_scroll > 0:
                article_scroll -= 1
            elif key == curses.KEY_DOWN and article_scroll < len(article_lines) - height + 1:
                article_scroll += 1
            elif key == ord('b') or key == ord('B'):
                view_mode = 'list'
            elif key == ord('o') or key == ord('O'):
                webbrowser.open(current_article_url)
        
        if key == ord('q') or key == ord('Q'):
            break

if __name__ == "__main__":
    curses.wrapper(main)