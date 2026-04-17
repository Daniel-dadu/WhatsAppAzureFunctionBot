import json
import re
import os
from typing import Dict, Any, List, Optional, Tuple
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import langchain
from ai_prompts import (
    NEGATIVE_RESPONSE_PROMPT, 
    EXTRACTION_PROMPT, 
    RESPONSE_GENERATION_PROMPT, 
    INVENTORY_DETECTION_PROMPT
)
from maquinaria_config import machinery_config_service, get_required_fields_for_tipo
from state_management import ConversationState, ConversationStateStore, InMemoryStateStore, FIELDS_CONFIG_PRIORITY
from datetime import datetime, timezone
import logging
from hubspot_manager import HubSpotManager
from inventory_service import InventoryService

langchain.debug = False
langchain.verbose = False
langchain.llm_cache = False

# ============================================================================
# CONFIGURACIÓN DE DEBUG
# ============================================================================

# Variable global para controlar si se muestran los prints de DEBUG
DEBUG_MODE = True

def debug_print(*args, **kwargs):
    """
    Función helper para imprimir mensajes de DEBUG solo cuando DEBUG_MODE es True
    """
    if DEBUG_MODE:
        logging.info(*args, **kwargs)

# ============================================================================
# INVENTARIO FAKE
# ============================================================================

def get_inventory():
    return {
        "tipo_maquinaria": [
            "soldadora",
            "compresor",
            "torre_iluminacion",
            "plataforma",
            "generador",
            "rompedor",
            "apisonador",
            "montacargas",
            "manipulador"
        ],
        "modelo_maquinaria": "Cualquier modelo",
        "ubicacion": "Cualquier ubicación en México",
    }

# ============================================================================
# OBTENER EL ESTADO ACTUAL DE LOS CAMPOS EN UN STRING
# ============================================================================

def get_current_state_str(current_state: ConversationState) -> str:
    """Obtiene el estado actual de los campos como una cadena de texto"""
    field_names = [field for field in FIELDS_CONFIG_PRIORITY.keys()]
    fields_str = ""
    for field in field_names:
        if field == "detalles_maquinaria":
            fields_str += f"- {field}: " + json.dumps(current_state.get(field) or {}) + "\n"
        else:
            value = current_state.get(field)
            # Convert to string to handle boolean values like quiere_cotizacion
            fields_str += f"- {field}: " + (str(value) if value is not None else "") + "\n"
    return fields_str

# ============================================================================
# CONFIGURACIÓN DE AZURE OPENAI
# ============================================================================

class AzureOpenAIConfig:
    """Clase para manejar la configuración de Azure OpenAI con diferentes configuraciones según el propósito"""
    
    def __init__(self, 
                 endpoint: str,
                 api_key: str,
                 deployment_name: str,
                 api_version: str = "2024-12-01-preview",
                 model_name: str = "gpt-4.1-mini"):
        self.endpoint = endpoint
        self.api_key = api_key
        self.deployment_name = deployment_name
        self.api_version = api_version
        self.model_name = model_name
        
        # Configurar variables de entorno para Azure OpenAI
        os.environ["FOUNDRY_ENDPOINT"] = endpoint
        os.environ["FOUNDRY_API_KEY"] = api_key
        os.environ["OPENAI_API_VERSION"] = api_version
    
    def create_llm(self, temperature: float = 0.3, max_tokens: int = 1000, top_p: float = 1.0):
        """Crea una instancia de AzureChatOpenAI con parámetros personalizados"""
        return AzureChatOpenAI(
            azure_endpoint=self.endpoint,
            api_key=self.api_key,
            azure_deployment=self.deployment_name,
            api_version=self.api_version,
            model_name=self.model_name,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            timeout=60,
            max_retries=3,
            verbose=True
        )
    
    def create_extraction_llm(self):
        """Crea un LLM optimizado para extracción de información (temperatura baja para mayor precisión)"""
        return self.create_llm(
            temperature=0.1,  # Temperatura muy baja para extracción precisa
            top_p=0.9,        # Top-p moderado para consistencia
            max_tokens=1000
        )
    
    def create_conversational_llm(self):
        """Crea un LLM optimizado para generación conversacional (temperatura alta para mayor creatividad)"""
        return self.create_llm(
            temperature=0.7,  # Temperatura alta para respuestas más creativas y variadas
            top_p=0.95,       # Top-p alto para mayor diversidad
            max_tokens=75
        )
    
    def create_inventory_llm(self):
        """Crea un LLM para responder preguntas sobre inventario (temperatura moderada)"""
        return self.create_llm(
            temperature=0.5,  # Temperatura moderada para balance entre precisión y creatividad
            top_p=0.9,       # Top-p moderado
            max_tokens=1000
        )

# ============================================================================
# FUNCIONES HELPER
# ============================================================================

def _is_distribuidor(giro: str) -> bool:
    """Verifica si el giro corresponde a un distribuidor basado en palabras clave."""
    if not giro:
        return False
    g = giro.lower()
    distributor_keywords = ["venta", "renta", "distribuidor", "reventa", "distribucion", "distribución"]
    for keyword in distributor_keywords:
        if keyword in g:
            return True
    return False

def _format_machine_details(machine: Dict[str, Any]) -> str:
    """Extrae las características técnicas de una máquina en un string amigable."""
    ignore_keys = {"modelo", "categoria", "id", "_rid", "_self", "_etag", "_attachments", "_ts", "precio", "moneda"}
    details = []
    for key, value in machine.items():
        if key not in ignore_keys and value is not None and str(value).strip() != "":
            # Convert keys: "altura_trabajo_m" -> "Altura Trabajo M"
            label = " ".join(word.capitalize() for word in key.split("_"))
            details.append(f"{label}: {value}")
    
    if details:
        return f" ({', '.join(details)})"
    return ""

def get_pending_empresa_fields(current_state: ConversationState) -> List[str]:
    """
    Extrae los campos pendientes de la empresa según el flujo de venta o uso propio.
    Retorna una lista con los labels de los campos que aún no han sido respondidos.
    """
    uso = current_state.get("uso_empresa_o_venta")
    
    # 1. Primer bloque: uso, correo, ubicacion
    if not uso:
        pending = ["si te dedicas a la venta/renta de maquinaria"]
        if not current_state.get("correo"):
            pending.append("correo electrónico")
        if not current_state.get("lugar_requerimiento"):
            pending.append("ubicación (estado de la República Mexicana)")
        return pending

    pending_basic = []
    if not current_state.get("correo"):
        pending_basic.append("correo electrónico")
    if not current_state.get("lugar_requerimiento"):
        pending_basic.append("ubicación (estado de la República Mexicana)")
        
    if uso == "venta":
        constancia = current_state.get("constancia_fiscal_entregada")
        if not constancia: # None
            return pending_basic + ["Constancia de Situación Fiscal"]
        elif constancia == "No tiene" or constancia is False:
            giro = current_state.get("giro_empresa")
            if not giro:
                return pending_basic + ["Giro de la empresa"]
            
            is_distribuidor = _is_distribuidor(giro)
            if is_distribuidor:
                return pending_basic
            else:
                if not current_state.get("nombre_empresa"):
                    return pending_basic + ["Nombre de la empresa"]
                return pending_basic
        else:
            return pending_basic
            
    else: # uso == "uso empresa"
        if not current_state.get("nombre_empresa"):
            pending_basic.append("Nombre de la empresa")
        if not current_state.get("giro_empresa"):
            pending_basic.append("Giro de la empresa")
            
        return pending_basic

# ============================================================================
# SISTEMA DE SLOT-FILLING INTELIGENTE
# ============================================================================

class IntelligentSlotFiller:
    """Sistema inteligente de slot-filling que detecta información ya proporcionada"""
    
    def __init__(self, azure_config: AzureOpenAIConfig):
        self.llm = azure_config.create_extraction_llm()  # Usar LLM optimizado para extracción
        self.parser = JsonOutputParser()
    
    def _parse_json_robust(self, text: str) -> dict:
        """
        Parsing robusto de JSON que maneja:
        - JSON envuelto en bloques de código markdown (```json ... ```)
        - Texto extra antes/después del JSON
        - Respuestas con explicaciones antes del JSON
        Retorna un dict o lanza una excepción si no se puede parsear.
        """
        if not text or not text.strip():
            return {}
        
        original_text = text
        text = text.strip()
        
        # 1. Intentar parseo directo
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
        
        # 2. Intentar extraer JSON de bloques de código markdown
        code_block_match = re.search(r'```(?:json)?\s*\n?(\{[\s\S]*?\})\s*\n?```', text)
        if code_block_match:
            try:
                result = json.loads(code_block_match.group(1))
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass
        
        # 3. Intentar encontrar la primera aparición de un objeto JSON { ... }
        brace_match = re.search(r'(\{[\s\S]*\})', text)
        if brace_match:
            try:
                result = json.loads(brace_match.group(1))
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass
        
        # 4. Intentar con el parser de LangChain como último recurso
        try:
            result = self.parser.parse(original_text)
            if isinstance(result, dict):
                return result
        except Exception:
            pass
        
        raise ValueError(f"No se pudo extraer JSON válido del texto: {text[:200]}")
        
    def detect_negative_response(self, message: str, last_bot_question: Optional[str] = None) -> Optional[Dict[str, str]]:
        """
        Detecta si el usuario está dando una respuesta negativa o de incertidumbre.
        Retorna un diccionario con el tipo de respuesta y el campo específico, o None si no es una respuesta negativa.
        Formato: {"response_type": "No tiene" o "No especificado", "field": "nombre_del_campo"}
        """
        prompt = NEGATIVE_RESPONSE_PROMPT
        
        try:
            # Obtener campos disponibles desde el FIELDS_CONFIG_PRIORITY
            fields_available = self._get_fields_available_str()

            response = self.llm.invoke(prompt.format_prompt(
                message=message,
                last_bot_question=last_bot_question or "No hay pregunta previa",
                fields_available=fields_available
            ))
            
            result = response.content.strip()
            
            # Verificar si es "None" (no es respuesta negativa)
            if result.lower().strip('"\'') == "none":
                return None
            
            # Intentar parsear como JSON con método robusto
            try:
                parsed_result = self._parse_json_robust(result)
                if isinstance(parsed_result, dict) and "response_type" in parsed_result and "field" in parsed_result:
                    return parsed_result
                else:
                    return None
            except (ValueError, json.JSONDecodeError):
                return None
                
        except Exception as e:
            logging.error(f"Error detectando respuesta negativa: {e}")
            return None

    def extract_all_information(self, message: str, current_state: ConversationState, last_bot_question: Optional[str] = None) -> Dict[str, Any]:
        """
        Extrae TODA la información disponible en un solo mensaje
        Detecta qué slots se pueden llenar y cuáles ya están completos
        Incluye el contexto de la última pregunta del bot para mejor interpretación
        """
        
        # PRIMERO: Detectar si es una respuesta negativa o de incertidumbre
        negative_response = self.detect_negative_response(message, last_bot_question)
        
        extracted_data = {}

        if negative_response:
            # Si es una respuesta negativa, guardar el campo y valor
            field_name = negative_response.get("field")
            response_type = negative_response.get("response_type")
            
            if field_name and response_type:
                extracted_data[field_name] = response_type
        
        # SEGUNDO: Extraer el resto de la información usando el prompt general
        # Crear prompt que considere el estado actual y la última pregunta del bot
        prompt = EXTRACTION_PROMPT
        
        try:
            # Nombres de tipos de maquinaria
            # OBTENER DINÁMICAMENTE LOS NOMBRES DESDE LA CONFIGURACIÓN (Strings)
            maquinaria_names = " ".join([f"\"{m.type_id}\"" for m in machinery_config_service.get_all_types()])

            # Obtener campos disponibles desde el FIELDS_CONFIG_PRIORITY
            fields_available = self._get_fields_available_str()

            # Obtener campos específicos del tipo de maquinaria actual
            machine_type = current_state.get("tipo_maquinaria")
            machine_specific_fields = ""
            
            if machine_type:
                # Validar dinámicamente si existe configuración
                config = machinery_config_service.get_config(machine_type)
                if config:
                   field_instructions = []
                   for field in config.fields:
                       field_instructions.append(f"- Para {machine_type.upper()}: {field.name} ({field.question})")
                   machine_specific_fields = "\n".join(field_instructions)
            
            if not machine_specific_fields:
                machine_specific_fields = "- No hay un tipo de maquinaria seleccionado aún, o no hay configuración específica."

            # Formatear la lista de máquinas recomendadas para el prompt
            recomendadas = current_state.get("maquinas_recomendadas", [])
            if recomendadas:
                maquinas_lines = [f"  {i+1}. {modelo}" for i, modelo in enumerate(recomendadas)]
                maquinas_recomendadas_str = "\n".join(maquinas_lines)
            else:
                maquinas_recomendadas_str = "  (No hay máquinas recomendadas aún)"

            response = self.llm.invoke(prompt.format_prompt(
                message=message,
                current_state_str=get_current_state_str(current_state),
                last_bot_question=last_bot_question or "No hay pregunta previa (inicio de conversación)",
                maquinaria_names=maquinaria_names,
                fields_available=fields_available,
                machine_specific_fields=machine_specific_fields,
                maquinas_recomendadas_str=maquinas_recomendadas_str
            ))
            
            # Parsear la respuesta JSON con método robusto
            raw_content = response.content
            try:
                general_extraction = self._parse_json_robust(raw_content)
            except ValueError as parse_err:
                logging.error(f"Error parseando JSON de extracción. Respuesta del LLM: '{raw_content[:300]}'. Error: {parse_err}")
                general_extraction = {}
            
            # Fusionar resultados (la extracción general tiene prioridad si encuentra algo más específico,
            # pero mantenemos la respuesta negativa si no hay conflicto o si es complementaria)
            if isinstance(general_extraction, dict):
                extracted_data.update(general_extraction)
            
            logging.info(f"Extracción completada. Mensaje: '{message[:50]}' → Datos: {json.dumps(extracted_data, ensure_ascii=False, default=str)}")
            
            # Lógica determinista de selección implícita
            quiere_cot_new = extracted_data.get("quiere_cotizacion")
            quiere_cot_curr = current_state.get("quiere_cotizacion")
            is_quoting = quiere_cot_new is True or quiere_cot_curr is True
            
            if is_quoting and not extracted_data.get("maquina_seleccionada") and not current_state.get("maquina_seleccionada"):
                recomendadas = current_state.get("maquinas_recomendadas", [])
                if isinstance(recomendadas, list) and len(recomendadas) == 1:
                    extracted_data["maquina_seleccionada"] = recomendadas[0]
                    logging.info(f"Seleccionada automáticamente la única opción recomendada: {recomendadas[0]}")
            
            return extracted_data
            
        except Exception as e:
            logging.error(f"Error extrayendo información: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            return extracted_data
    
    def get_next_question(self, current_state: ConversationState) -> Optional[str]:
        """
        Determina inteligentemente cuál es la siguiente pregunta necesaria
        siguiendo el flujo definido en el diagrama PlantUML.
        """
        try:
            # 1. NOMBRE Y APELLIDO
            # Verificar si tenemos el nombre
            nombre = current_state.get("nombre")
            if not nombre:
                return {
                    "question": FIELDS_CONFIG_PRIORITY["nombre"]["question"],
                    "reason": FIELDS_CONFIG_PRIORITY["nombre"]["reason"],
                    "question_type": "nombre"
                }
            
            # Verificar si tenemos el apellido (o si el nombre ya incluye apellido)
            apellido = current_state.get("apellido")
            if not apellido and len(nombre.split()) < 2:
                return {
                    "question": FIELDS_CONFIG_PRIORITY["apellido"]["question"],
                    "reason": FIELDS_CONFIG_PRIORITY["apellido"]["reason"],
                    "question_type": "apellido"
                }

            # 2. TIPO DE AYUDA
            tipo_ayuda = current_state.get("tipo_ayuda")
            if not tipo_ayuda:
                return {
                    "question": FIELDS_CONFIG_PRIORITY["tipo_ayuda"]["question"],
                    "reason": FIELDS_CONFIG_PRIORITY["tipo_ayuda"]["reason"],
                    "question_type": "tipo_ayuda"
                }
            
            # Si el tipo de ayuda es "otro", terminamos el flujo de preguntas
            if tipo_ayuda == "otro":
                return None

            # 3. TIPO DE MAQUINARIA (Solo si tipo_ayuda es "maquinaria")
            tipo_maquinaria = current_state.get("tipo_maquinaria")
            if not tipo_maquinaria:
                return {
                    "question": FIELDS_CONFIG_PRIORITY["tipo_maquinaria"]["question"],
                    "reason": FIELDS_CONFIG_PRIORITY["tipo_maquinaria"]["reason"],
                    "question_type": "tipo_maquinaria"
                }

            # 4. DETALLES DE MAQUINARIA
            # Verificar si faltan detalles específicos
            if not self._are_maquinaria_details_complete(current_state):
                question_details = self._get_maquinaria_detail_question_with_reason(current_state)
                if question_details:
                    return question_details

            # 5. COTIZACIÓN / INVENTARIO
            # Si no hemos recomendado máquinas aún, forzamos este paso para que se active la búsqueda de inventario.
            quiere_cotizacion = current_state.get("quiere_cotizacion")
            if not current_state.get("maquinas_recomendadas"):
                return {
                    "question": FIELDS_CONFIG_PRIORITY["quiere_cotizacion"]["question"],
                    "reason": FIELDS_CONFIG_PRIORITY["quiere_cotizacion"]["reason"],
                    "question_type": "quiere_cotizacion"
                }
            
            # Si ya se recomendaron máquinas y el usuario no quiere cotización, terminamos
            if quiere_cotizacion is False:
                return None

            # 6. DATOS DE EMPRESA
            # Si quiere cotización o está pendiente, pedir datos de empresa si faltan
            pending_fields = get_pending_empresa_fields(current_state)
            if len(pending_fields) > 0:
                return {
                    "question": "Necesito los siguientes datos de su empresa para continuar con la cotización.",  # Mensaje explícito para evitar que el LLM piense que acabó
                    "reason": "Para generar la cotización",
                    "question_type": "datos_empresa"
                }

            # Si llegamos aquí, tenemos toda la información necesaria
            return None
            
        except Exception as e:
            logging.error(f"Error generando siguiente pregunta: {e}")
            return None

    def _get_fields_available_str(self) -> str:
        """Obtiene los campos disponibles como una lista de strings con su descripción"""
        fields_available = [field for field in FIELDS_CONFIG_PRIORITY.keys()]
        fields_available_str = ""
        for field in fields_available:
            fields_available_str += f"- {field}: " + FIELDS_CONFIG_PRIORITY[field]['description'] + "\n"
        return fields_available_str
    
    def _get_contextual_required_fields(self, current_state: ConversationState) -> list:
        """
        Obtiene los campos requeridos para el tipo de maquinaria actual,
        filtrando campos condicionales según el contexto.
        Ej: tipo_alimentacion solo se requiere para plataformas articuladas.
        """
        tipo = current_state.get("tipo_maquinaria")
        required_fields = get_required_fields_for_tipo(tipo)
        
        # Para plataformas, tipo_alimentacion solo aplica a "articulada"
        if tipo == "plataforma":
            detalles = current_state.get("detalles_maquinaria", {})
            tipo_plataforma = detalles.get("tipo_plataforma", "")
            if tipo_plataforma and tipo_plataforma != "articulada":
                required_fields = [f for f in required_fields if f != "tipo_alimentacion"]
        
        return required_fields

    def _are_maquinaria_details_complete(self, current_state: ConversationState) -> bool:
        """Verifica si todos los detalles de maquinaria están completos"""
        tipo = current_state.get("tipo_maquinaria")
        
        if not tipo:
            return False
            
        # Verificar si existe configuración para este tipo
        if not machinery_config_service.get_config(tipo):
            return False
        
        detalles = current_state.get("detalles_maquinaria", {})
        required_fields = self._get_contextual_required_fields(current_state)
        
        return all(
            field in detalles and 
            detalles[field] is not None and 
            detalles[field] != ""
            for field in required_fields
        )
    
    def _get_maquinaria_detail_question_with_reason(self, current_state: ConversationState) -> Optional[dict]:
        """Obtiene la siguiente pregunta específica sobre detalles de maquinaria de manera conversacional con el motivo"""
        
        tipo = current_state.get("tipo_maquinaria")

        config = machinery_config_service.get_config(tipo)
        if not config:
            return None

        detalles = current_state.get("detalles_maquinaria", {})

        # Obtener campos requeridos según contexto (ej: tipo_alimentacion solo para articulada)
        contextual_required = self._get_contextual_required_fields(current_state)

        # Buscar el primer campo de la configuración que no esté en los detalles
        for field_info in config.fields:
            field_name = field_info.name
            # Saltar campos que no aplican en el contexto actual
            if field_name not in contextual_required:
                continue
            if not detalles.get(field_name):
                # Encontrado el siguiente campo a preguntar
                # Devolver la pregunta fija definida en la configuración centralizada
                return {
                    "question": field_info.question, 
                    "reason": field_info.reason, 
                    "question_type": "detalles_maquinaria"
                }

        return None # Todos los detalles están completos
    
    def is_conversation_complete(self, current_state: ConversationState) -> bool:
        """Verifica si la conversación está completa (todos los slots llenos)"""

        # Verificar si el nombre tiene al menos dos palabras (nombre + apellido)
        nombre = current_state.get("nombre", "")
        if not nombre or len(nombre.split()) < 2:
            return False

        # Verificar tipo_ayuda
        tipo_ayuda = current_state.get("tipo_ayuda")
        if not tipo_ayuda:
            return False
        
        # Si tipo_ayuda es "otro", solo se requiere nombre y apellido
        if tipo_ayuda == "otro":
            # Solo verificar nombre y apellido
            nombre = current_state.get("nombre", "")
            if not nombre or len(nombre.split()) < 2:
                return False
            
            return True
        
        # Si tipo_ayuda es "maquinaria", verificar también tipo_maquinaria y detalles_maquinaria
        # Obtener campos obligatorios desde el FIELDS_CONFIG_PRIORITY
        required_fields = [field for field in FIELDS_CONFIG_PRIORITY.keys() if FIELDS_CONFIG_PRIORITY[field]["required"]]
        
        # Verificar campos básicos
        for field in required_fields:
            value = current_state.get(field)
            if not value or value == "":
                return False
        
        # Verificar tipo_maquinaria
        tipo_maquinaria = current_state.get("tipo_maquinaria")
        if not tipo_maquinaria:
            return False
        
        # Verificar detalles de maquinaria
        detalles = current_state.get("detalles_maquinaria", {})
        
        if not detalles:
            return False
        
        # Usar la configuración centralizada para obtener campos obligatorios (con contexto)
        required_fields = self._get_contextual_required_fields(current_state)
        
        if not all(
            field in detalles and 
            detalles[field] is not None and 
            detalles[field] != ""
            for field in required_fields
        ):
            return False

        # Verificar si quiere cotización
        quiere_cot = current_state.get("quiere_cotizacion")
        if quiere_cot is None:
            return False
            
        if quiere_cot is True:
            # Reutilizamos get_pending_empresa_fields para validar
            if len(get_pending_empresa_fields(current_state)) > 0:
                return False

        return True

# ============================================================================
# SISTEMA DE RESPUESTAS INTELIGENTES
# ============================================================================

class IntelligentResponseGenerator:
    """Genera respuestas inteligentes basadas en el contexto y la información extraída"""
    
    def __init__(self, azure_config: AzureOpenAIConfig, cosmos_client=None, db_name=None):
        self.llm = azure_config.create_conversational_llm()  # Usar LLM optimizado para conversación
        self.inventory_service = InventoryService(cosmos_client, db_name)
    
    def generate_response(self, 
        message: str, 
        history_messages: List[Dict[str, Any]],
        extracted_info: Dict[str, Any], 
        current_state: ConversationState, 
        next_question: str = None, 
        is_inventory_question: bool = False,
        question_type: str = None
    ) -> str:
        """Genera una respuesta contextual apropiada usando un enfoque conversacional"""
        
        try:
            # Crear prompt conversacional basado en el estilo de llm.py
            # Crear prompt conversacional basado en el estilo de llm.py
            prompt = RESPONSE_GENERATION_PROMPT

            # Verificar si es el inicio de la conversación (menos de 2 elementos en history_messages)
            is_initial_conversation = len(history_messages) < 2
            
            # Instrucción de presentación obligatoria si es el inicio
            presentation_instruction = ""
            if is_initial_conversation:
                presentation_instruction = """
                
                PRESENTACIÓN:
                Presentate como Enrique Delfin, asesor comercial de Alpha C.
                Si en el primer mensaje del usuario este menciona que requiere algún producto o servicio, o solo quiere más información, dile "Hola, sí claro, puedo ayudarte con eso. Soy Enrique Delfin, asesor comercial de Alpha C." y luego haz la pregunta correspondiente.
                Si el usuario NO menciona ninguna necesidad (solo saluda o se presenta), dile "Hola, soy Enrique Delfin, asesor comercial de Alpha C." y luego haz la pregunta correspondiente.
                IMPORTANTE: SIEMPRE debes incluir tu nombre y cargo en el PRIMER mensaje.
                """

            # Instrucción para manejar el nombre y apellido del usuario
            extracted_name_instruction = ""

            # Preparar información extraída como string de manera más segura
            if not extracted_info:
                extracted_info_str = "Ninguna información nueva"
            else:
                # Filtrar información sensible antes de enviar
                safe_info = {}
                for key, value in extracted_info.items():
                    if key in ['apellido', 'correo', 'telefono']:
                        safe_info[key] = '[INFORMACIÓN PRIVADA]'
                    else:
                        safe_info[key] = value
                extracted_info_str = json.dumps(safe_info, ensure_ascii=False, indent=2)

                if extracted_info.get("nombre"):
                    nombre = extracted_info.get("nombre")
                    if is_initial_conversation:
                        extracted_name_instruction = f"El usuario ya proporcionó su nombre ({nombre}). Úsalo amablemente en tu saludo, PERO NO dejes de presentarte tú primero."
                    else:
                        extracted_name_instruction = f"El usuario acaba de decir su nombre, así que responde con un 'Gracias, {nombre}.' Y haz la siguiente pregunta."
                elif extracted_info.get("apellido"):
                    if is_initial_conversation:
                        extracted_name_instruction = "El usuario proporcionó su apellido. Tómalo en cuenta."
                    else:
                        extracted_name_instruction = "El usuario acaba de decir su apellido, así que responde con un 'Va.' Y haz la siguiente pregunta, no repitas el nombre ni apellido."
                else:
                    extracted_name_instruction = "No menciones el nombre ni apellido del usuario."

            if is_inventory_question:
                # Nombres de tipos de maquinaria
                # OBTENER DINÁMICAMENTE LOS NOMBRES DESDE LA CONFIGURACIÓN (Strings)
                maquinaria_names = ", ".join([f"\"{m.type_id}\"" for m in machinery_config_service.get_all_types()])
                
                # Cambiar torre_iluminacion por torre de iluminación y plataforma por plataforma de elevación
                maquinaria_names = maquinaria_names.replace("torre_iluminacion", "torre de iluminación")
                maquinaria_names = maquinaria_names.replace("plataforma", "plataforma de elevación")

                inventory_instruction = "Este mensaje del usuario incluye una pregunta sobre inventario, por lo tanto, a continuación te comparto los tipos de maquinaria que tenemos:" + maquinaria_names
            else:
                inventory_instruction = "Sigue las instrucciones dadas."

            # Instrucción especial para cuando se pregunta sobre cotización de maquinarias
            if question_type == "quiere_cotizacion":
                # START MODIFICATION: Lógica dinámica de recomendación
                machine_type = current_state.get("tipo_maquinaria")
                detalles = current_state.get("detalles_maquinaria", {})
                
                recommended_machines = []
                if machine_type:
                    recommended_machines = self.inventory_service.find_matching_machines(machine_type, detalles)
                
                if recommended_machines:
                    # Formatear lista de máquinas recomendadas
                    machines_list = ""
                    recommended_models = []  # Lista de modelos para guardar en el estado
                    for machine in recommended_machines[:3]: # Limitar a top 3
                         # Intentar construir un nombre descriptivo
                        modelo = machine.get("modelo", "Modelo Desconocido")
                        recommended_models.append(modelo)  # Guardar modelo
                        cat = machine.get("categoria", "")
                        
                        # Agregar detalles clave según el tipo (simplificado)
                        extra_info = _format_machine_details(machine)
                        
                        # NOTE: Prices are NOT shown in recommendations.
                        machines_list += f"- {modelo}{extra_info}\n"
                    
                    # Guardar la lista de modelos recomendados en el estado
                    current_state["maquinas_recomendadas"] = recommended_models
                    
                    intro_recomendacion = "la siguiente opción disponible" if len(recommended_models) == 1 else "las siguientes opciones disponibles"
                    
                    if current_state.get("quiere_cotizacion") is True:
                        cierre_cotizacion = "Para la cotización que solicitaste, ¿te interesa esta opción?" if len(recommended_models) == 1 else "Para la cotización que solicitaste, ¿te interesa alguna de estas opciones?"
                        return f"""Muy bien, basándome en tus requerimientos, te recomiendo {intro_recomendacion} en nuestro inventario:
{machines_list}

{cierre_cotizacion}"""
                    else:
                        cierre_cotizacion = "¿Te gustaría recibir una cotización formal por esta?" if len(recommended_models) == 1 else "¿Te gustaría recibir una cotización formal por alguna de estas?"
                        return f"""Muy bien, basándome en tus requerimientos, te recomiendo {intro_recomendacion} en nuestro inventario:
{machines_list}
{cierre_cotizacion}"""
                else:
                     # Fallback si no hay coincidencias exactas
                    if current_state.get("quiere_cotizacion") is True:
                        return """Entendido. No manejamos una máquina en el inventario con esas características, pero un asesor experto te buscará una alternativa para cotizarte."""
                    else:
                        return """Entendido. No manejamos una máquina en el inventario con esas características, pero tenemos muchas opciones que podrían adaptarse.
 
¿Te gustaría que un asesor te contacte para ofrecerte una solución personalizada?"""
                # END MODIFICATION
            
            # Instrucción especial para datos_empresa
            datos_empresa_instruction = ""
            pending_fields = []
            if question_type == "datos_empresa":
                pending_fields = get_pending_empresa_fields(current_state)
                if not pending_fields:
                    return ""
                
                # Agregar instrucción específica para datos_empresa
                datos_empresa_instruction = """
                
                INSTRUCCIÓN ESPECIAL PARA RECOPILAR DATOS:
                - Responde inteligentemente pero de forma BREVE al mensaje del usuario
                - Si el usuario pregunta algo, responde de manera natural y útil
                - Usa un mensaje como: """
                should_list_pending_fields = False
                uso = current_state.get("uso_empresa_o_venta")
                
                if not uso and "si te dedicas a la venta/renta de maquinaria" in pending_fields:
                    missing_str = "¿Te dedicas a la venta o renta de maquinaria?"
                    if "correo electrónico" in pending_fields and "ubicación (estado de la República Mexicana)" in pending_fields:
                         missing_str += " También me podrías compartir tu correo electrónico y ubicación (estado de la República Mexicana)."
                    elif "correo electrónico" in pending_fields:
                         missing_str += " También me podrías compartir tu correo electrónico."
                    elif "ubicación (estado de la República Mexicana)" in pending_fields:
                         missing_str += " También me podrías compartir tu ubicación (estado de la República Mexicana)."
                    datos_empresa_instruction += f"{missing_str}"
                
                elif "Constancia de Situación Fiscal" in pending_fields and len(pending_fields) == 1:
                    datos_empresa_instruction += "Pide ÚNICAMENTE la Constancia de Situación Fiscal. EXPRESAMENTE PROHIBIDO pedir otro dato como nombre de empresa, teléfono o correo. Usa este mensaje exacto: 'Perfecto, para poder brindarle un precio preferencial como distribuidor, le pido de favor que me comparta por este medio su Constancia de Situación Fiscal.'"
                
                elif pending_fields == ["Giro de la empresa"]:
                    datos_empresa_instruction += "Pregunta ÚNICAMENTE por el giro de la empresa usando un mensaje como: 'Para continuar, ¿me podrías indicar cuál es el giro de tu empresa?' No uses viñetas."
                    should_list_pending_fields = False
                    
                elif pending_fields == ["Nombre de la empresa"]:
                    datos_empresa_instruction += "Pregunta ÚNICAMENTE por el nombre de la empresa usando un mensaje como: 'Para generar la cotización, ¿me podrías indicar el nombre de tu empresa?' No uses viñetas."
                    should_list_pending_fields = False

                else:
                    datos_empresa_instruction += "Para poder generar la cotización, necesito que me comparta el siguiente dato (o datos):"
                    should_list_pending_fields = True
                
                if should_list_pending_fields:
                    pending_fields_bullets = "\n".join([f"- {f}" for f in pending_fields])
                    datos_empresa_instruction += f"""
                - Menciona EXPLÍCITAMENTE los campos que faltan (en viñetas) y pídelos en este mismo mensaje, en este orden:
{pending_fields_bullets}
                - Si el usuario ya contestó alguno de estos campos en su último mensaje, NO lo repitas ni lo vuelvas a pedir.
                - NUNCA inventes campos adicionales (por ejemplo: teléfono) si no están en la lista.
                - IMPORTANTE: NO te despidas, NO cierres la conversación.
                    """
                else:
                    datos_empresa_instruction += """
                - NUNCA menciones los campos pendientes en tu respuesta, solo responde con la introducción
                - NUNCA menciones información que se extrajo previamente, ni confirmes la información recién extraída, a menos de que el usuario lo pregunte
                - IMPORTANTE: NO te despidas, NO digas 'Perfecto, con esto terminamos', NO digas 'Gracias por la información' como cierre.
                - Debes dejar claro que FALTAN datos y que la conversación continúa.
                    """

            tipo_ayuda_instruction = ""
            if question_type == "tipo_ayuda":
                tipo_ayuda_instruction = "IMPORTANTÍSIMO: Cuando vayas a preguntar en qué le puedes ayudar al usuario, EXCLUSIVAMENTE usa la frase: '¿En qué te puedo ayudar?' de forma literal y directa, sin agregar texto adicional a la pregunta."

            current_state_str = get_current_state_str(current_state)
            formatedPrompt = prompt.format_prompt(
                user_message=message,
                current_state_str=current_state_str,
                history_messages=history_messages,
                extracted_info_str=extracted_info_str,
                next_question=next_question or "No hay siguiente pregunta",
                inventory_instruction=inventory_instruction,
                presentation_instruction=presentation_instruction,
                extracted_name_instruction=extracted_name_instruction,
                datos_empresa_instruction=datos_empresa_instruction,
                tipo_ayuda_instruction=tipo_ayuda_instruction
            )

            debug_print(f"DEBUG: Prompt conversacional: {formatedPrompt}")
            
            response = self.llm.invoke(formatedPrompt)
            
            result = response.content.strip()
            debug_print(f"DEBUG: Respuesta conversacional generada: '{result}'")
            
            # Ya no agreamos la lista de campos pendientes hardcoded,
            # porque el LLM ya incorpora la pregunta dentro del propio texto.
            
            return result
            
        except Exception as e:
            logging.error(f"Error generando respuesta conversacional: {e}")
            # Fallback a la lógica simple si no se puede generar la respuesta
            if next_question:
                return next_question
            else:
                return "En un momento le responderemos."
    
    def generate_final_response(self, current_state: ConversationState) -> str:
        """Genera la respuesta final cuando la conversación está completa"""
        
        uso = current_state.get("uso_empresa_o_venta")
        constancia = current_state.get("constancia_fiscal_entregada")
        giro = current_state.get("giro_empresa", "")
        
        is_advisor_handoff = False
        if uso == "venta":
            if constancia and constancia != "No tiene":
                is_advisor_handoff = True
            elif (constancia == "No tiene" or constancia is False) and giro and _is_distribuidor(giro):
                is_advisor_handoff = True
                
        if is_advisor_handoff:
            return "En un momento te contactará el asesor de la zona para darle el precio preferencial."

        from pricing_service import get_pricing_service
        
        # Fetch price for the selected machine only
        pricing_str = ""
        maquina_seleccionada = current_state.get("maquina_seleccionada")
        
        logging.info(f"[PRICING_DEBUG] generate_final_response: maquina_seleccionada = '{maquina_seleccionada}'")
        
        if maquina_seleccionada:
            try:
                pricing_service = get_pricing_service()
                logging.info(f"[PRICING_DEBUG] generate_final_response: pricing_service.is_available() = {pricing_service.is_available()}")
                price_info = pricing_service.get_price(maquina_seleccionada)
                
                logging.info(f"[PRICING_DEBUG] generate_final_response: price_info = {price_info}")
                
                if price_info:
                    precio = price_info["price"]
                    moneda = price_info.get("currency", "USD")
                    pricing_str = f"\n\nMáquina seleccionada:\n- {maquina_seleccionada}: ${precio:,.0f} {moneda}"
                    logging.info(f"[PRICING_DEBUG] generate_final_response: Price FOUND - ${precio:,.0f} {moneda}")
                else:
                    pricing_str = f"\n\nMáquina seleccionada:\n- {maquina_seleccionada}: Precio a consultar"
                    logging.warning(f"[PRICING_DEBUG] generate_final_response: No price found for '{maquina_seleccionada}'")
            except Exception as e:
                logging.error(f"[PRICING_DEBUG] generate_final_response: EXCEPTION fetching price: {type(e).__name__}: {e}")
                import traceback
                logging.error(f"[PRICING_DEBUG] generate_final_response: Traceback: {traceback.format_exc()}")
                pricing_str = f"\n\nMáquina seleccionada:\n- {maquina_seleccionada}"
        
        return f"""¡Perfecto, {current_state.get('nombre', 'Usuario')}!{pricing_str}

Procederé a generar su cotización."""

# ============================================================================
# RESPONDEDOR DE INVENTARIO
# ============================================================================

class InventoryResponder:
    """Responde preguntas sobre el inventario de maquinaria"""
    
    def __init__(self, azure_config: AzureOpenAIConfig):
        self.llm = azure_config.create_inventory_llm()  # Usar LLM optimizado para inventario
        self.inventory = get_inventory() # TODO: Mover esto también a DB si es necesario, por ahora usa el fake

    def is_inventory_question(self, message: str) -> bool:
        """Determina si el mensaje del usuario es una pregunta sobre el inventario"""
        try:
            prompt = INVENTORY_DETECTION_PROMPT
            
            response = self.llm.invoke(prompt.format_prompt(
                message=message
            ))
            
            result = response.content.strip().lower()
            
            debug_print(f"DEBUG: ¿Es pregunta sobre inventario? '{message}' → {result}")
            
            return result == "true"
            
        except Exception as e:
            logging.error(f"Error detectando pregunta de inventario: {e}")
            import traceback
            traceback.print_exc()
            return False

# ============================================================================
# CLASE PRINCIPAL DEL CHATBOT CON SLOT-FILLING INTELIGENTE
# ============================================================================

class IntelligentLeadQualificationChatbot:
    """Chatbot con slot-filling inteligente que detecta información ya proporcionada"""
    
    def __init__(self, azure_config: AzureOpenAIConfig, state_store: Optional[ConversationStateStore] = None, send_message_callback=None, send_pdf_callback=None, cosmos_client=None, db_name=None):
        self.azure_config = azure_config
        # Crear instancias con configuraciones específicas para cada propósito
        self.slot_filler = IntelligentSlotFiller(azure_config)
        self.response_generator = IntelligentResponseGenerator(azure_config, cosmos_client, db_name)
        self.inventory_responder = InventoryResponder(azure_config)
        
        # Usar el state_store proporcionado o crear uno en memoria por defecto
        self.state_store = state_store or InMemoryStateStore()
        self.current_user_id = None
        
        # Callback para enviar mensajes por WhatsApp
        self.send_message_callback = send_message_callback
        
        # Callback para enviar PDFs por WhatsApp
        self.send_pdf_callback = send_pdf_callback
        
        # El estado local sigue existiendo para compatibilidad con código existente
        self.state = self._create_empty_state()

    def _create_empty_state(self) -> ConversationState:
        """Crea un estado vacío"""
        state = {
            # Campos que no se preguntan al usuario
            "completed": False,
            "messages": [],
            "conversation_mode": "bot", # agente o bot
            "asignado_asesor": None,
            "hubspot_contact_id": None,
            "quiere_cotizacion": None,
            "maquinas_recomendadas": []  # Lista de máquinas recomendadas para mapear posición a modelo
        }
        
        # Agregamos los campos que se preguntan al usuario desde el FIELDS_CONFIG_PRIORITY
        fields_to_ask = [field for field in FIELDS_CONFIG_PRIORITY.keys()]
        for field in fields_to_ask:
            if field == "detalles_maquinaria":
                state[field] = {}
            else:
                state[field] = None


        return state
    
    def load_conversation(self, user_id: str):
        """Carga la conversación de un usuario específico"""
        logging.info(f"Cargando conversación para usuario {user_id}")
        self.current_user_id = user_id
        stored_state = self.state_store.get_conversation_state(user_id)
        
        if stored_state:
            self.state = stored_state
            debug_print(f"DEBUG: Estado cargado para usuario {user_id}")
        else:
            logging.info(f"No hay estado existente para usuario {user_id}, creando nuevo estado")
            self.state = self._create_empty_state()
            debug_print(f"DEBUG: Nuevo estado creado para usuario {user_id}")

    def save_conversation(self):
        """Guarda el estado actual de la conversación"""
        if self.current_user_id:
            self.state_store.save_conversation_state(self.current_user_id, self.state)
            debug_print(f"DEBUG: Estado guardado para usuario {self.current_user_id}")

    def reset_conversation(self):
        """Reinicia el estado de la conversación"""
        if self.current_user_id:
            self.state_store.delete_conversation_state(self.current_user_id)
        self.state = self._create_empty_state()
    
    def _get_final_response_message(self) -> str:
        """
        Determina el mensaje final basado en el tipo_ayuda del estado actual.
        Retorna un mensaje diferente si el usuario necesita algo diferente a maquinaria.
        """
        tipo_ayuda = self.state.get("tipo_ayuda")
        if tipo_ayuda == "otro":
            return "Claro, en un momento te comparto la información."
        else:
            return "Gracias por la información. Pronto te contactará nuestro asesor especializado."
    
    def send_message(self, user_message: str, whatsapp_message_id: str = None, hubspot_manager: HubSpotManager = None) -> str:
        """
        Procesa un mensaje del usuario con slot-filling inteligente.
        Si hubspot_manager es None, no se actualiza el contacto en HubSpot (para poder usar test_chatbot.py)
        """
        
        try:
            debug_print(f"DEBUG: send_message llamado con mensaje: '{user_message}'")
            
            # Si el mensaje está vacío, no hacer nada y esperar al usuario
            if not user_message or not user_message.strip():
                return None
            
            # Mensaje que se regresa
            contextual_response = ""
            
            # Agregar mensaje del usuario
            self.state["messages"].append({
                "role": "user", 
                "whatsapp_message_id": whatsapp_message_id,
                "content": user_message,
                "question_type": "",
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sender": "lead"
            })

            # Extraer TODA la información disponible del mensaje (SIEMPRE)
            # Obtener la última pregunta del bot para contexto
            last_bot_question, _ = self._get_last_bot_question()
            extracted_info = self.slot_filler.extract_all_information(user_message, self.state, last_bot_question)
            debug_print(f"DEBUG: Información extraída: {extracted_info}") 
            
            # Actualizar el contacto en HubSpot
            if hubspot_manager:
                hubspot_manager.update_contact(self.state, extracted_info)

            # Actualizar el estado con la información extraída
            self._update_state_with_extracted_info(extracted_info)

            # Verificar modo de conversación antes de generar respuesta
            current_mode = self.state.get("conversation_mode", "bot")
            
            if current_mode == "agente":
                # Modo agente: solo guardar estado, no generar respuesta automática
                debug_print(f"DEBUG: Modo agente activo, no generando respuesta automática")
                self.save_conversation()
                return None  # No response en modo agente
            
            return self._process_and_respond(user_message, extracted_info)
        
        except Exception as e:
            logging.error(f"Error procesando mensaje: {e}")
            return "Disculpe, hubo un error técnico. ¿Podría intentar de nuevo?"

    def _process_and_respond(self, user_message: str, extracted_info: Dict[str, Any]) -> str:
        """
        Lógica común para procesar un mensaje y generar una respuesta.
        Detecta preguntas de inventario, verifica si la conversación está completa,
        obtiene la siguiente pregunta y genera la respuesta con LLM.
        """
        is_inventory_question = False

        # Verificar si es una pregunta sobre inventario
        if self.inventory_responder.is_inventory_question(user_message):
            debug_print(f"DEBUG: Pregunta sobre inventario detectada")
            is_inventory_question = True
        
        # Si no es pregunta de inventario ni de requerimientos, continuar con el flujo normal
        debug_print(f"DEBUG: Flujo normal de calificación de leads...")

        # Preparar historial de mensajes para el LLM
        history_messages = [{
            "role": msg["role"],
            "content": msg["content"]
        } for msg in self.state["messages"]]

        next_question_str = None
        next_question_type = "conversation_complete"
        # Por defecto, si la conversación está completa, guardamos tipo vacío o un marcador
        storage_question_type = "" 

        # 1. Verificar si la conversación YA estaba marcada como completa o cumple condiciones
        if self.slot_filler.is_conversation_complete(self.state):
            debug_print(f"DEBUG: Conversación completa!")
            self.state["completed"] = True
            # Se usan los valores por defecto (None, conversation_complete)
        
        else:
            # 2. Si no está completa, buscar siguiente pregunta
            next_question_data = self.slot_filler.get_next_question(self.state)

            if next_question_data is None:
                debug_print(f"DEBUG: Estado completo (sin siguiente pregunta): {self.state}")
                
                # Caso especial: Si el usuario dijo "no" a la cotización
                quiere_cot = self.state.get("quiere_cotizacion")
                if quiere_cot is False:
                    self.state["completed"] = True
                    final_message = "Okay, ¿hay algo más en lo que te pueda ayudar?"
                    return self._add_message_and_return_response(final_message, "")
                
                self.state["completed"] = True
                # Se usan los valores por defecto
            else:
                # 3. Hay una siguiente pregunta
                next_question_str = next_question_data["question"]
                next_question_type = next_question_data['question_type']
                storage_question_type = next_question_type

                debug_print(f"DEBUG: Siguiente pregunta: {next_question_str}")
                debug_print(f"DEBUG: Tipo de siguiente pregunta: {next_question_type}")

        # If conversation is complete, use the final response with prices
        if self.state.get("completed") and next_question_str is None:
            final_response = self.response_generator.generate_final_response(self.state)
            result = self._add_message_and_return_response(final_response, storage_question_type)
            
            # Generate and send PDF quotation if applicable
            self._try_send_pdf_quotation()
            
            return result

        # Generar respuesta con LLM (Llamada unificada)
        generated_response = self.response_generator.generate_response(
            user_message, 
            history_messages,
            extracted_info, 
            self.state, 
            next_question=next_question_str, 
            is_inventory_question=is_inventory_question,
            question_type=next_question_type
        )
        
        return self._add_message_and_return_response(generated_response, storage_question_type)
        
    def _add_message_and_return_response(self, response: str, question_type: str) -> str:
        """
        Añade un mensaje al estado y devuelve la respuesta final
        Si es un mensaje del bot y hay callback disponible, envía por WhatsApp primero
        """
        whatsapp_message_id = ""
        
        # Enviar mensaje por WhatsApp primero
        try:
            whatsapp_message_id = self.send_message_callback(self.current_user_id, response)
            debug_print(f"DEBUG: Mensaje enviado por WhatsApp con ID: {whatsapp_message_id}")
        except Exception as e:
            debug_print(f"DEBUG: Error enviando mensaje por WhatsApp: {e}")
            # Continuar sin el ID si hay error
        
        # Crear el mensaje con el ID de WhatsApp       
        self.state["messages"].append({
            "role": "assistant", 
            "whatsapp_message_id": whatsapp_message_id,
            "question_type": question_type,
            "content": response,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sender": "bot"
        })
        
        # Al final, guardar el estado
        self.save_conversation()

        return response

    def _try_send_pdf_quotation(self):
        """
        Attempts to generate and send a PDF quotation via WhatsApp.
        Only triggers when:
        - quiere_cotizacion is True
        - maquina_seleccionada is set
        - send_pdf_callback is available (running in WhatsApp context)
        """
        try:
            # Check conditions
            if not self.state.get("quiere_cotizacion"):
                logging.info("[PDF] Skipping PDF: quiere_cotizacion is not True")
                return

            if self.state.get("uso_empresa_o_venta") == "venta":
                logging.info("[PDF] Skipping PDF: uso is 'venta', handoff triggered instead.")
                return
            
            maquina = self.state.get("maquina_seleccionada")
            if not maquina:
                logging.info("[PDF] Skipping PDF: no maquina_seleccionada in state")
                return
            
            if not self.send_pdf_callback:
                logging.info("[PDF] Skipping PDF: no send_pdf_callback (test mode)")
                return
            
            if not self.current_user_id:
                logging.warning("[PDF] Skipping PDF: no current_user_id set")
                return
            
            logging.info(f"[PDF] Starting PDF generation for machine: {maquina}, user: {self.current_user_id}")
            
            # Get price info
            from pricing_service import get_pricing_service
            price_info = None
            try:
                pricing_service = get_pricing_service()
                price_info = pricing_service.get_price(maquina)
                logging.info(f"[PDF] Price info retrieved: {price_info}")
            except Exception as e:
                logging.warning(f"[PDF] Could not fetch price for PDF: {e}")
            
            # Generate PDF
            from pdf_service import get_pdf_generator
            generator = get_pdf_generator()
            pdf_bytes = generator.generate(self.state, price_info)
            logging.info(f"[PDF] PDF generated successfully, size: {len(pdf_bytes)} bytes")
            
            # Build filename
            safe_machine_name = maquina.replace(" ", "_").replace("/", "-")
            filename = f"Cotizacion_{safe_machine_name}.pdf"
            
            # Send via WhatsApp
            logging.info(f"[PDF] Sending PDF '{filename}' to {self.current_user_id}")
            result = self.send_pdf_callback(self.current_user_id, pdf_bytes, filename)
            
            if result:
                logging.info(f"[PDF] PDF quotation sent successfully. WhatsApp message_id: {result}")
            else:
                logging.error(f"[PDF] send_pdf_callback returned None/empty for {self.current_user_id}")
            
        except Exception as e:
            logging.error(f"[PDF] Error generating/sending PDF quotation: {e}")
            import traceback
            logging.error(f"[PDF] Traceback: {traceback.format_exc()}")
    
    def _update_state_with_extracted_info(self, extracted_info: Dict[str, Any]):
        """
        Actualiza el estado con la información extraída, confiando en el 
        pre-procesamiento y formato realizado por el LLM.
        """
        debug_print(f"DEBUG: Actualizando estado con información: {extracted_info}")
        for key, value in extracted_info.items():
            # 1. Ignorar valores nulos o vacíos para no insertar datos inútiles.
            if value is None or value == "":
                continue

            # 2. No sobrescribir campos que ya tienen un valor válido a excepción de:
            # - detalles_maquinaria: se actualiza múltiples veces porque tiene varios subcampos.
            # - quiere_cotizacion: puede cambiar si el usuario corrige su respuesta.
            # - maquina_seleccionada: puede cambiar si el usuario elige otra máquina.
            # - tipo_maquinaria: puede cambiar si el usuario cambia de opinión.
            # Esto es clave para evitar que una respuesta ambigua posterior
            # borre un dato que ya se había confirmado.
            current_value = self.state.get(key)
            if key not in ["detalles_maquinaria", "quiere_cotizacion", "maquina_seleccionada", "tipo_maquinaria"] and current_value:
                debug_print(f"DEBUG: Campo '{key}' ya tiene valor válido '{current_value}', no se sobrescribe.")
                continue

            # 3. Manejo de casos especiales
            if key == "detalles_maquinaria" and isinstance(value, dict):
                current_detalles = self.state.get("detalles_maquinaria", {})
                current_detalles.update(value)
                self.state["detalles_maquinaria"] = current_detalles
                debug_print(f"DEBUG: Detalles de maquinaria actualizados: {self.state['detalles_maquinaria']}")
            
            elif key == "tipo_maquinaria":
                # Validar dinámicamente si el tipo existe en la configuración
                config = machinery_config_service.get_config(value)
                if config:
                    old_tipo = self.state.get("tipo_maquinaria")
                    self.state[key] = value
                    debug_print(f"DEBUG: Campo '{key}' actualizado a: {value}")
                    
                    # Si el tipo de maquinaria CAMBIÓ, limpiar campos relacionados
                    if old_tipo and old_tipo != value:
                        debug_print(f"DEBUG: Tipo de maquinaria cambió de '{old_tipo}' a '{value}'. Limpiando detalles, recomendaciones y selección.")
                        self.state["detalles_maquinaria"] = {}
                        self.state["maquinas_recomendadas"] = []
                        self.state["maquina_seleccionada"] = None
                        self.state["quiere_cotizacion"] = None
                else:
                    logging.error(f"ADVERTENCIA: Tipo de maquinaria inválido '{value}' extraído por el LLM.")
            
            elif key == "apellido":
                # Combinar nombre y apellido en el campo nombre
                nombre_actual = self.state.get("nombre", "")
                if nombre_actual and value:
                    self.state["nombre"] = f"{nombre_actual} {value}".strip()
                    self.state["apellido"] = value 
                    debug_print(f"DEBUG: Nombre y apellido combinados: '{self.state['nombre']}'")
                else:
                    self.state[key] = value
                    debug_print(f"DEBUG: Campo '{key}' actualizado con valor: '{value}'")
            
            # 4. Para todos los demás campos, la actualización es directa.
            # Se confía en que el LLM ya formateó la respuesta según las reglas del prompt.
            else:
                self.state[key] = value
                debug_print(f"DEBUG: Campo '{key}' actualizado con valor: '{value}'")
        
        # Lógica de inferencia post-extracción
        # Si tenemos tipo_maquinaria pero no tipo_ayuda, inferimos que es "maquinaria"
        if self.state.get("tipo_maquinaria") and not self.state.get("tipo_ayuda"):
            self.state["tipo_ayuda"] = "maquinaria"
            debug_print("DEBUG: Inferido tipo_ayuda='maquinaria' basado en presencia de tipo_maquinaria")
        
        # Si el LLM extrajo maquina_seleccionada, inferir quiere_cotizacion=True
        # (seleccionar una máquina implica querer cotización)
        if self.state.get("maquina_seleccionada") and not self.state.get("quiere_cotizacion"):
            self.state["quiere_cotizacion"] = True
            debug_print("DEBUG: Inferido quiere_cotizacion=True por selección de máquina")
        
        # Resolve partial model names against recommended machines
        # e.g. "X-START" → "Trime X-START", "DGM250MK-D" → "Shindaiwa DGM250MK-D"
        maquina_sel = self.state.get("maquina_seleccionada")
        maquinas_recomendadas = self.state.get("maquinas_recomendadas", [])
        if maquina_sel and maquinas_recomendadas:
            partial_lower = maquina_sel.lower().strip()
            for full_model in maquinas_recomendadas:
                if partial_lower in full_model.lower() and partial_lower != full_model.lower():
                    debug_print(f"DEBUG: maquina_seleccionada resolved: '{maquina_sel}' → '{full_model}'")
                    self.state["maquina_seleccionada"] = full_model
                    break
        
    def _get_last_bot_question(self) -> Tuple[Optional[str], Optional[str]]:
        """Obtiene la última pregunta que hizo el bot para proporcionar contexto"""
        try:
            # Buscar el último mensaje del bot en el historial
            for msg in reversed(self.state["messages"]):
                if msg["role"] == "assistant" or msg["sender"] == "bot":
                    content = msg["content"]
                    question_type = msg["question_type"]
                    # Si el mensaje contiene una pregunta, extraerla
                    if "?" in content:
                        # Buscar la última línea que contenga una pregunta
                        lines = content.split('\n')
                        for line in reversed(lines):
                            if "?" in line and line.strip():
                                return line.strip(), question_type
                        # Si no se encuentra una línea específica, devolver todo el contenido
                        return content, question_type
                    return content, question_type
            return None, None
        except Exception as e:
            logging.error(f"Error obteniendo última pregunta del bot: {e}")
            return None, None
    
    def get_lead_data_json(self) -> str:
        """Obtiene los datos del lead en formato JSON"""
        return json.dumps(get_current_state_str(self.state), indent=2, ensure_ascii=False)
    
    def process_last_lead_message(self, wa_id: str) -> Optional[str]:
        """
        Procesa el último mensaje del lead y genera una respuesta contextual.
        Esta función es específica para el endpoint /start-bot-mode.
        """
        try:
            debug_print(f"DEBUG: Procesando último mensaje del lead para {wa_id}")

            self.load_conversation(wa_id)
                        
            # Verificar que hay mensajes en la conversación
            messages = self.state.get("messages", [])
            if not messages:
                debug_print(f"DEBUG: No hay mensajes en la conversación para {wa_id}")
                return None
            
            # Obtener el último mensaje
            last_message = messages[-1]
            
            # Verificar que el último mensaje sea del lead
            if last_message.get("sender") != "lead" and last_message.get("role") != "user":
                debug_print(f"DEBUG: El último mensaje no es del lead para {wa_id}")
                return None
            
            # Obtener el contenido del mensaje
            message_content = last_message.get("content", "")
            if not message_content or not message_content.strip():
                debug_print(f"DEBUG: El último mensaje del lead está vacío para {wa_id}")
                return None
            
            debug_print(f"DEBUG: Procesando mensaje del lead: '{message_content}'")
            
            return self._process_and_respond(message_content, {})
            
        except Exception as e:
            logging.error(f"Error procesando último mensaje del lead: {e}")
            return "Disculpe, hubo un error técnico. ¿Podría intentar de nuevo?"