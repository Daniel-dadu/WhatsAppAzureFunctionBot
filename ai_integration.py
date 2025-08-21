from openai import OpenAI
from openai import AzureOpenAI
import logging
import os
import requests

# Cliente Azure OpenAI
client = AzureOpenAI(
    api_key=os.environ["FOUNDRY_API_KEY"],
    api_version="2024-10-21",
    azure_endpoint=os.environ["FOUNDRY_ENDPOINT"],
)

GPT_MODEL = "gpt-4.1-mini"

def generate_gpt_response(prompt):
    """
    Generates a response using the GPT model.
    """
    logging.info("generate_gpt_response - Start")
    
    # Mandando el prompt al modelo
    try:
        response = client.beta.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Eres un asistente de ventas de maquinaria ligera que solo proporciona respuestas cortas, pero responde de manera completa y precisa. Tu objetivo es ayudar a los clientes a entender mejor los productos y servicios que ofrecemos.",
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        logging.info("generate_gpt_response - End")
        return response.choices[0].message.content if response.choices else None
    except Exception as e:
        logging.error(f"Error en generate_gpt_response: {e}")

def generate_gemini_response(prompt):
    """
    Generates a response using the Gemini API.
    """
    logging.info("generate_gemini_response - Start")
    
    # Ensure the API key is set
    if "GEMINI_API_KEY" not in os.environ:
        logging.error("GEMINI_API_KEY environment variable is not set.")
        return None

    # Initialize the OpenAI client with the Gemini API key
    client = OpenAI(
        api_key=os.environ["GEMINI_API_KEY"],
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )

    response = client.chat.completions.create(
        model="gemini-2.5-flash-lite",
        reasoning_effort="low",
        messages=[
            {
                "role": "system",
                "content": "Eres un asistente de ventas de maquinaria ligera que solo proporciona respuestas cortas, pero responde de manera completa y precisa. Tu objetivo es ayudar a los clientes a entender mejor los productos y servicios que ofrecemos.",
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    logging.info("generate_gemini_response - End")
    return response.choices[0].message.content if response.choices else None

def generate_grok_response(prompt):
    """
    Generates a response using the Grok API.
    """
    logging.info("generate_grok_response - Start")
    
    # Ensure the API key is set
    if "FOUNDRY_API_KEY" not in os.environ:
        logging.error("FOUNDRY_API_KEY environment variable is not set.")
        return None
    
    if "FOUNDRY_ENDPOINT" not in os.environ:
        logging.error("FOUNDRY_ENDPOINT environment variable is not set.")
        return None
    
    api_key = os.environ["FOUNDRY_API_KEY"]
    endpoint = os.environ["FOUNDRY_ENDPOINT"] + "models/chat/completions?api-version=2024-05-01-preview"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "messages": [
            {
                "role": "system",
                "content": "Eres un asistente de ventas de maquinaria ligera que solo proporciona respuestas cortas, pero responde de manera completa y precisa. Tu objetivo es ayudar a los clientes a entender mejor los productos y servicios que ofrecemos.",
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_completion_tokens": 16000,
        "temperature": 1,
        "top_p": 1,
        "model": "grok-3-mini"
    }

    response = requests.post(endpoint, headers=headers, json=payload)

    if response.status_code == 200:
        resp_json = response.json()
        logging.info("generate_grok_response - End")
        logging.info(f"Response from grok: {resp_json}")

        # Extrae el texto correctamente: primero intenta choices[0].message.content,
        # luego cae a choices[0].get('text') para compatibilidad con formatos previos.
        try:
            choice = resp_json.get("choices", [None])[0] or {}
            # nuevo formato: {'message': {'content': '...'}}
            content = None
            if isinstance(choice, dict):
                content = choice.get("message", {}).get("content")
                if not content:
                    # fallback histórico
                    content = choice.get("text")
            return content.strip() if content else None
        except Exception as e:
            logging.error(f"generate_grok_response - parse error: {e}")
            return None
    else:
        logging.error(f"generate_grok_response - Error: {response.status_code} {response.text}")
        return None