from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import threading
import speech_recognition as sr
import pyttsx3
import pywhatkit
import datetime
import wikipedia
import pyjokes
import requests
import os
import re
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Logging Setup
if not os.path.exists('logs'):
    os.makedirs('logs')

log_handler = RotatingFileHandler('logs/app.log', maxBytes=1000000, backupCount=3)
log_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] - %(message)s')
log_handler.setFormatter(log_formatter)
log_handler.setLevel(logging.INFO)
app.logger.addHandler(log_handler)
app.logger.setLevel(logging.INFO)

# Voice Setup
engine = pyttsx3.init()
voices = engine.getProperty('voices')
engine.setProperty('voice', voices[1].id)
listener = sr.Recognizer()

def engine_talk(text):
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        app.logger.error(f"TTS Error: {str(e)}")

def weather(city):
    api_key = os.getenv("WEATHER_API_KEY")
    base_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {"appid": api_key, "q": city, "units": "imperial"}
    try:
        response = requests.get(base_url, params=params)
        data = response.json()
        if data["cod"] != "404":
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"]
            return f"{temp}°F with {desc}"
        else:
            return "City not found"
    except Exception as e:
        app.logger.error(f"Weather error: {str(e)}")
        return "Weather service unavailable"

def ask_groq(prompt):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "Groq API key not set."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "messages": [
            {"role": "system", "content": "You are a helpful voice assistant."},
            {"role": "user", "content": prompt}
        ],
        "model": "mixtral-8x7b-32768"
    }

    try:
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return "Groq API error."
    except Exception as e:
        app.logger.error(f"Groq API exception: {str(e)}")
        return "Failed to connect to Groq."

def search_serpapi(query):
    api_key = os.getenv("SERPAPI_KEY")
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": api_key,
        "engine": "google",
        "num": 3
    }
    try:
        res = requests.get(url, params=params)
        data = res.json()

        answer = (
            data.get("answer_box", {}).get("answer") or
            data.get("answer_box", {}).get("snippet") or
            data.get("answer_box", {}).get("highlighted_words", [None])[0] or
            data.get("knowledge_graph", {}).get("description") or
            (data.get("related_questions", [{}])[0].get("snippet") if data.get("related_questions") else None) or
            data.get("organic_results", [{}])[0].get("snippet") or
            "No good result found"
        )
        return answer
    except Exception as e:
        app.logger.error(f"SERP API error: {e}")
        return "Error getting result from search API"

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    command = request.json.get('command', '').lower()
    response = {"output": "", "success": False}
    app.logger.info(f"Received: {command}")

    if not command:
        response["output"] = "No command received"
        return jsonify(response)

    try:
        if 'play' in command:
            song = command.replace('play', '').strip()
            threading.Thread(target=pywhatkit.playonyt, args=(song,)).start()
            response.update({"output": f"Playing {song}", "success": True})
            engine_talk(f"Playing {song}")

        elif 'time' in command:
            time = datetime.datetime.now().strftime('%I:%M %p')
            response.update({"output": f"The current time is {time}", "success": True})
            engine_talk(f"The current time is {time}")

        elif 'joke' in command:
            joke = pyjokes.get_joke()
            response.update({"output": joke, "success": True})
            engine_talk(joke)

        elif any(word in command for word in ['weather', 'temperature', 'climate']):
            match = re.search(r'(?:in|at|for)\s+([\w\s]+)', command)
            city = match.group(1).strip().title() if match else ''
            if not city:
                response.update({"output": "Please specify a city", "success": False})
            else:
                weather_info = weather(city)
                response.update({"output": f"Weather in {city}: {weather_info}", "success": True})
                engine_talk(f"Weather in {city}: {weather_info}")

        elif 'ask groq' in command:
            prompt = command.replace('ask groq', '').strip()
            groq_result = ask_groq(prompt)
            response.update({"output": groq_result, "success": True})
            engine_talk(groq_result)

        elif 'who is' in command or 'president' in command or 'prime minister' in command:
            name = command.replace('who is', '').replace('what is', '').strip()
            try:
                results = wikipedia.search(name)
                if not results:
                    raise Exception("No Wikipedia match")
                info = wikipedia.summary(results[0], sentences=2)
                response.update({"output": info, "success": True})
                engine_talk(info)
            except:
                serp_result = search_serpapi(command)
                response.update({"output": serp_result, "success": True})
                engine_talk(serp_result)

        elif any(word in command for word in ['score', 'football', 'match', 'live score']):
            serp_result = search_serpapi(command)
            response.update({"output": f"Live update: {serp_result}", "success": True})
            engine_talk(serp_result)

        elif 'news' in command:
            serp_result = search_serpapi("latest news headlines")
            response.update({"output": serp_result, "success": True})
            engine_talk(serp_result)

        elif 'search' in command or 'google' in command:
            query = command.replace('search', '').replace('google', '').strip()
            result = search_serpapi(query)
            response.update({"output": f"Search Result: {result}", "success": True})
            engine_talk(result)

        elif 'remind' in command or 'alarm' in command:
            match = re.search(r'in (\d+)\s*(second|seconds|minute|minutes)', command)
            if match:
                num = int(match.group(1))
                unit = match.group(2)
                seconds = num * 60 if 'minute' in unit else num
                threading.Timer(seconds, lambda: engine_talk("⏰ Alarm! Time's up!")).start()
                response.update({"output": f"Reminder set for {num} {unit}.", "success": True})
            else:
                response.update({"output": "Could not understand time for reminder.", "success": False})

        elif 'restaurant' in command or 'near me' in command:
            result = search_serpapi("restaurants near me")
            response.update({"output": result, "success": True})
            engine_talk(result)

        elif 'stop' in command or 'exit' in command:
            response.update({"output": "Goodbye!", "success": True})
            engine_talk("Goodbye")

        else:
            fallback = search_serpapi(command)
            response.update({"output": fallback, "success": True})
            engine_talk(fallback)

    except Exception as e:
        response.update({"output": f"Error: {str(e)}", "success": False})
        app.logger.error(f"Processing error: {str(e)}")

    return jsonify(response)

if __name__ == '__main__':
    app.logger.info("Server started.")
    print("Visit http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
