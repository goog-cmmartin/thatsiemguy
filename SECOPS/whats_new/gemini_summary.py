import os
import google.generativeai as genai
import json

# Attempt to configure from environment variable first
API_KEY = os.getenv('GEMINI_API_KEY')

# If not in env, fall back to the hardcoded key for testing
if not API_KEY:
    API_KEY = "" # Add your key here for local testing if needed

if not API_KEY:
    print("Warning: GEMINI_API_KEY environment variable not set. Summarizer will fail.")
else:
    genai.configure(api_key=API_KEY)

# This is the new, structured prompt
SYSTEM_PROMPT = """
You are an expert analysis engine. Analyze the provided article content and return ONLY a single, raw JSON object with three specific keys:
1. "summary": A concise, one or two-sentence summary of the article.
2. "sentiment": A single-word sentiment: 'Positive', 'Negative', or 'Neutral'.
3. "category": A single, one-word category (e.g., 'Security', 'AI', 'Politics', 'Business', 'Tech', 'Release').

Example output:
{
  "summary": "The article discusses a new critical vulnerability in a web server and the patch released to fix it.",
  "sentiment": "Negative",
  "category": "Security"
}
"""

def get_analysis(title, link, description):
    """
    Generates a structured analysis (summary, sentiment, category) from Gemini.
    Returns a dictionary, or a dictionary with an error message.
    """
    if not API_KEY:
        return {"summary": "API key not configured.", "sentiment": "Unknown", "category": "Unknown"}

    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        prompt_content = f"Title: {title}\nLink: {link}\nDescription Snippet: {description}"
        
        response = model.generate_content([SYSTEM_PROMPT, prompt_content])
        
        # Clean the response text to get a valid JSON string
        json_text = response.text.strip().lstrip("```json").rstrip("```")
        
        # Parse the JSON response
        data = json.loads(json_text)
        return {
            "summary": data.get("summary", "No summary provided."),
            "sentiment": data.get("sentiment", "Unknown"),
            "category": data.get("category", "Unknown")
        }
    except json.JSONDecodeError as e:
        print(f"Error decoding Gemini JSON response: {e}")
        print(f"Raw response was: {response.text}")
        return {"summary": "Failed to parse analysis from AI response.", "sentiment": "Error", "category": "Error"}
    except Exception as e:
        print(f"Error generating summary: {e}")
        return {"summary": f"Could not generate summary due to an API error: {e}", "sentiment": "Error", "category": "Error"}

