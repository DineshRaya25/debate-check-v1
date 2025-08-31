import streamlit as st
import requests
from openai import OpenAI

# ==============================
# Load Secrets from Streamlit Cloud
# ==============================
OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
#GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
GOOGLE_CSE_ID = st.secrets["GOOGLE_CSE_ID"]
WOLFRAM_APP_ID = st.secrets["WOLFRAM_APP_ID"]
OPENWEATHER_API_KEY = st.secrets["OPENWEATHER_API_KEY"]
NEWS_API_KEY = st.secrets["NEWS_API_KEY"]

# ==============================
# Helper Functions
# ==============================

def ask_openrouter(user_input):
    """Query OpenRouter LLM"""
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        response = client.chat.completions.create(
            model="google/gemini-2.5-flash-image-preview:free",
            messages=[{"role": "user", "content": user_input}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ OpenRouter error: {e}"


def google_search(query):
    """Perform Google Custom Search"""
    url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_API_KEY}&cx={GOOGLE_CSE_ID}"
    try:
        response = requests.get(url).json()
        if "error" in response:
            return [f"❌ Google API error: {response['error']['message']}"]
        items = response.get("items", [])
        return [f"{i['title']} - {i['link']}" for i in items] if items else ["❌ No search results"]
    except Exception as e:
        return [f"❌ Google Search error: {e}"]


def ask_wolfram(query):
    """Query Wolfram Alpha"""
    url = f"http://api.wolframalpha.com/v2/query?appid={WOLFRAM_APP_ID}&input={query}&output=json"
    try:
        response = requests.get(url).json()
        if not response["queryresult"]["success"]:
            return "❌ Wolfram could not compute"
        pods = response["queryresult"]["pods"]
        for pod in pods:
            if pod["title"].lower() in ["result", "exact result", "decimal approximation"]:
                return pod["subpods"][0]["plaintext"]
        return pods[0]["subpods"][0]["plaintext"] if pods else "❌ No result found"
    except Exception as e:
        return f"❌ Wolfram error: {e}"


def get_weather(city):
    """Fetch weather info from OpenWeather"""
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        response = requests.get(url).json()
        if response.get("cod") != 200:
            return f"❌ Weather error: {response.get('message','City not found')}"
        temp = response["main"]["temp"]
        desc = response["weather"][0]["description"]
        return f"{city}: {temp}°C, {desc}"
    except Exception as e:
        return f"❌ Weather error: {e}"


def get_news():
    """Fetch top headlines from NewsAPI"""
    url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}"
    try:
        response = requests.get(url).json()
        if response.get("status") != "ok":
            return [f"❌ News API error: {response.get('message','Unknown error')}"]
        return [f"{a['title']} - {a['source']['name']}" for a in response.get("articles", [])]
    except Exception as e:
        return [f"❌ News API error: {e}"]

# ==============================
# Streamlit UI
# ==============================

st.set_page_config(page_title="AI Assistant V1", page_icon="🤖", layout="centered")
st.title("🤖 Ask me anything!")

user_input = st.text_area("Ask me anything:", height=100)

if st.button("Submit") and user_input:
    with st.spinner("Thinking..."):
        assistant_response = ask_openrouter(user_input)
        wolfram_result = ask_wolfram(user_input)
        weather_result = get_weather(user_input)
        news_result = get_news()
        google_results = google_search(user_input)

    # Display response
    st.subheader("🤖 Assistant Response")
    st.write(assistant_response)

    # External Sources
    st.subheader("📡 External Sources Used")
    st.write("**Wolfram:**", wolfram_result)
    st.write("**Weather:**", weather_result)
    st.write("**News:**", news_result[:5])
    st.write("**Google Search:**", google_results[:5])
