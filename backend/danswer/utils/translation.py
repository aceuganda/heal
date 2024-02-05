from random import choice

def translate_to_english(text: str) -> str:
    # logic to translate to english
    return choice(["Hello, how are you?", "This is an English translation.", "Random English text."])

def translate_to_luganda(text: str) -> str:
    # logic to translate to luganda
    return choice(["Oli otya? Genda otya?", "Luganda translation yo!", "Random Luganda text."])
