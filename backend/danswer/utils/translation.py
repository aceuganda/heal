from random import choice
import time
import requests



def translate_to_english(text: str) -> str:
    # logic to translate to english
    return text


def translate_to_luganda(prompt):
    response = requests.post("http://65.108.33.93:5000/generate",
                             json={"prompt": prompt, "stream": True}, stream=True)

    if response.status_code != 200:
        raise Exception(f"Error fetching response: {response.status_code}")

    for chunk in response.iter_content(chunk_size=1024):
        decoded_chunk = chunk.decode("utf-8")
        lines = decoded_chunk.splitlines()
        for line in lines:
            if line.startswith("data: "):
                word = line[6:].strip()
                yield word + " "
                time.sleep(0.09)  
