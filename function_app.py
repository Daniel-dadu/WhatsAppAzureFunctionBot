"""
Chatbot automatizado para calificación de leads de maquinaria ligera
Integra WhatsApp + Azure OpenAI GPT-4.1-mini + HubSpot CRM
Azure Function para procesar webhooks de WhatsApp
"""

import azure.functions as func
import logging
import os
import json
from inventory import InventoryManager
from hubspot import HubSpotManager
from llm import LLMManager
from conversation import ConversationManager
from whatsapp_bot import WhatsAppBot

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
    
@app.route(route="login")
def login(req: func.HttpRequest) -> func.HttpResponse:
    """
    Handles login request.
    """
    logging.info("login - Start")
    body = req.get_json()
    if body.get("username") == "admin" and body.get("password") == "admin":
        return func.HttpResponse("Login successful", status_code=200)
    else:
        return func.HttpResponse("Login failed", status_code=401)

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
    
# Variables globales para los managers
inventory_manager = None
hubspot_manager = None
llm_manager = None
conversation_manager = None
whatsapp_bot = None

def initialize_managers():
    """Inicializa los managers globales si no están inicializados"""
    global inventory_manager, hubspot_manager, llm_manager, conversation_manager, whatsapp_bot
    
    if conversation_manager is None:
        try:
            inventory_manager = InventoryManager()
            hubspot_manager = HubSpotManager(os.environ["HUBSPOT_TOKEN"])
            llm_manager = LLMManager(os.environ["FOUNDRY_API_KEY"])
            
            conversation_manager = ConversationManager(
                inventory_manager,
                hubspot_manager, 
                llm_manager
            )
            
            whatsapp_bot = WhatsAppBot(conversation_manager)
            logging.info("Managers inicializados correctamente")
            
        except Exception as e:
            logging.error(f"Error inicializando managers: {e}")
            raise

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
    Uses the conversation manager and WhatsApp bot for intelligent responses.
    """
    logging.info("process_whatsapp_message - Start")

    # Extract sender information
    wa_id = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    name = body["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"]
    logging.info(f"wa_id: {wa_id}")
    logging.info(f"name: {name}")
    logging.info(f"Saved wa_id: {os.environ['RECIPIENT_WAID']}") # Debugging line

    # Initialize managers if needed
    initialize_managers()

    # Safeguard against unauthorized users
    if not whatsapp_bot.is_authorized_user(wa_id):
        logging.error("Unauthorized user!!!")
        return

    # Extract message content
    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    logging.info(f"message: {message}")

    if "text" in message:
        # Handle text messages with AI conversation manager
        logging.info(f"Message Type: TEXT")
        message_body = message["text"]["body"]
        logging.info(f"message_body: {message_body}")
        
        # Process message with conversation manager
        try:
            response = whatsapp_bot.process_message(wa_id, message_body)
            whatsapp_bot.send_message(wa_id, response)
        except Exception as e:
            logging.error(f"Error processing message: {e}")
            error_message = "Disculpa, hubo un problema técnico. ¿Podrías repetir tu mensaje?"
            whatsapp_bot.send_message(wa_id, error_message)
        
    else:
        # Handle non-text messages with a help message
        logging.info(f"Message Type: NON-TEXT")
        help_text = "¡Hola! Solo puedo procesar mensajes de texto. Por favor, envíame un mensaje de texto y te responderé con información sobre maquinaria."
        whatsapp_bot.send_message(wa_id, help_text)