import os
from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel
from openai import AzureOpenAI
from datetime import datetime
import json
import re
import logging

# Cliente Azure OpenAI
client = AzureOpenAI(
    api_key=os.environ["FOUNDRY_API_KEY"],
    api_version="2024-10-21",
    azure_endpoint=os.environ["FOUNDRY_ENDPOINT"],
)

GPT_MODEL = "gpt-4.1-mini"

# ==== Esquemas de structured output ====
class ExtractedInfo(BaseModel):
    """Información que se puede extraer de cualquier mensaje"""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    company_name: Optional[str] = None
    machine_type: Optional[str] = None
    city: Optional[str] = None
    # Campos específicos por tipo de máquina
    welding_amperage: Optional[str] = None
    welding_electrode: Optional[str] = None
    compressor_volume: Optional[str] = None
    compressor_tools: Optional[str] = None
    lighting_led: Optional[bool] = None
    lgmg_height: Optional[str] = None
    lgmg_activity: Optional[str] = None
    lgmg_location: Optional[str] = None  # interior/exterior
    generator_activity: Optional[str] = None
    generator_capacity: Optional[str] = None
    generator_fuel_receipt: Optional[bool] = None
    breaker_use: Optional[str] = None
    breaker_type: Optional[str] = None  # eléctrico/neumático
    # Campos de cotización
    business_use: Optional[str] = None  # empresa/venta
    is_distributor: Optional[bool] = None

class ConversationState(BaseModel):
    """Estado completo de la conversación"""
    current_stage: Literal[
        "greeting", "name", "machine_type", "machine_details", 
        "quote_info", "distributor_check", "completed"
    ] = "name"  # Cambiado de "greeting" a "name"
    extracted_info: ExtractedInfo = ExtractedInfo()
    conversation_history: list = []
    last_updated: str = ""

# ==== Base de datos ficticia para múltiples conversaciones ====
CONVERSATIONS_DB: Dict[str, ConversationState] = {}

# ==== Configuración de flujo por tipo de máquina ====
MACHINE_QUESTIONS = {
    "soldadora": [
        "¿Qué amperaje requiere o qué electrodo quema?",
    ],
    "compresor": [
        "¿Qué capacidad de volumen de aire requiere o qué herramienta le va a conectar?",
    ],
    "torre de iluminacion": [
        "¿La requiere de Led?",
    ],
    "lgmg": [
        "¿Qué altura de trabajo necesita?",
        "¿Qué actividad va a realizar?",
        "¿Es en exterior, o interior?",
    ],
    "generador": [
        "¿Para qué actividad lo requiere?",
        "¿Qué capacidad en (kvas o kw)?",
    ],
    "rompedor": [
        "¿Para qué lo vas a utilizar?",
        "Lo requiere eléctrico o neumático?",
    ]
}

def get_conversation_state(wa_id: str) -> ConversationState:
    """Obtiene el estado de conversación o crea uno nuevo"""
    if wa_id not in CONVERSATIONS_DB:
        CONVERSATIONS_DB[wa_id] = ConversationState()
        logging.info(f"Nueva conversación creada para wa_id: {wa_id}")
    return CONVERSATIONS_DB[wa_id]

def update_conversation_state(wa_id: str, state: ConversationState):
    """Actualiza el estado de conversación"""
    state.last_updated = datetime.now().isoformat()
    CONVERSATIONS_DB[wa_id] = state
    logging.info(f"Estado actualizado para wa_id: {wa_id} - Etapa: {state.current_stage}")

def analyze_message_with_llm(message: str, current_state: ConversationState) -> ExtractedInfo:
    """Usa el LLM para extraer información del mensaje"""
    logging.info(f"=== ANALIZANDO MENSAJE CON LLM ===")
    logging.info(f"Mensaje: '{message}'")
    logging.info(f"Etapa actual: {current_state.current_stage}")
    
    try:
        logging.info("🔄 Intentando structured output...")
        completion = client.beta.chat.completions.parse(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": """Eres un extractor de información experto para una empresa de maquinaria ligera.
                
                Extrae ÚNICAMENTE la información que está claramente presente en el mensaje del usuario.
                
                Tipos de máquinas que manejamos:
                - soldadora: máquinas de soldar
                - compresor: compresores de aire
                - torre de iluminacion: torres de iluminación
                - lgmg: elevadores y plataformas
                - generador: generadores eléctricos
                - rompedor: rompedores y martillos
                
                Para NOMBRES, busca específicamente estos patrones:
                - "Me llamo [NOMBRE]" → extrae solo el nombre
                - "Soy [NOME]" → extrae solo el nombre  
                - "Mi nombre es [NOMBRE]" → extrae solo el nombre
                - Solo "[NOMBRE]" si es claramente un nombre (no saludos)
                
                Para máquinas: identifica el tipo de máquina mencionada.
                Para teléfonos: números de 10 dígitos.
                Para emails: direcciones de correo válidas.
                
                IMPORTANTE: Para nombres, extrae SOLO el nombre, sin apellidos si no están claramente especificados.
                Si no hay información clara en algún campo, déjalo en null.
                Solo extrae lo que está explícitamente en el mensaje."""},
                {"role": "user", "content": f"Analiza este mensaje y extrae la información disponible: '{message}'"}
            ],
            response_format=ExtractedInfo,
        )
        
        extracted = completion.choices[0].message.parsed
        logging.info(f"✅ Structured output exitoso")
        logging.info(f"Respuesta del LLM: {extracted.model_dump()}")
        logging.info(f"Campo name extraído: '{extracted.name}' (tipo: {type(extracted.name)})")
        return extracted
        
    except Exception as e:
        logging.error(f"❌ Error con structured output: {e}")
        logging.info("🔄 Intentando JSON fallback...")
        return analyze_message_with_json_fallback(message, current_state)

def analyze_message_with_json_fallback(message: str, current_state: ConversationState) -> ExtractedInfo:
    """Método fallback usando JSON tradicional"""
    logging.info("🔄 Usando método fallback con JSON")
    
    try:
        completion = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": """Analiza el mensaje y extrae información en formato JSON.
                
                Busca específicamente:
                - NOMBRES: "Me llamo Juan", "Soy María", "Mi nombre es Carlos", o solo nombres claros
                - Máquinas: soldadora, compresor, torre de iluminacion, lgmg, generador, rompedor
                - Teléfonos y emails
                
                Para nombres: extrae SOLO el nombre, sin apellidos si no están claramente especificados.
                
                Responde SOLO con JSON válido. Ejemplo:
                {"name": "Juan", "machine_type": "soldadora", "phone": null, "email": null, "company_name": null, "city": null, "welding_amperage": null, "welding_electrode": null, "compressor_volume": null, "compressor_tools": null, "lighting_led": null, "lgmg_height": null, "lgmg_activity": null, "lgmg_location": null, "generator_activity": null, "generator_capacity": null, "generator_fuel_receipt": null, "breaker_use": null, "breaker_type": null, "business_use": null, "is_distributor": null}"""},
                {"role": "user", "content": f"Mensaje: '{message}'"}
            ],
            response_format={"type": "json_object"}
        )
        
        json_response = json.loads(completion.choices[0].message.content)
        logging.info(f"✅ JSON fallback exitoso")
        logging.info(f"Respuesta JSON: {json_response}")
        logging.info(f"Campo name en JSON: '{json_response.get('name')}'")
        
        extracted = ExtractedInfo(**json_response)
        logging.info(f"✅ Objeto ExtractedInfo creado: {extracted.model_dump()}")
        return extracted
        
    except Exception as e:
        logging.error(f"❌ Error en JSON fallback: {e}")
        logging.info("🔄 Retornando ExtractedInfo vacío")
        return ExtractedInfo()

def merge_extracted_info(current: ExtractedInfo, new: ExtractedInfo) -> ExtractedInfo:
    """Combina información nueva con la existente"""
    logging.info(f"=== MERGE DE INFORMACIÓN ===")
    logging.info(f"Info actual: {current.model_dump()}")
    logging.info(f"Info nueva: {new.model_dump()}")
    
    merged = current.model_copy()
    changes_made = False
    
    for field, value in new.model_dump().items():
        if value is not None:
            current_value = getattr(merged, field)
            logging.info(f"Campo {field}: actual='{current_value}', nuevo='{value}'")
            
            if current_value is None or current_value == "":
                setattr(merged, field, value)
                logging.info(f"✅ Campo actualizado - {field}: '{current_value}' -> '{value}'")
                changes_made = True
            else:
                logging.info(f"⚠️ Campo {field} ya tiene valor: '{current_value}', no se actualiza")
    
    if not changes_made:
        logging.info("❌ No se realizaron cambios en la información extraída")
    else:
        logging.info(f"✅ Cambios realizados. Info final: {merged.model_dump()}")
    
    return merged

def is_machinery_question(message: str) -> bool:
    """Detecta si el usuario está haciendo una pregunta sobre maquinaria usando el LLM"""
    try:
        system_prompt = """Eres un clasificador experto. Tu tarea es determinar si un mensaje del usuario contiene una pregunta o consulta sobre maquinaria ligera.

        Considera que es una pregunta sobre maquinaria si el usuario está preguntando sobre:
        - Precios, costos, valores, cotizaciones
        - Disponibilidad, stock, inventario
        - Características técnicas, especificaciones, fichas técnicas
        - Marcas, modelos, años, condición (nuevo, usado, reacondicionado)
        - Garantía, servicio, mantenimiento, reparación
        - Entrega, envío, instalación, capacitación
        - Ubicaciones, bodegas, sucursales
        - Ofertas, descuentos, presupuestos

        Responde SOLO con "SI" si es una pregunta sobre maquinaria, o "NO" si no lo es.
        No agregues explicaciones, solo "SI" o "NO"."""

        completion = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"¿Este mensaje contiene una pregunta sobre maquinaria? '{message}'"}
            ],
            max_tokens=10,
            temperature=0.1
        )
        
        response = completion.choices[0].message.content.strip().upper()
        is_machinery = response == "SI"
        
        logging.info(f"LLM determinó que el mensaje '{message}' {'SÍ' if is_machinery else 'NO'} es pregunta sobre maquinaria")
        logging.info(f"Respuesta del LLM: {response}")
        return is_machinery
        
    except Exception as e:
        logging.error(f"Error usando LLM para determinar si es pregunta sobre maquinaria: {e}")
        # Fallback simple: si contiene signo de interrogación, probablemente es una pregunta
        return "?" in message

def generate_machinery_response(message: str, current_state: ConversationState) -> str:
    """Genera respuestas específicas sobre maquinaria usando el LLM"""
    try:
        system_prompt = """Eres un asistente virtual experto en maquinaria ligera. El usuario está haciendo preguntas 
        sobre precios, disponibilidad, características técnicas, ubicaciones, etc.
        
        Responde de manera profesional y útil, pero NO des precios exactos. En su lugar:
        - Para precios: menciona que varían según especificaciones y que puedes enviar cotización
        - Para disponibilidad: menciona que tienes amplio inventario y puedes verificar stock específico
        - Para características: proporciona información técnica general
        - Para ubicaciones: menciona que tienes bodegas en diferentes ciudades
        - Para entrega: menciona que ofreces entrega e instalación
        
        Mantén las respuestas enfocadas en maquinaria ligera y sé útil pero no demasiado específico con precios.
        Siempre ofrece generar una cotización personalizada.
        
        Después de responder la pregunta, si es apropiado, continúa con la siguiente pregunta del flujo conversacional."""
        
        conversation_context = f"""
        Información del usuario: {current_state.extracted_info.model_dump()}
        Etapa de conversación: {current_state.current_stage}
        """
        
        completion = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt + "\n\n" + conversation_context},
                {"role": "user", "content": f"Responde a esta pregunta sobre maquinaria: '{message}'"}
            ],
            max_tokens=300,
            temperature=0.7
        )
        
        response = completion.choices[0].message.content
        logging.info(f"Respuesta sobre maquinaria generada: {response}")
        
        # Después de responder la pregunta sobre maquinaria, verificar si debemos continuar con el flujo
        if current_state.current_stage != "completed":
            try:
                next_stage, next_question = determine_next_stage(current_state)
                if next_stage != current_state.current_stage:
                    # Agregar la siguiente pregunta al final de la respuesta
                    response += f"\n\n{next_question}"
                    current_state.current_stage = next_stage
                    logging.info(f"Continuando flujo después de pregunta sobre maquinaria: {next_stage}")
            except Exception as e:
                logging.error(f"Error continuando flujo después de pregunta sobre maquinaria: {e}")
        
        return response
        
    except Exception as e:
        logging.error(f"Error generando respuesta sobre maquinaria: {e}")
        return "Te puedo ayudar con información sobre maquinaria. ¿Te gustaría que te envíe una cotización personalizada?"

def is_user_response_to_bot(message: str, current_state: ConversationState) -> tuple[bool, bool]:
    """Detecta si el usuario está respondiendo a las preguntas del bot y/o haciendo una nueva consulta usando el LLM
    
    Returns:
        tuple: (is_response, has_additional_question)
        - is_response: True si está respondiendo a la pregunta del bot
        - has_additional_question: True si también está haciendo una consulta adicional
    """
    try:
        # Obtener el último mensaje del bot para contexto
        last_bot_message = ""
        if current_state.conversation_history and current_state.conversation_history[-1]['sender'] == 'bot':
            last_bot_message = current_state.conversation_history[-1]['message']
        
        system_prompt = """Eres un clasificador experto. Tu tarea es analizar un mensaje del usuario y determinar dos cosas:

        1. ¿Está respondiendo a la pregunta del bot?
        2. ¿También está haciendo una consulta o pregunta adicional?

        Considera que está RESPONDIENDO si:
        - Proporciona información solicitada (nombre, tipo de máquina, detalles técnicos, etc.)
        - Es una afirmación o negación simple
        - Responde directamente a lo que se le preguntó

        Considera que tiene PREGUNTA ADICIONAL si:
        - Hace una consulta sobre maquinaria, precios, disponibilidad, etc.
        - Pregunta sobre algo no relacionado con la pregunta anterior
        - Cambia de tema o hace una nueva consulta

        IMPORTANTE: Un mensaje puede contener AMBAS cosas (respuesta + pregunta adicional).

        Responde SOLO con:
        - "SOLO_RESPUESTA" si solo responde
        - "SOLO_PREGUNTA" si solo hace una consulta
        - "AMBAS" si responde Y hace una consulta adicional
        - "NINGUNA" si no es ni una cosa ni la otra

        No agregues explicaciones, solo una de las cuatro opciones."""

        user_prompt = f"""Mensaje del usuario: '{message}'
        
        Último mensaje del bot: '{last_bot_message}'
        
        Clasifica este mensaje del usuario."""

        completion = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=20,
            temperature=0.1
        )
        
        response = completion.choices[0].message.content.strip().upper()
        
        # Determinar el tipo de mensaje
        is_response = "SOLO_RESPUESTA" in response or "AMBAS" in response
        has_additional_question = "SOLO_PREGUNTA" in response or "AMBAS" in response
        
        logging.info(f"LLM clasificó el mensaje '{message}' como: {response}")
        logging.info(f"Es respuesta: {is_response}, Tiene pregunta adicional: {has_additional_question}")
        
        return is_response, has_additional_question
        
    except Exception as e:
        logging.error(f"Error usando LLM para clasificar el mensaje: {e}")
        # Fallback simple: si contiene ?, probablemente tiene pregunta adicional
        message_stripped = message.strip()
        has_question_mark = "?" in message_stripped
        is_short_response = len(message_stripped) <= 50
        
        # Si es corto y no tiene ?, probablemente es solo respuesta
        if is_short_response and not has_question_mark:
            return True, False
        # Si tiene ?, probablemente es pregunta o ambas
        elif has_question_mark:
            return False, True
        # Si es largo sin ?, probablemente es respuesta
        else:
            return True, False

def extract_response_and_question(message: str, current_state: ConversationState) -> tuple[str, str]:
    """Extrae la parte de respuesta y la parte de pregunta adicional del mensaje del usuario
    
    Returns:
        tuple: (response_part, question_part)
        - response_part: La parte del mensaje que responde a la pregunta del bot
        - question_part: La parte del mensaje que contiene la consulta adicional (puede estar vacía)
    """
    try:
        # Obtener el último mensaje del bot para contexto
        last_bot_message = ""
        if current_state.conversation_history and current_state.conversation_history[-1]['sender'] == 'bot':
            last_bot_message = current_state.conversation_history[-1]['message']
        
        system_prompt = """Eres un analizador experto de mensajes. Tu tarea es separar un mensaje del usuario en dos partes:

        1. RESPUESTA: La parte que responde a la pregunta del bot
        2. PREGUNTA: La parte que contiene una consulta o pregunta adicional

        Si el mensaje solo responde, deja la PREGUNTA vacía.
        Si el mensaje solo pregunta, deja la RESPUESTA vacía.
        Si el mensaje contiene ambas, sepáralas claramente.

        Responde en formato JSON:
        {
            "respuesta": "texto de la respuesta",
            "pregunta": "texto de la pregunta adicional (vacío si no hay)"
        }"""

        user_prompt = f"""Mensaje del usuario: '{message}'
        
        Último mensaje del bot: '{last_bot_message}'
        
        Separa este mensaje en respuesta y pregunta adicional."""

        completion = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0.1
        )
        
        json_response = json.loads(completion.choices[0].message.content)
        response_part = json_response.get("respuesta", "").strip()
        question_part = json_response.get("pregunta", "").strip()
        
        logging.info(f"Mensaje separado - Respuesta: '{response_part}', Pregunta: '{question_part}'")
        
        return response_part, question_part
        
    except Exception as e:
        logging.error(f"Error separando respuesta y pregunta: {e}")
        # Fallback: tratar todo como respuesta
        return message.strip(), ""

def generate_llm_response(message: str, current_state: ConversationState, stage: str) -> str:
    """Genera respuestas dinámicas usando el LLM"""
    
    # Primero, analizar si el usuario está respondiendo y/o haciendo una pregunta adicional
    is_response, has_additional_question = is_user_response_to_bot(message, current_state)
    
    # Si el usuario está haciendo preguntas sobre maquinaria, responder específicamente
    if is_machinery_question(message):
        logging.info("Usuario haciendo pregunta sobre maquinaria, generando respuesta específica")
        return generate_machinery_response(message, current_state)
    
    # Si el usuario está respondiendo a las preguntas del bot, continuar con el flujo
    if is_response:
        logging.info("Usuario respondiendo a preguntas del bot, continuando con el flujo")
        
        # Si también tiene pregunta adicional, manejarla primero
        if has_additional_question:
            logging.info("Usuario también tiene pregunta adicional, manejando ambas partes")
            response_part, question_part = extract_response_and_question(message, current_state)
            
            # Generar respuesta para la pregunta adicional
            if question_part:
                machinery_response = generate_machinery_response(question_part, current_state)
                
                # Continuar con el flujo para la parte de respuesta
                flow_response = continue_conversation_flow(response_part, current_state, stage)
                
                # Combinar ambas respuestas
                combined_response = f"{machinery_response}\n\n{flow_response}"
                logging.info("Respuesta combinada generada: pregunta + flujo")
                return combined_response
        
        # Si solo está respondiendo, continuar con el flujo normal
        return continue_conversation_flow(message, current_state, stage)
    
    try:
        # Determinar el contexto basado en la etapa
        if stage == "greeting":
            system_prompt = """Eres un asistente virtual amigable de una empresa de maquinaria ligera. 
            El usuario acaba de iniciar una conversación. Saluda de manera cálida y profesional, 
            y pide su nombre para poder ayudarlo mejor. Sé natural y conversacional."""
            
        elif stage == "name":
            system_prompt = """Eres un asistente virtual de maquinaria ligera. El usuario ya te dio su nombre. 
            Agradécele y pregúntale qué tipo de máquina o equipo necesita. 
            Sé amigable y profesional."""
            
        elif stage == "machine_type":
            system_prompt = """Eres un asistente virtual de maquinaria ligera. El usuario ya te dijo qué máquina necesita. 
            Haz preguntas específicas sobre esa máquina para entender mejor sus requerimientos. 
            Sé técnico pero comprensible."""
            
        elif stage == "machine_details":
            system_prompt = """Eres un asistente virtual de maquinaria ligera. Estás recopilando detalles específicos 
            de la máquina que necesita el usuario. Haz preguntas técnicas relevantes de manera clara."""
            
        elif stage == "quote_info":
            system_prompt = """Eres un asistente virtual de maquinaria ligera. Estás recopilando información 
            para generar una cotización. Pregunta sobre el uso empresarial, datos de contacto, etc. 
            Sé profesional y organizado."""
            
        elif stage == "distributor_check":
            system_prompt = """Eres un asistente virtual de maquinaria ligera. Estás finalizando la información 
            para la cotización. Pregunta si es distribuidor y confirma que tienes toda la información necesaria."""
            
        else:
            system_prompt = """Eres un asistente virtual de maquinaria ligera. Responde de manera profesional 
            y útil a las consultas del usuario."""
        
        # Agregar contexto de la conversación
        conversation_context = f"""
        Etapa actual: {stage}
        Información recopilada: {current_state.extracted_info.model_dump()}
        Historial de mensajes: {len(current_state.conversation_history)} mensajes
        """
        
        completion = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt + "\n\n" + conversation_context},
                {"role": "user", "content": f"Genera una respuesta apropiada para el mensaje: '{message}'"}
            ],
            max_tokens=200,
            temperature=0.7
        )
        
        response = completion.choices[0].message.content
        logging.info(f"Respuesta generada por LLM: {response}")
        return response
        
    except Exception as e:
        logging.error(f"Error generando respuesta con LLM: {e}")
        # Fallback a respuestas estáticas
        return get_static_fallback_response(stage, current_state)

def continue_conversation_flow(message: str, current_state: ConversationState, stage: str) -> str:
    """Continúa el flujo de conversación cuando el usuario responde a las preguntas del bot"""
    try:
        # Determinar la siguiente etapa basándose en la información actual
        next_stage, next_question = determine_next_stage(current_state)
        
        # Si la etapa cambió, actualizar el estado
        if next_stage != stage:
            current_state.current_stage = next_stage
            logging.info(f"Avanzando de etapa {stage} a {next_stage}")
        
        # Generar respuesta contextual usando el LLM
        system_prompt = f"""Eres un asistente virtual de maquinaria ligera. El usuario está respondiendo a tus preguntas.
        
        Etapa actual: {next_stage}
        Pregunta siguiente: {next_question}
        
        Basándote en la respuesta del usuario y la siguiente pregunta que debes hacer, genera una respuesta natural
        que reconozca la información proporcionada y continúe con la siguiente pregunta.
        
        Mantén un tono profesional pero amigable, y asegúrate de que la conversación fluya naturalmente.
        
        Si el usuario proporcionó información útil, reconócela brevemente antes de hacer la siguiente pregunta."""
        
        conversation_context = f"""
        Información recopilada: {current_state.extracted_info.model_dump()}
        Último mensaje del usuario: {message}
        Pregunta siguiente: {next_question}
        """
        
        completion = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt + "\n\n" + conversation_context},
                {"role": "user", "content": "Genera una respuesta que reconozca la información del usuario y continúe con la siguiente pregunta."}
            ],
            max_tokens=250,
            temperature=0.7
        )
        
        response = completion.choices[0].message.content
        logging.info(f"Respuesta de continuación generada: {response}")
        return response
        
    except Exception as e:
        logging.error(f"Error generando respuesta de continuación: {e}")
        # Fallback: usar la pregunta siguiente directamente
        try:
            next_stage, next_question = determine_next_stage(current_state)
            if next_stage != stage:
                current_state.current_stage = next_stage
            return next_question
        except:
            return get_static_fallback_response(stage, current_state)

def get_static_fallback_response(stage: str, current_state: ConversationState) -> str:
    """Respuestas estáticas de fallback si falla el LLM"""
    info = current_state.extracted_info
    
    if stage == "greeting":
        return "¡Hola! Soy tu asistente virtual de maquinaria ligera. Para poder ayudarte mejor, ¿con quién tengo el gusto?"
    
    elif stage == "name":
        if info.name:
            return f"Mucho gusto {info.name}. ¿Qué tipo de máquina o equipo necesitas?"
        else:
            return "¡Hola! Para poder ayudarte mejor, ¿con quién tengo el gusto?"
    
    elif stage == "machine_type":
        if info.machine_type:
            return f"Perfecto, veo que necesitas una {info.machine_type}. Déjame hacerte algunas preguntas específicas para entender mejor tus requerimientos."
        else:
            return "¿Qué tipo de máquina o equipo necesitas?"
    
    elif stage == "machine_details":
        return "Necesito algunos detalles técnicos para poder ayudarte mejor."
    
    elif stage == "quote_info":
        return "Para generar tu cotización, necesito algunos datos adicionales."
    
    elif stage == "distributor_check":
        return "¿Eres distribuidor?"
    
    else:
        return "¿En qué puedo ayudarte?"

def determine_next_stage(state: ConversationState) -> tuple[str, str]:
    """Determina la siguiente etapa y genera la pregunta correspondiente"""
    info = state.extracted_info
    logging.info(f"=== DETERMINANDO SIGUIENTE ETAPA ===")
    logging.info(f"Estado actual: {state.current_stage}")
    logging.info(f"Info completa: {info.model_dump()}")
    logging.info(f"Campo name: '{info.name}' (tipo: {type(info.name)})")
    logging.info(f"¿Name está vacío?: {info.name is None or info.name.strip() == ''}")
    logging.info(f"¿Name tiene contenido?: {bool(info.name and info.name.strip())}")
    
    # Verificar si tenemos nombre
    if not info.name or info.name.strip() == "":
        logging.info("❌ Falta nombre, permaneciendo en etapa 'name'")
        return "name", "¡Hola! Para poder ayudarte mejor, ¿con quién tengo el gusto?"
    
    logging.info(f"✅ Nombre encontrado: '{info.name}', avanzando a 'machine_type'")
    
    # Verificar si tenemos tipo de máquina
    if not info.machine_type or info.machine_type.strip() == "":
        logging.info("Nombre completo, avanzando a 'machine_type'")
        return "machine_type", f"Mucho gusto {info.name}. ¿Qué tipo de máquina o equipo necesitas?"
    
    # Preguntas específicas por tipo de máquina
    machine_lower = info.machine_type.lower().strip()
    logging.info(f"Verificando preguntas específicas para: {machine_lower}")
    
    if machine_lower in MACHINE_QUESTIONS:
        missing_questions = get_missing_machine_questions(info, machine_lower)
        if missing_questions:
            logging.info(f"Preguntas faltantes para {machine_lower}: {missing_questions}")
            return "machine_details", missing_questions[0]
    
    # Preguntas para cotización
    missing_quote_info = get_missing_quote_info(info)
    if missing_quote_info:
        logging.info(f"Información de cotización faltante: {missing_quote_info}")
        return "quote_info", missing_quote_info[0]
    
    # Verificar distribuidor
    if info.is_distributor is None:
        logging.info("Falta información de distribuidor")
        return "distributor_check", "¿Eres distribuidor?"
    
    logging.info("Conversación completada")
    return "completed", "¡Perfecto! Ya tengo toda la información necesaria. Te contactaremos pronto con tu cotización."

def get_missing_machine_questions(info: ExtractedInfo, machine_type: str) -> list[str]:
    """Determina qué preguntas específicas de máquina faltan"""
    missing = []
    
    if machine_type == "soldadora":
        if not info.welding_amperage and not info.welding_electrode:
            missing.append("¿Qué amperaje requiere o qué electrodo quema?")
    
    elif machine_type == "compresor":
        if not info.compressor_volume and not info.compressor_tools:
            missing.append("¿Qué capacidad de volumen de aire requiere o qué herramienta le va a conectar?")
    
    elif machine_type == "torre de iluminacion":
        if info.lighting_led is None:
            missing.append("¿La requiere de Led?")
    
    elif machine_type == "lgmg":
        if not info.lgmg_height:
            missing.append("¿Qué altura de trabajo necesita?")
        elif not info.lgmg_activity:
            missing.append("¿Qué actividad va a realizar?")
        elif not info.lgmg_location:
            missing.append("¿Es en exterior, o interior?")
    
    elif machine_type == "generador":
        if not info.generator_activity:
            missing.append("¿Para qué actividad lo requiere?")
        elif not info.generator_capacity:
            missing.append("¿Qué capacidad en (kvas o kw)?")
    
    elif machine_type == "rompedor":
        if not info.breaker_use:
            missing.append("¿Para qué lo vas a utilizar?")
        elif not info.breaker_type:
            missing.append("Lo requiere eléctrico o neumático?")
    
    return missing

def get_missing_quote_info(info: ExtractedInfo) -> list[str]:
    """Determina qué información de cotización falta"""
    missing = []
    
    if not info.business_use:
        missing.append("¿Es para uso de la empresa o para venta?")
    elif not info.company_name:
        missing.append("¿Cuál es el nombre y giro de tu empresa?")
    elif not info.email:
        missing.append("¿Cuál es tu correo electrónico?")
    elif not info.phone:
        missing.append("¿Cuál es tu número telefónico?")
    
    return missing

def handle_lead_message(message: str, wa_id: str) -> str:
    """Función principal que maneja los mensajes de WhatsApp"""
    
    logging.info(f"=== PROCESANDO MENSAJE ===")
    logging.info(f"WA_ID: {wa_id}")
    logging.info(f"Mensaje: '{message}'")
    
    # Obtener estado actual de la conversación
    current_state = get_conversation_state(wa_id)
    logging.info(f"Estado actual: {current_state.current_stage}")
    logging.info(f"Info antes del procesamiento: {current_state.extracted_info.model_dump()}")
    
    # Agregar mensaje al historial
    current_state.conversation_history.append({
        "timestamp": datetime.now().isoformat(),
        "message": message,
        "sender": "user"
    })
    
    # Extraer información del mensaje actual
    new_extracted_info = analyze_message_with_llm(message, current_state)
    logging.info(f"Nueva información extraída: {new_extracted_info.model_dump()}")
    
    # Combinar con información existente
    old_info_dict = current_state.extracted_info.model_dump()
    current_state.extracted_info = merge_extracted_info(
        current_state.extracted_info, 
        new_extracted_info
    )
    new_info_dict = current_state.extracted_info.model_dump()
    
    logging.info(f"Información después del merge: {new_info_dict}")
    logging.info(f"¿Se extrajo nombre?: {bool(current_state.extracted_info.name)}")
    logging.info(f"Nombre extraído: '{current_state.extracted_info.name}'")
    
    # Determinar siguiente etapa
    next_stage, _ = determine_next_stage(current_state)
    logging.info(f"Siguiente etapa determinada: {next_stage}")
    
    # Generar respuesta usando LLM
    response_message = generate_llm_response(message, current_state, next_stage)
    logging.info(f"Respuesta generada: '{response_message}'")
    
    # Actualizar el estado
    current_state.current_stage = next_stage
    
    # Agregar respuesta al historial
    current_state.conversation_history.append({
        "timestamp": datetime.now().isoformat(),
        "message": response_message,
        "sender": "bot"
    })
    
    # Guardar estado actualizado
    update_conversation_state(wa_id, current_state)
    
    logging.info(f"=== FIN DEL PROCESAMIENTO ===\n")
    
    return response_message

def test_name_extraction():
    """Función de prueba para verificar la extracción de nombres"""
    logging.info("=== PRUEBA DE EXTRACCIÓN DE NOMBRES ===")
    
    test_messages = [
        "Me llamo Paco López",
        "Soy María",
        "Mi nombre es Carlos",
        "Juan",
        "Hola, ¿cómo estás?"
    ]
    
    for message in test_messages:
        logging.info(f"\n--- Probando: '{message}' ---")
        try:
            result = analyze_message_with_llm(message, ConversationState())
            logging.info(f"✅ Resultado: name='{result.name}', machine_type='{result.machine_type}'")
        except Exception as e:
            logging.error(f"❌ Error: {e}")

# ==== Funciones de utilidad ====
def debug_extraction(message: str) -> ExtractedInfo:
    """Función de debug para probar la extracción de información"""
    logging.info(f"=== DEBUG EXTRACCIÓN ===")
    logging.info(f"Mensaje a analizar: '{message}'")
    
    try:
        # Probar structured output
        completion = client.beta.chat.completions.parse(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": """Eres un extractor de información experto para una empresa de maquinaria ligera.
                
                Extrae ÚNICAMENTE la información que está claramente presente en el mensaje del usuario.
                
                Para NOMBRES, busca específicamente estos patrones:
                - "Me llamo [NOMBRE]" → extrae solo el nombre
                - "Soy [NOMBRE]" → extrae solo el nombre  
                - "Mi nombre es [NOMBRE]" → extrae solo el nombre
                - Solo "[NOMBRE]" si es claramente un nombre (no saludos)
                
                Para máquinas: identifica el tipo de máquina mencionada.
                Para teléfonos: números de 10 dígitos.
                Para emails: direcciones de correo válidas.
                
                IMPORTANTE: Para nombres, extrae SOLO el nombre, sin apellidos si no están claramente especificados.
                Si no hay información clara en algún campo, déjalo en null.
                Solo extrae lo que está explícitamente en el mensaje."""},
                {"role": "user", "content": f"Analiza este mensaje y extrae la información disponible: '{message}'"}
            ],
            response_format=ExtractedInfo,
        )
        
        extracted = completion.choices[0].message.parsed
        logging.info(f"Structured output exitoso: {extracted.model_dump()}")
        return extracted
        
    except Exception as e:
        logging.error(f"Error con structured output: {e}")
        
        # Probar JSON fallback
        try:
            completion = client.chat.completions.create(
                model=GPT_MODEL,
                messages=[
                    {"role": "system", "content": """Analiza el mensaje y extrae información en formato JSON.
                    
                    Busca específicamente:
                    - NOMBRES: "Me llamo Juan", "Soy María", "Mi nombre es Carlos", o solo nombres claros
                    - Máquinas: soldadora, compresor, torre de iluminacion, lgmg, generador, rompedor
                    - Teléfonos y emails
                    
                    Para nombres: extrae SOLO el nombre, sin apellidos si no están claramente especificados.
                    
                    Responde SOLO con JSON válido. Ejemplo:
                    {"name": "Juan", "machine_type": "soldadora", "phone": null, "email": null, "company_name": null, "city": null, "welding_amperage": null, "welding_electrode": null, "compressor_volume": null, "compressor_tools": null, "lighting_led": null, "lgmg_height": null, "lgmg_activity": null, "lgmg_location": null, "generator_activity": null, "generator_capacity": null, "generator_fuel_receipt": null, "breaker_use": null, "breaker_type": null, "business_use": null, "is_distributor": null}"""},
                    {"role": "user", "content": f"Mensaje: '{message}'"}
                ],
                response_format={"type": "json_object"}
            )
            
            json_response = json.loads(completion.choices[0].message.content)
            extracted = ExtractedInfo(**json_response)
            logging.info(f"JSON fallback exitoso: {extracted.model_dump()}")
            return extracted
            
        except Exception as e2:
            logging.error(f"Error en JSON fallback: {e2}")
            return ExtractedInfo()

def get_conversation_summary(wa_id: str) -> dict:
    """Obtiene un resumen de la conversación para debugging"""
    if wa_id in CONVERSATIONS_DB:
        state = CONVERSATIONS_DB[wa_id]
        return {
            "stage": state.current_stage,
            "extracted_info": state.extracted_info.model_dump(),
            "messages_count": len(state.conversation_history)
        }
    return {"error": "Conversation not found"}

def reset_conversation(wa_id: str):
    """Reinicia una conversación específica"""
    if wa_id in CONVERSATIONS_DB:
        del CONVERSATIONS_DB[wa_id]
        logging.info(f"Conversación reiniciada para wa_id: {wa_id}")

def get_all_conversations() -> dict:
    """Obtiene todas las conversaciones activas (para debugging)"""
    return {wa_id: state.model_dump() for wa_id, state in CONVERSATIONS_DB.items()}