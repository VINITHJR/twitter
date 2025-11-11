import os
import random
from datetime import datetime
import requests
import streamlit as st

# Optional import: only used if you enable tweet posting
try:
    import tweepy
    TWEET_AVAILABLE = True
except Exception:
    TWEET_AVAILABLE = False


# ------------------------------
# Secrets (never hardcode keys!)
# Set these in Streamlit secrets
# ------------------------------
WEATHER_API_KEY = st.secrets.get("WEATHER_API_KEY", "f4ed27622e29484a8c342846251210")
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "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")

TWITTER_API_KEY = st.secrets.get("TWITTER_API_KEY", "OMQqc5K4ilbWz3Us9SKvg8Yta")
TWITTER_API_KEY_SECRET = st.secrets.get("TWITTER_API_KEY_SECRET", "eXoOOSk2eaJ0NfwZ6cNhORRFbIaKPgAavyU7KzO9OyjH5cohwa")
TWITTER_ACCESS_TOKEN = st.secrets.get("TWITTER_ACCESS_TOKEN", "1845850146107703297-m4NSBzgPdjDC48XFqAyGznHoHJK5Zj")
TWITTER_ACCESS_TOKEN_SECRET = st.secrets.get("TWITTER_ACCESS_TOKEN_SECRET", "k88a9zqXXvoS41k5Nus5gDbCiHK2tshWHYQ0MuE1g9z1W")

# ------------------------------
# Config / constants
# ------------------------------
CITIES = ["Chennai", "Delhi", "Bengaluru", "Mumbai", "Kolkata", "Hyderabad"]


# ------------------------------
# Helper functions
# ------------------------------
def get_detailed_weather(city: str):
    """Fetch detailed weather + air quality data for a city using WeatherAPI."""
    url = f"http://api.weatherapi.com/v1/current.json"
    params = {
        "key": WEATHER_API_KEY,
        "q": f"{city},India",
        "aqi": "yes",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    weather = {
        "city": data["location"]["name"],
        "region": data["location"]["region"],
        "country": data["location"]["country"],
        "local_time": data["location"]["localtime"],
        "temp_c": data["current"]["temp_c"],
        "feels_like_c": data["current"]["feelslike_c"],
        "condition": data["current"]["condition"]["text"],
        "wind_kph": data["current"]["wind_kph"],
        "humidity": data["current"]["humidity"],
        "uv": data["current"]["uv"],
        # WeatherAPI AQI fields sometimes missing—use dict.get with defaults
        "aqi_us": data["current"].get("air_quality", {}).get("us-epa-index", None),
        "pm2_5": data["current"].get("air_quality", {}).get("pm2_5", None),
        "pm10": data["current"].get("air_quality", {}).get("pm10", None),
    }
    return weather


def generate_story_tweet_with_groq(weather_data: dict) -> str:
    """Use Groq Chat Completions API to produce a short narrative tweet."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""
Write a descriptive, story-like weather update for {weather_data['city']}, India.

Create a single, evocative paragraph within 280 characters (Twitter limit).
- Set the scene from the condition: '{weather_data['condition']}'.
- Mention the temperature ({weather_data['temp_c']}°C) and feels-like ({weather_data['feels_like_c']}°C).
- Subtly mention air quality (AQI {weather_data['aqi_us']}).
- End with 3-4 relevant hashtags.

DATA:
City: {weather_data['city']}
Temp: {weather_data['temp_c']}°C
Feels Like: {weather_data['feels_like_c']}°C
Condition: {weather_data['condition']}
AQI(US): {weather_data['aqi_us']}
"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 200,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    result = resp.json()
    text = result["choices"][0]["message"]["content"].strip()

    # Ensure 280 chars max (hard safety)
    if len(text) > 280:
        text = text[:277].rstrip() + "..."
    return text


def generate_image(prompt: str, filename: str = "weather_image.png"):
    """Get an AI image from Pollinations (simple GET to prompt URL)."""
    # You can swap to another service if needed; this is simple/no auth.
    url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with open(filename, "wb") as f:
        f.write(r.content)
    return filename


def twitter_auth():
    """Create both Tweepy v2 Client and v1.1 API for media upload."""
    if not TWEET_AVAILABLE:
        st.error("tweepy is not installed. Add 'tweepy' to requirements.txt.")
        return None, None

    if not (TWITTER_API_KEY and TWITTER_API_KEY_SECRET and TWITTER_ACCESS_TOKEN and TWITTER_ACCESS_TOKEN_SECRET):
        st.error("Twitter API secrets are missing. Add them in Streamlit secrets.")
        return None, None

    try:
        client = tweepy.Client(
            consumer_key=TWITTER_API_KEY,
            consumer_secret=TWITTER_API_KEY_SECRET,
            access_token=TWITTER_ACCESS_TOKEN,
            access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
        )
        auth_v1 = tweepy.OAuth1UserHandler(
            TWITTER_API_KEY,
            TWITTER_API_KEY_SECRET,
            TWITTER_ACCESS_TOKEN,
            TWITTER_ACCESS_TOKEN_SECRET,
        )
        api_v1 = tweepy.API(auth_v1)
        return client, api_v1
    except Exception as e:
        st.error(f"Twitter authentication failed: {e}")
        return None, None


# ------------------------------
# Streamlit UI
# ------------------------------
st.set_page_config(page_title="Weather Story Tweeter", page_icon="🌤", layout="centered")
st.title("🌤 Weather Story Tweeter")

with st.sidebar:
    st.header("Settings")
    default_city = random.choice(CITIES)
    city = st.selectbox("Choose a city", CITIES, index=CITIES.index(default_city))
    generate_btn = st.button("Fetch Weather & Generate Story", type="primary")
    st.divider()
    post_to_twitter = st.checkbox("Enable Tweet Posting (requires X/Twitter API keys)")
    st.caption("Tip: Leave this off to preview first.")

# Validate required secrets for the core functions
if not WEATHER_API_KEY:
    st.warning("Set WEATHER_API_KEY in your Streamlit secrets to fetch live data.")

if not GROQ_API_KEY:
    st.warning("Set GROQ_API_KEY in your Streamlit secrets to generate the story text.")

placeholder = st.empty()

if generate_btn:
    if not (WEATHER_API_KEY and GROQ_API_KEY):
        st.error("Missing required API keys. Add WEATHER_API_KEY and GROQ_API_KEY in secrets.")
    else:
        with st.spinner("Fetching weather..."):
            try:
                current = get_detailed_weather(city)
            except Exception as e:
                st.error(f"Failed to fetch weather: {e}")
                st.stop()

        st.success(f"Weather fetched for {current['city']} ({current['local_time']})")

        # Show weather data
        st.subheader("Current Conditions")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Temperature (°C)", current["temp_c"], help="Actual temperature")
            st.metric("Feels Like (°C)", current["feels_like_c"])
            st.metric("Humidity (%)", current["humidity"])
        with col2:
            st.metric("Wind (kph)", current["wind_kph"])
            st.metric("UV Index", current["uv"])
            aqi = current["aqi_us"] if current["aqi_us"] is not None else "N/A"
            st.metric("AQI (US-EPA Index)", aqi)

        st.subheader("Story-like Tweet")
        with st.spinner("Writing with Groq..."):
            try:
                tweet_text = generate_story_tweet_with_groq(current)
            except Exception as e:
                st.error(f"Failed to generate story: {e}")
                st.stop()

        st.text_area("Generated Tweet (<= 280 chars)", tweet_text, height=120)

        st.subheader("Image")
        image_prompt = f"{current['condition']} weather in {city}, India, realistic photo"
        with st.spinner("Generating image..."):
            try:
                image_path = generate_image(image_prompt)
                st.image(image_path, caption=image_prompt, use_container_width=True)
            except Exception as e:
                st.error(f"Failed to generate image: {e}")
                image_path = None

        # Tweet posting
        if post_to_twitter:
            st.subheader("Post to X (Twitter)")
            if not TWEET_AVAILABLE:
                st.error("tweepy not installed. Add 'tweepy' to requirements.txt.")
            else:
                client, api_v1 = twitter_auth()
                if client and api_v1:
                    if st.button("Post Tweet now 🚀"):
                        try:
                            media_id = None
                            if image_path:
                                with st.spinner("Uploading media..."):
                                    media = api_v1.media_upload(image_path)
                                    media_id = media.media_id

                            # Enforce 280 characters (final safety)
                            text = tweet_text if len(tweet_text) <= 280 else (tweet_text[:277] + "...")

                            with st.spinner("Posting tweet..."):
                                if media_id:
                                    response = client.create_tweet(text=text, media_ids=[media_id])
                                else:
                                    response = client.create_tweet(text=text)

                            tweet_id = response.data["id"]
                            # Get username
                            me = client.get_me()
                            username = me.data["username"]
                            url = f"https://twitter.com/{username}/status/{tweet_id}"
                            st.success(f"Tweet posted successfully! 👉 {url}")
                            st.write(url)
                        except Exception as e:
                            st.error(f"Tweet failed: {e}")
                else:
                    st.info("Provide valid Twitter API keys in secrets to enable posting.")



