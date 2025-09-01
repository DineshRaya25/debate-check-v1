# app.py
import re
import time
import requests
import streamlit as st
from openai import OpenAI

# ==============================
# Secrets helper (supports flat or [api_keys] structure)
# ==============================
def get_secret(name: str, default=None):
    # flat
    if name in st.secrets:
        return st.secrets.get(name, default)
    # nested [api_keys]
    if "api_keys" in st.secrets and name in st.secrets["api_keys"]:
        return st.secrets["api_keys"].get(name, default)
    return default

# Load secrets (works with either flat or [api_keys] structure)
OPENROUTER_API_KEY = get_secret("OPENROUTER_API_KEY")
GOOGLE_API_KEY     = get_secret("GOOGLE_API_KEY")
GOOGLE_CSE_ID      = get_secret("GOOGLE_CSE_ID")
WOLFRAM_APP_ID     = get_secret("WOLFRAM_APP_ID") or get_secret("WOLFRAM_ALPHA_APP_ID")  # support both names
OPENWEATHER_API_KEY= get_secret("OPENWEATHER_API_KEY")
NEWS_API_KEY       = get_secret("NEWS_API_KEY")

# Optional (nice to have for OpenRouter rankings)
OPENROUTER_REFERER = get_secret("APP_REFERER", "https://your-app.example")
OPENROUTER_TITLE   = get_secret("APP_TITLE", "LLM Debate Assistant V1")

# ==============================
# Utility — simple intent detection
# ==============================
MATH_HINT = re.compile(r"(\d+\s*[\+\-\*/\^]\s*\d+)|\bsolve\b|\bevaluate\b|\bderivative\b|\bintegral\b", re.I)
WEATHER_HINT = re.compile(r"\b(weather|temperature|forecast)\b", re.I)
CITY_FROM_WEATHER = re.compile(r"(?:in|for)\s+([A-Za-z][A-Za-z\s\.\-']{1,40})$", re.I)

def should_check_weather(q: str) -> str | None:
    """
    Returns a city string if the query looks like a weather request.
    Examples: "weather in London", "temperature in New York"
    """
    if not WEATHER_HINT.search(q):
        return None
    m = CITY_FROM_WEATHER.search(q.strip())
    if m:
        city = m.group(1).strip().strip(".")
        return city
    # fallback: if user asked "weather" only, default to a neutral city to avoid errors
    if q.strip().lower() in {"weather", "forecast", "temperature"}:
        return "London"
    return None

def looks_like_math(q: str) -> bool:
    return bool(MATH_HINT.search(q))

# ==============================
# External API wrappers
# ==============================
def ask_openrouter(system_prompt: str, user_prompt: str, model: str = "google/gemini-2.5-flash-image-preview:free") -> str:
    if not OPENROUTER_API_KEY:
        return "❌ Missing API key: OPENROUTER_API_KEY"

    # OpenRouter via OpenAI client
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            extra_headers={
                "HTTP-Referer": OPENROUTER_REFERER,
                "X-Title": OPENROUTER_TITLE,
            },
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"❌ OpenRouter error: {e}"

# # Function: Query WolframAlpha
# def query_wolfram_alpha(query: str) -> str:
#     app_id = st.secrets["WOLFRAM_APP_ID"]  # ✅ from Streamlit secrets
#     url = "http://api.wolframalpha.com/v2/query"

#     params = {
#         "input": query,
#         "format": "plaintext",
#         "output": "JSON",
#         "appid": app_id
#     }

#     try:
#         response = requests.get(url, params=params, timeout=10)
#         response.raise_for_status()
#         data = response.json()

#         # ✅ Safely parse Wolfram response
#         if "queryresult" in data and data["queryresult"].get("success", False):
#             pods = data["queryresult"].get("pods", [])

#             # 1. Look for "Result" pod (usually main answer)
#             for pod in pods:
#                 if pod.get("title", "").lower() == "result":
#                     subpods = pod.get("subpods", [])
#                     if subpods and "plaintext" in subpods[0]:
#                         return subpods[0]["plaintext"]

#             # 2. If no "Result", take first pod with plaintext
#             for pod in pods:
#                 subpods = pod.get("subpods", [])
#                 if subpods and "plaintext" in subpods[0] and subpods[0]["plaintext"].strip():
#                     return subpods[0]["plaintext"]

#             return "No readable answer found from Wolfram Alpha."

#         else:
#             return "Wolfram Alpha could not compute an answer."

#     except Exception as e:
#         return f"⚠️ Wolfram Alpha error: {str(e)}"

def clean_query(query: str) -> str:
    # Remove filler words that confuse Wolfram Alpha
    query = query.lower().strip()
    query = re.sub(r"^(ok|hey|please)\s+", "", query)  # strip prefixes
    return query

def query_wolfram_alpha(query: str) -> str:
    app_id = st.secrets["WOLFRAM_APP_ID"]
    url = "http://api.wolframalpha.com/v2/query"

    cleaned_query = clean_query(query)

    params = {
        "input": cleaned_query,
        "format": "plaintext",
        "output": "JSON",
        "appid": app_id
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Debug: show raw Wolfram response in Streamlit expander
        with st.expander("🔎 Wolfram Alpha Debug"):
            st.json(data)

        if "queryresult" in data and data["queryresult"].get("success", False):
            pods = data["queryresult"].get("pods", [])
            for pod in pods:
                if pod.get("title", "").lower() == "result":
                    subpods = pod.get("subpods", [])
                    if subpods and subpods[0].get("plaintext"):
                        return subpods[0]["plaintext"]
            for pod in pods:
                subpods = pod.get("subpods", [])
                if subpods and subpods[0].get("plaintext"):
                    return subpods[0]["plaintext"]
            return "No readable answer found from Wolfram Alpha."
        else:
            return "Wolfram Alpha could not compute an answer."

    except Exception as e:
        return f"⚠️ Wolfram Alpha error: {str(e)}"


def google_cse_search(query: str, num: int = 5) -> list[str]:
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        return ["⚠️ Skipped (missing GOOGLE_API_KEY or GOOGLE_CSE_ID)"]
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "q": query,
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "num": max(1, min(num, 10)),
        "safe": "active",
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()
        if "error" in data:
            return [f"❌ Google API error: {data['error'].get('message', 'Unknown error')}"]
        items = data.get("items", [])
        if not items:
            return ["ℹ️ Google: no results"]
        return [f"{it.get('title','(no title)')} - {it.get('link','')}" for it in items]
    except Exception as e:
        return [f"❌ Google Search error: {e}"]

def openweather(city: str) -> str:
    if not OPENWEATHER_API_KEY:
        return "⚠️ Skipped (missing OPENWEATHER_API_KEY)"
    url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()
        if data.get("cod") != 200:
            return f"ℹ️ Weather: {data.get('message','city not found')}"
        temp = data["main"]["temp"]
        desc = data["weather"][0]["description"]
        return f"{city}: {temp}°C, {desc}"
    except Exception as e:
        return f"❌ Weather error: {e}"

def news_top(country: str = "us", limit: int = 5) -> list[str]:
    if not NEWS_API_KEY:
        return ["⚠️ Skipped (missing NEWS_API_KEY)"]
    url = "https://newsapi.org/v2/top-headlines"
    params = {"country": country, "apiKey": NEWS_API_KEY, "pageSize": max(1, min(limit, 20))}
    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()
        if data.get("status") != "ok":
            return [f"❌ News API error: {data.get('message','Unknown error')}"]
        articles = data.get("articles", [])
        out = []
        for a in articles[:limit]:
            title = a.get("title", "(no title)")
            src = a.get("source", {}).get("name", "")
            url = a.get("url", "")
            out.append(f"{title} - {src} - {url}")
        return out or ["ℹ️ No headlines"]
    except Exception as e:
        return [f"❌ News API error: {e}"]

# ==============================
# Compose LLM prompt with references
# ==============================
SYSTEM_PROMPT = (
    "You are the Answerer in a lightweight multi-agent pipeline. "
    "Respond in clear, direct language. Use external snippets (Wolfram, Google, Weather, News) "
    "as references only; keep the answer LLM-native. If references conflict, note uncertainty."
)

def build_context_snippet(user_q: str) -> dict:
    """Collect reference snippets depending on user question (contextual integration)."""
    refs = {}

    # Google CSE always useful for general grounding
    refs["google"] = google_cse_search(user_q, num=5)

    # Wolfram mostly for math / factual computations
    if looks_like_math(user_q):
        refs["wolfram"] = wolfram_compute(user_q)

    # Weather only if query clearly asks about weather
    city = should_check_weather(user_q)
    if city:
        refs["weather"] = openweather(city)

    # News only if user mentions news/headlines/trending
    if re.search(r"\bnews|headline|trending|today\b", user_q, re.I):
        refs["news"] = news_top(limit=5)

    return refs

def render_refs(context_refs: dict) -> str:
    """Turn reference dict to a concise bullet list for the LLM."""
    lines = []
    if "wolfram" in context_refs:
        lines.append(f"- Wolfram: {context_refs['wolfram']}")
    if "weather" in context_refs:
        lines.append(f"- Weather: {context_refs['weather']}")
    if "news" in context_refs:
        # join first 3 lines
        items = context_refs["news"]
        if isinstance(items, list):
            lines.append("- News:\n  " + "\n  ".join(items[:3]))
        else:
            lines.append(f"- News: {items}")
    if "google" in context_refs:
        items = context_refs["google"]
        if isinstance(items, list):
            lines.append("- Google:\n  " + "\n  ".join(items[:5]))
        else:
            lines.append(f"- Google: {items}")
    return "\n".join(lines) if lines else "(no external references)"

# ==============================
# Streamlit UI
# ==============================
st.set_page_config(page_title="LLM Assistant V1 (Contextual Engineering)", page_icon="🤖", layout="wide")
st.title("🤖 LLM Assistant V1 — Contextual Engineering")

with st.sidebar:
    st.subheader("Diagnostics")
    # show which keys are present (without exposing values)
    def status_dot(ok: bool): return "🟢" if ok else "🔴"
    st.write(f"{status_dot(bool(OPENROUTER_API_KEY))} OpenRouter")
    st.write(f"{status_dot(bool(GOOGLE_API_KEY and GOOGLE_CSE_ID))} Google CSE")
    st.write(f"{status_dot(bool(WOLFRAM_APP_ID))} WolframAlpha")
    st.write(f"{status_dot(bool(OPENWEATHER_API_KEY))} OpenWeather")
    st.write(f"{status_dot(bool(NEWS_API_KEY))} NewsAPI")

    st.divider()
    st.markdown("### 🔎 Google CSE Self-Test")
    test_query = st.text_input("Test query", value="OpenRouter AI")
    if st.button("Run Google CSE Test"):
        with st.spinner("Testing Google CSE…"):
            results = google_cse_search(test_query, num=5)
        st.markdown("**Results:**")
        for r in results:
            st.write("- ", r)

    st.divider()
    st.caption("Keys are read from Streamlit **Secrets**. Both flat and `[api_keys]` structures are supported.")

# Main input
user_q = st.text_area("Ask me anything:", height=120, placeholder="e.g., What's the weather in Tokyo tomorrow? Or: Evaluate 2^10 + 35.")

# Submit
colA, colB = st.columns([1, 1])
with colA:
    run_btn = st.button("Submit", type="primary")
with colB:
    clear_btn = st.button("Clear")

if clear_btn:
    st.session_state.clear()
    st.rerun()

if run_btn and user_q.strip():
    with st.spinner("Thinking with references…"):
        refs = build_context_snippet(user_q)
        refs_text = render_refs(refs)

        composed_user_prompt = f"""User Question:
{user_q}

External references (use as supportive context only):
{refs_text}

Instruction:
- Provide a concise, confident answer first.
- Then briefly cite which references influenced the answer (if any).
- If references disagree, note the uncertainty."""
        answer = ask_openrouter(SYSTEM_PROMPT, composed_user_prompt)

    st.subheader("🤖 Assistant (LLM-native answer)")
    st.write(answer or "No response.")

    st.subheader("📡 External References Used")
    if not refs:
        st.write("No external references were fetched for this query.")
    else:
        if "wolfram" in refs: st.write("**Wolfram:** ", refs["wolfram"])
        if "weather" in refs: st.write("**Weather:** ", refs["weather"])
        if "news"    in refs: st.write("**News:**", *([f"- {n}" for n in refs["news"]][:5]) if isinstance(refs["news"], list) else refs["news"])
        if "google"  in refs:
            st.write("**Google Search (top):**")
            if isinstance(refs["google"], list):
                for item in refs["google"][:5]:
                    st.write("-", item)
            else:
                st.write(refs["google"])
