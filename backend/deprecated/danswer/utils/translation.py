"""RETIRED. Replaced by heal/language/. Kept for reference only.

The service addresses have been redacted; they now come from
TRANSLATION_EN_URL / TRANSLATION_LUG_URL. See docs/deprecated/MOVED.md.
"""
from random import choice
import time
import requests



def translate_to_english(text: str) -> str:
    url = "http://<TRANSLATION_EN_HOST_REDACTED>/translate"
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
    response = requests.post("http://<TRANSLATION_LUG_HOST_REDACTED>/generate",
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
