import azure.functions as func
import logging
import os
import json
import requests
# from ai_integration import generate_gemini_response, generate_grok_response
from ai_model import handle_lead_message

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.route(route="whatsappbot1")
def whatsappbot1(req: func.HttpRequest) -> func.HttpResponse:
    """
    Main Azure Function entry point for WhatsApp webhook.
    Handles both GET (verification) and POST (message) requests.
    """
    logging.info('Python HTTP trigger function processed a request')
    logging.info(f"req.method: {req.method}")

    if req.method == 'POST':
        return handle_message(req)
    else:
        return verify(req)
    
def verify(req):
    """
    Handles WhatsApp webhook verification (GET requests).
    This is called when you first set up the webhook in Meta Developer Console.
    """
    logging.info("verify - Start")

    verify_token = os.environ["VERIFY_TOKEN"]
    if verify_token:
        logging.info(f"verify_token: {verify_token}")
    else:
        logging.info("VERIFY_TOKEN Empty")

    if req.params:
        logging.info(req.params)

    # Parse params from the webhook verification request
    mode = req.params.get("hub.mode")
    token = req.params.get("hub.verify_token")
    challenge = req.params.get("hub.challenge")
    logging.info(f"mode: {mode}, token: {token}, challenge: {challenge}")

    # Check if a token and mode were sent
    if mode and token:
        # Check the mode and token sent are correct
        if mode == "subscribe" and token == verify_token:
            # Respond with 200 OK and challenge token from the request
            logging.info("WEBHOOK_VERIFIED")
            return func.HttpResponse(challenge, status_code=200)
        else:
            # Responds with '403 Forbidden' if verify tokens do not match
            logging.info("VERIFICATION_FAILED")
            return func.HttpResponse("Verification failed", status_code=403)
    else:
        # Responds with '400 Bad Request' if verify tokens do not match
        logging.info("MISSING_PARAMETER")
        return func.HttpResponse("Missing parameters", status_code=400)

def handle_message(req):
    """
    Handles incoming WhatsApp messages (POST requests).
    Processes the message and sends appropriate responses.
    """
    logging.info("handle_message - Start")

    body = req.get_json()
    logging.info(f"request body: {body}")

    # Check if it's a WhatsApp status update (ignore these)
    if (
        body.get("entry", [{}])[0]
        .get("changes", [{}])[0]
        .get("value", {})
        .get("statuses")
    ):
        logging.info("Received a WhatsApp status update.")
        return func.HttpResponse("OK", status_code=200)

    try:
        if is_valid_whatsapp_message(body):
            process_whatsapp_message(body)
            return func.HttpResponse("OK", status_code=200)
        else:
            # if the request is not a WhatsApp API event, return an error
            logging.error("Not a WhatsApp API event")
            return func.HttpResponse("Not a WhatsApp API event", status_code=404)
    except json.JSONDecodeError:
        logging.error("Failed to decode JSON")
        return func.HttpResponse("Invalid JSON provided", status_code=400)

def is_valid_whatsapp_message(body):
    """
    Check if the incoming webhook event has a valid WhatsApp message structure.
    """
    logging.info("is_valid_whatsapp_message - Start")
    return (
        body.get("object")
        and body.get("entry")
        and body["entry"][0].get("changes")
        and body["entry"][0]["changes"][0].get("value")
        and body["entry"][0]["changes"][0]["value"].get("messages")
        and body["entry"][0]["changes"][0]["value"]["messages"][0]
    )

def process_whatsapp_message(body):
    """
    Processes the WhatsApp message and sends appropriate response.
    For text messages: converts to uppercase and sends back.
    For other message types: sends a help message.
    """
    logging.info("process_whatsapp_message - Start")

    # Extract sender information
    wa_id = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    name = body["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"]
    logging.info(f"wa_id: {wa_id}")
    logging.info(f"name: {name}")
    logging.info(f"Saved wa_id: {os.environ['RECIPIENT_WAID']}") # Debugging line

    # Safeguard against unauthorized users (optional - remove if you want to allow all users)
    if not (wa_id == os.environ["RECIPIENT_WAID"] or wa_id == "5212212122080" or wa_id == "5219512397285"):
        logging.error("Unauthorized user!!!")
        return

    # Extract message content
    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    logging.info(f"message: {message}")

    if "text" in message:
        # Handle text messages - convert to uppercase and echo back
        logging.info(f"Message Type: TEXT")
        message_body = message["text"]["body"]
        logging.info(f"message_body: {message_body}")
        
        # Generate response using Gemini API and Grok API
        # gemini_message = generate_gemini_response(message_body)
        # grok_message = generate_grok_response(message_body)
        # final_message = f"Gemini Response:\n{gemini_message}\n\nGrok Response:\n{grok_message}"

        # Handle lead message with AI model
        final_message = handle_lead_message(wa_id, message_body)

        # Send the final message back
        data = get_text_message_input(wa_id, final_message)
        send_message(data)
        
    else:
        # Handle non-text messages with a help message
        logging.info(f"Message Type: NON-TEXT")
        help_text = "Hi! I can only convert text messages to UPPERCASE. Please send me a text message and I'll reply with it in capital letters!"
        data = get_text_message_input(wa_id, help_text)
        send_message(data)

def normalize_mexican_number(phone_number: str) -> str:
    """
    Normaliza un número mexicano en formato internacional para que sea aceptado por la API de WhatsApp.
    Si el número comienza con '521' (México + celular), elimina el '1' extra.

    Args:
        phone_number: Número de teléfono en formato internacional (ej. '5212345678901')

    Returns:
        Número de teléfono normalizado (ej. '522345678901')
    """
    if phone_number.startswith("521") and len(phone_number) >= 12:
        return "52" + phone_number[3:]
    return phone_number

def get_text_message_input(recipient, text):
    """
    Creates the JSON payload for sending a text message via WhatsApp API.
    
    Args:
        recipient: WhatsApp ID of the recipient
        text: Text message to send
        
    Returns:
        JSON string formatted for WhatsApp API
    """
    normalized_recipient = normalize_mexican_number(recipient)
    return json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalized_recipient,
            "type": "text",
            "text": {
                "preview_url": False, 
                "body": text
            },
        }
    )

def send_message(data):
    """
    Sends a message to WhatsApp API.
    
    Args:
        data: JSON payload for the message
        
    Returns:
        HTTP response from the API
    """
    logging.info("send_message - Start")

    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {os.environ['ACCESS_TOKEN']}",
    }

    url = f"https://graph.facebook.com/{os.environ['VERSION']}/{os.environ['PHONE_NUMBER_ID']}/messages"
    return send_post_request_to_graph_facebook(url, data, headers)


def log_http_response(response):
    """
    Logs HTTP response details for debugging.
    """
    logging.info(f"Status: {response.status_code}")
    logging.info(f"Content-type: {response.headers.get('content-type')}")
    logging.info(f"Body: {response.text}")


def send_post_request_to_graph_facebook(url, data, headers):
    """
    Sends a POST request to Facebook Graph API with proper error handling.
    
    Args:
        url: API endpoint URL
        data: JSON payload
        headers: HTTP headers
        
    Returns:
        HTTP response or error response
    """
    logging.info(f"send_post_request_to_graph_facebook - Start, url: {url}")

    try:
        response = requests.post(url, data=data, headers=headers, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad status codes
    except requests.Timeout:
        logging.error("Timeout occurred while sending message")
        return func.HttpResponse("Request timed out", status_code=408)
    except requests.RequestException as e:
        logging.error(f"Request failed due to: {e}")
        return func.HttpResponse("Failed to send message", status_code=500)
    else:
        # Process the response as normal
        log_http_response(response)
        return response