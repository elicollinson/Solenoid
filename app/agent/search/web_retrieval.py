
import requests
from bs4 import BeautifulSoup
from google.adk.tools.function_tool import FunctionTool

def read_webpage(url: str) -> str:
    """
    Reads the content of a web page and returns the text.
    
    Args:
        url: The URL of the web page to read.
        
    Returns:
        The text content of the web page.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
            
        text = soup.get_text()
        
        # Break into lines and remove leading/trailing space on each
        lines = (line.strip() for line in text.splitlines())
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Drop blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text[:10000] # Limit to 10k chars to avoid context overflow
    except Exception as e:
        return f"Error reading {url}: {e}"

# Create the tool instance
read_webpage_tool = FunctionTool(func=read_webpage)
