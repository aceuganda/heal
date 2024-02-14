from random import choice
import time
import requests



def translate_to_english(text: str) -> str:
    url = "http://65.108.33.93:4002/translate"
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
    }
    data = {"prompt": text}

    response = requests.post(url, headers=headers, json=data, stream=True)

    if response.status_code != 200:
        raise Exception(f"Error fetching response: {response.status_code}")

    return response.text


def translate_to_luganda(prompt) -> str:
    response = requests.post("http://65.108.33.93:5000/generate",
                             json={"prompt": prompt, "stream": True}, stream=True)

    if response.status_code != 200:
        raise Exception(f"Error fetching response: {response.status_code}")
    luganda_response = ""
    for chunk in response.iter_content(chunk_size=1024):
        decoded_chunk = chunk.decode("utf-8")
        lines = decoded_chunk.splitlines()
        for line in lines:
            if line.startswith("data: "):
                word = line[6:].strip()
                luganda_response += word + " "
    
    return luganda_response
