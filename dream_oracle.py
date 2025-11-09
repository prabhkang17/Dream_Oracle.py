import os
import json
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# --- Configuration ---
JOURNAL_FILE = "dream_journal.txt"
API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
# We hard-code a reliable model instead of searching for one
# UPDATED: Corrected the model ID to the one that works
MODEL_ID = "gemini-flash-latest" 
API_TIMEOUT = 45
MAX_OUTPUT_TOKENS = 2048 
GENERATION_TEMPERATURE = 0.8
MAX_RETRIES = 3 # Number of times to retry on network errors

# --- ANSI Color Codes for Terminal Styling ---
class Colors:
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def typing_effect(text, delay=0.03, color=Colors.CYAN):
    """Prints text with a typing effect."""
    text_to_print = str(text)
    for char in text_to_print:
        print(color + char, end='', flush=True)
        time.sleep(delay)
    print(Colors.ENDC)


def make_api_request(url, api_key, method='POST', data=None, timeout=API_TIMEOUT):
    """
    Makes an API request with proper header-based authentication and retry logic.
    This is the most complex part, added to handle bad network connections.
    """
    headers = {
        'Content-Type': 'application/json',
        'x-goog-api-key': api_key
    }
    
    request_data = json.dumps(data).encode('utf-8') if data else None
    req = Request(url, data=request_data, headers=headers, method=method)
    
    last_exception = None
    # Try the request up to MAX_RETRIES times
    for attempt in range(MAX_RETRIES):
        try:
            # Try to open the URL
            with urlopen(req, timeout=timeout) as response:
                body = response.read().decode('utf-8')
                return json.loads(body) # Success!
        
        except HTTPError as e:
            # An "HTTP Error" (like 404, 500) means the server replied with an error.
            # We don't retry these, because the error is likely permanent (e.g., bad API key).
            error_body = e.read().decode('utf-8')
            print(f"{Colors.RED}API HTTPError: {error_body}{Colors.ENDC}")
            last_exception = RuntimeError(f"API Error: {e.reason}")
            break # Stop retrying
        
        except URLError as e:
            # A "URL Error" (like a timeout) means we couldn't reach the server.
            # This is a network problem, so we SHOULD retry.
            print(f"{Colors.YELLOW}Network Error (Attempt {attempt + 1}): {e.reason}. Retrying...{Colors.ENDC}")
            last_exception = RuntimeError(f"Network Error: {e.reason}")
            time.sleep(2 * (attempt + 1)) # Wait 2s, then 4s, then 6s
        
        except Exception as e:
            # Any other unexpected error
            print(f"{Colors.RED}Unexpected Error (Attempt {attempt + 1}): {e}. Retrying...{Colors.ENDC}")
            last_exception = RuntimeError(f"Unexpected error: {e}")
            time.sleep(2 * (attempt + 1))

    # If all retries failed, raise the last error
    raise last_exception


def build_prompt(dream_description):
    """Builds the complete prompt for the AI."""
    # UPDATED: New system prompt based on user request
    system_prompt = (
        "You are the Dream Oracle. Your persona is a blend of the Attack Titan and Sir Nighteye. "
        "You see the core truth of the dream, a future path, and you will state it plainly. "
        "You are not here to comfort. You are here to reveal the **facts** you have seen.\n\n"
        "1.  **Your Viewpoint:** Be cutthroat, honest, and factual. Find the central truth. Do not sugar-coat it.\n"
        "2.  **Your Presentation:** Be artistic, poetic, and melodramatic. Present the hard truth in a grand, impactful style. Use clear, powerful words, not overly complex ones.\n"
        "3.  **Your Knowledge:** Ground your interpretation in real-world symbology. Casually reference what a symbol (like 'water' or 'falling') means in psychology or across different cultures/religions to prove your point.\n\n"
        "Start by declaring the core truth you've seen. End with a sharp, profound statement that forces the user to confront this reality."
    )
    return f"{system_prompt}\n\nHere is the dream you must analyze:\n{dream_description}"


def parse_generation_response(response):
    """
    Safely parses the API response to extract generated text.
    """
    try:
        candidate = response.get("candidates", [])[0]
        
        # Check if the AI was cut off for any reason
        finish_reason = candidate.get("finishReason")
        if finish_reason and finish_reason != "STOP":
            print(f"{Colors.YELLOW}Warning: Response stopped due to {finish_reason}{Colors.ENDC}")
            if finish_reason == "MAX_TOKENS":
                return "The Oracle's vision was too vast and was cut short. (MAX_TOKENS)."
            else:
                return f"The Oracle's vision was blocked by: {finish_reason}."

        # If everything is fine, get the text
        text = candidate.get("content", {}).get("parts", [])[0].get("text")
        if text:
            return text
        else:
            return "The Oracle spoke, but the vision was unclear (could not parse text)."
        
    except Exception as e:
        print(f"{Colors.RED}Error parsing response: {e}{Colors.ENDC}")
        print(f"Raw Response: {response}")
        return "A critical error occurred while parsing the Oracle's response."


def get_ai_interpretation(dream_description, api_key):
    """
    Gets AI interpretation of a dream by calling the Gemini API.
    """
    # Build the full API URL
    url = f"{API_BASE_URL}/models/{MODEL_ID}:generateContent"
    
    # Create the payload to send to the AI
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": build_prompt(dream_description)}]
            }
        ],
        "generationConfig": {
            "temperature": GENERATION_TEMPERATURE,
            "maxOutputTokens": MAX_OUTPUT_TOKENS
        }
    }

    # Make the API call
    try:
        response = make_api_request(url, api_key, method='POST', data=payload)
        return parse_generation_response(response)
    except Exception as e:
        print(f"{Colors.RED}API call failed after all retries.{Colors.ENDC}")
        return f"The Oracle is silent. {e}"


def sanitize_text(text):
    """Sanitizes text for safe file writing."""
    return text.replace('\x00', '').strip()


def save_dream(dream, interpretation):
    """Saves the dream and its interpretation to the journal file."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    
    dream = sanitize_text(dream)
    interpretation = sanitize_text(interpretation)
    
    entry = (
        f"Time: {timestamp}\n"
        f"Dream: {dream}\n\n"
        f"Interpretation:\n{interpretation}\n"
        f"{'=' * 60}\n\n"
    )
    
    try:
        with open(JOURNAL_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        typing_effect("Your dream has been etched into memory.", 0.02, Colors.GREEN)
    except Exception as e:
        print(f"{Colors.RED}Failed to save dream: {e}{Colors.ENDC}")


def view_journal():
    """Displays the contents of the dream journal."""
    if not os.path.exists(JOURNAL_FILE):
        typing_effect("Your dream journal is empty. Time to start dreaming!", 
                      0.02, Colors.YELLOW)
        return
    
    try:
        with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
            print(f"\n{Colors.BOLD}{Colors.MAGENTA}📜 Your Dream Journal 📜{Colors.ENDC}")
            print(f"{Colors.BLUE}{'-'*60}{Colors.ENDC}")
            print(Colors.CYAN + f.read() + Colors.ENDC)
            print(f"{Colors.BLUE}{'-'*60}{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.RED}Could not read the journal file: {e}{Colors.ENDC}")


def clear_journal():
    """Deletes the dream journal file after confirmation."""
    if not os.path.exists(JOURNAL_FILE):
        typing_effect("No journal found to clear.", 0.02, Colors.YELLOW)
        return
    
    confirm = input(
        f"{Colors.YELLOW}Are you sure you want to erase all saved dreams? "
        f"This cannot be undone. (y/n): {Colors.ENDC}"
    ).lower()
    
    if confirm == 'y':
        try:
            os.remove(JOURNAL_FILE)
            typing_effect("The old memories have faded into mist. Your journal is clear.", 
                          0.02, Colors.RED)
        except Exception as e:
            print(f"{Colors.RED}Failed to clear journal: {e}{Colors.ENDC}")
    else:
        typing_effect("The journal remains untouched.", 0.02, Colors.GREEN)


def main_menu():
    """Displays the main menu and returns user's choice."""
    print(f"\n{Colors.CYAN}{Colors.BOLD}--- Dream Oracle Menu ---{Colors.ENDC}")
    print(f"{Colors.GREEN}1. Interpret a New Dream")
    print(f"{Colors.BLUE}2. View Your Dream Journal")
    print(f"{Colors.RED}3. Clear Your Dream Journal")
    print(f"{Colors.YELLOW}4. Exit{Colors.ENDC}")
    return input(f"\n{Colors.BOLD}Choose an option (1-4): {Colors.ENDC}").strip()


def get_api_key():
    """
    Loads Gemini API key from environment variable or user input.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    
    if api_key:
        print(f"{Colors.GREEN}✅ Gemini API key detected from environment.{Colors.ENDC}")
        return api_key
    
    # If not found in environment, ask the user
    print(f"{Colors.YELLOW}GEMINI_API_KEY environment variable not found.{Colors.ENDC}")
    while True:
        api_key = input(
            f"{Colors.CYAN}Please paste your Gemini API Key (or type 'q' to quit): {Colors.ENDC}"
        ).strip()
        
        if api_key.lower() == 'q':
            return None
        if api_key:
            return api_key
        else:
            print(f"{Colors.RED}API Key cannot be empty.{Colors.ENDC}")


def main():
    """Main application loop."""
    typing_effect("🔮 Welcome, Dreamer... The Dream Oracle awaits your vision. 🌙", 
                  0.04, Colors.MAGENTA)
    
    # Load and validate API key
    api_key = get_api_key()
    if not api_key:
        print(f"{Colors.RED}No API key provided. Exiting.{Colors.ENDC}")
        return
    
    # Main menu loop
    while True:
        choice = main_menu()
        
        if choice == '1':
            dream = input(f"\n{Colors.CYAN}Describe your dream in detail:\n> {Colors.ENDC}")
            
            if not dream.strip():
                print(f"{Colors.YELLOW}You must provide a dream to be interpreted.{Colors.ENDC}")
                continue
            
            print(f"\n{Colors.MAGENTA}The Oracle is gazing into the ether... please wait.{Colors.ENDC}")
            interpretation = get_ai_interpretation(dream, api_key)
            
            print(f"\n{Colors.BOLD}{Colors.MAGENTA}--- The Oracle Speaks ---{Colors.ENDC}")
            typing_effect(interpretation, 0.02, Colors.CYAN)
            
            save_choice = input(
                f"\n{Colors.GREEN}Would you like to record this vision in your journal? (y/n): {Colors.ENDC}"
            ).lower()
            
            if save_choice == 'y':
                save_dream(dream, interpretation)
        
        elif choice == '2':
            view_journal()
        
        elif choice == '3':
            clear_journal()
        
        elif choice == '4':
            typing_effect("May your waking life be as insightful as your dreams. Farewell. 🌌", 
                          0.03, Colors.MAGENTA)
            break
        
        else:
            print(f"{Colors.RED}Invalid choice. Please select a number from 1 to 4.{Colors.ENDC}")
        
        try:
            input(f"\n{Colors.YELLOW}Press Enter to return to the menu...{Colors.ENDC}")
        except EOFError:
            pass


if __name__ == "__main__":
    main()
