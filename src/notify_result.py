import requests
from bs4 import BeautifulSoup
import time
import os
import re

# --- CONFIGURATION ---
URL = "https://jeemain.nta.nic.in/"
CHECK_INTERVAL = 30  # Check every 30 seconds

def clean_text(text):
    """Removes digits and extra space to ignore visitor counters/clocks."""
    text = re.sub(r'\d+', '', text) 
    return " ".join(text.split()).lower()

def get_page_data():
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    try:
        res = requests.get(URL, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 1. Track link names
        links = {l.get_text().strip(): l.get('href') for l in soup.find_all('a') if l.get_text().strip()}
        
        # 2. Track page text (ignoring code/scripts)
        for script in soup(["script", "style"]):
            script.decompose()
        visible_text = clean_text(soup.get_text())
        
        return visible_text, links
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Connection issue: {e}. Retrying...")
        return None, None

def trigger_alert(reason, detail=""):
    # macOS Voice + Notification
    os.system(f"osascript -e 'display notification \"{detail}\" with title \"{reason}\" sound name \"Submarine\"'")
    os.system("say -v Samantha 'The JEE Main results are live. Open the NTA website immediately.'")
    
    print(f"\n{'#'*50}")
    print(f"🚨 ACTUAL CHANGE DETECTED: {reason}")
    print(f"Detail: {detail}")
    print(f"{'#'*50}\n")

def run_monitor():
    print(f"🛡️  LIVE MONITOR ACTIVE for {URL}")
    print("This will stay silent until the Result or Score Card appears.")
    
    # Capture the current state (with the Final Answer Key already there)
    prev_text, prev_links = get_page_data()
    if not prev_text:
        print("Could not connect to NTA. Check your internet.")
        return

    print("Baseline captured. Monitoring started...")

    while True:
        time.sleep(CHECK_INTERVAL)
        curr_text, curr_links = get_page_data()
        
        if not curr_text:
            continue

        # 1. Check for NEW links containing result keywords
        new_links = set(curr_links.keys()) - set(prev_links.keys())
        for link_text in new_links:
            lt_lower = link_text.lower()
            # Must mention Session 2 and Result-related words, but NOT Session 1
            if ("session 2" in lt_lower or "session-2" in lt_lower) and \
               any(k in lt_lower for k in ["result", "score card", "scorecard", "nta score"]) and \
               "session 1" not in lt_lower:
                
                trigger_alert("JEE SESSION 2 RESULT FOUND", link_text)
                return # Exit once found

        # 2. Check for major text changes involving keywords
        if curr_text != prev_text:
            if "session 2" in curr_text and any(k in curr_text for k in ["result", "score card"]):
                # Only alert if the text change actually involves the results
                trigger_alert("WEBSITE TEXT UPDATED", "Session 2 Result keywords detected.")
                return

        print(f"[{time.strftime('%H:%M:%S')}] Monitoring... (No result link yet)", end='\r')
        prev_text, prev_links = curr_text, curr_links

if __name__ == "__main__":
    run_monitor()