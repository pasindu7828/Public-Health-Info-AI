# backend/chat_agent/engine.py
import random

def get_chat_response(user_query: str) -> str:
    """
    Chat Agent with multiple dummy responses per topic.
    """
    query = user_query.lower()

    responses = {
        "dengue": [
            "Dengue symptoms include high fever, headache, joint pain, rash, and nausea.",
            "If you have dengue, watch for fever, pain behind the eyes, and skin rash.",
            "If you have dengue, watch for fever, pain behind the eyes."
        ],
        "covid": [
            "COVID-19 symptoms include fever, cough, fatigue, and loss of taste or smell.",
            "Remember: COVID-19 can cause shortness of breath, fever, and cough."
        ],
        "flu": [
            "Flu prevention tips: get vaccinated, wash hands regularly, avoid close contact with sick people.",
            "To prevent flu: stay home if sick, cover your mouth when sneezing, and keep hands clean."
        ],
        "hello": [
            "Hello! I am your Public Health Chat Agent. How can I help you today?",
            "Hi there! Ask me anything about public health topics."
        ]
    }

    for key in responses:
        if key in query:
            return random.choice(responses[key])

    return "Sorry, I don't have information on that yet. Please try another public health topic."
