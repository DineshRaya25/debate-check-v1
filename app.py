import streamlit as st
import requests
import json
from openai import OpenAI

# Load API keys from Streamlit secrets
OPENROUTER_API_KEY = st.secrets["api_keys"]["OPENROUTER_API_KEY"]
WOLFRAM_APP_ID = st.secrets["api_keys"]["WOLFRAM_APP_ID"]
OPENWEATHER_API_KEY = st.secrets["api_keys"]["OPENWEATHER_API_KEY"]
NEWS_API_KEY = st.secrets["api_keys"]["NEWS_API_KEY"]
GOOGLE_CSE_API_KEY = st.secrets["api_keys"]["GOOGLE_CSE_API_KEY"]
GOOGLE_CSE_ID = st.secrets["api_keys"]["GOOGLE_CSE_ID"]

# Initialize OpenRouter client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# -------- Helper Functions --------

def query_openrouter(prompt, model="google/gemini-2.5-flash-image-preview:free"):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ Error with OpenRouter: {str(e)}"

def query_wolfram(query):
    url = f"http://api.wolframalpha.com/v1/result?i={query}&appid={WOLFRAM_APP_ID}"
    r = requests.get(url)
    return r.text if r.status_code == 200 else "❌ Wolfram could not compute"

def query_weather(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
    r = requests.get(url).json()
    if "main" in r:
        return f"{city}: {r['main']['temp']}°C, {r['weather'][0]['description']}"
    return "❌ City not found"

def query_news():
    url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}"
    r = requests.get(url).json()
    if "articles" in r:
        return [article["title"] for article in r["articles"][:5]]
    return ["❌ No news available"]

def query_google_cse(query):
    url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_CSE_API_KEY}&cx={GOOGLE_CSE_ID}"
    r = requests.get(url).json()
    if "items" in r:
        return [item["title"] + " - " + item["link"] for item in r["items"][:5]]
    return ["❌ No search results"]

# -------- Streamlit App --------

st.title("🤖 LLM + External APIs Assistant (v1)")
st.write("This assistant uses LLMs for reasoning and external APIs for fact-checking.")

user_input = st.text_area("💬 Ask me anything:")

if st.button("Submit"):
    if user_input.strip() == "":
        st.warning("Please enter a question!")
    else:
        with st.spinner("Thinking..."):
            # Call APIs for facts
            wolfram_result = query_wolfram(user_input)
            weather_result = query_weather(user_input)
            news_result = query_news()
            google_results = query_google_cse(user_input)

            # Feed external info into LLM
            context = f"""
            User Question: {user_input}
            
            External Facts:
            - WolframAlpha: {wolfram_result}
            - Weather API: {weather_result}
            - NewsAPI: {news_result}
            - Google CSE: {google_results}
            """

            llm_response = query_openrouter(context)

        # Display response
        st.subheader("🤖 Assistant Response")
        st.write(llm_response)

        st.subheader("📡 External Sources Used")
        st.write(f"**Wolfram:** {wolfram_result}")
        st.write(f"**Weather:** {weather_result}")
        st.write(f"**News:** {news_result}")
        st.write(f"**Google Search:** {google_results}")
