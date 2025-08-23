import json
import os
from typing import TypedDict, Dict, Any, Optional, List
from enum import Enum
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
import langchain

langchain.debug = False
langchain.verbose = False
langchain.llm_cache = False

# ============================================================================
# CONFIGURACIÓN DE DEBUG
# ============================================================================

# Variable global para controlar si se muestran los prints de DEBUG
DEBUG_MODE = False

def debug_print(*args, **kwargs):
    """
    Función helper para imprimir mensajes de DEBUG solo cuando DEBUG_MODE es True
    """
    if DEBUG_MODE:
        print(*args, **kwargs)

# ============================================================================
# INVENTARIO FAKE
# ============================================================================

def get_inventory():
    return {
        "tipo_maquinaria": [
            "soldadoras",
            "compresor",
            "torre_iluminacion",
            "lgmg",
            "generadores",
            "rompedores"
        ],
        "modelo_maquinaria": "Cualquier modelo",
        "ubicacion": "Cualquier ubicación en México",
    }

# ============================================================================
# MODELOS DE DATOS
# ============================================================================

class MaquinariaType(str, Enum):
    SOLDADORAS = "soldadoras"
    COMPRESOR = "compresor"
    TORRE_ILUMINACION = "torre_iluminacion"
    LGMG = "lgmg"
    GENERADORES = "generadores"
    ROMPEDORES = "rompedores"

class DetallesSoldadora(BaseModel):
    amperaje: Optional[str] = Field(None, description="Amperaje requerido para la soldadora")
    electrodo: Optional[str] = Field(None, description="Tipo de electrodo que quema")

class DetallesCompresor(BaseModel):
    capacidad_volumen: Optional[str] = Field(None, description="Capacidad de volumen de aire requerida")
    herramientas: Optional[str] = Field(None, description="Herramientas que va a conectar")

class DetallesTorre(BaseModel):
    es_led: Optional[bool] = Field(None, description="Si requiere LED o no")
    modelo_recomendado: Optional[str] = Field(None, description="Modelo recomendado según preferencias")

class DetallesLGMG(BaseModel):
    altura_trabajo: Optional[str] = Field(None, description="Altura de trabajo necesaria")
    actividad: Optional[str] = Field(None, description="Actividad que va a realizar")
    ubicacion: Optional[str] = Field(None, description="Si es en interior o exterior")

class DetallesGenerador(BaseModel):
    actividad: Optional[str] = Field(None, description="Para qué actividad lo requiere")
    capacidad: Optional[str] = Field(None, description="Capacidad en kvas o kw necesaria")
    necesita_recibo_luz: Optional[bool] = Field(None, description="Si necesita recibo de luz para calcular")

class DetallesRompedor(BaseModel):
    uso: Optional[str] = Field(None, description="Para qué lo va a utilizar")
    tipo: Optional[str] = Field(None, description="Si lo requiere eléctrico o neumático")
    opciones_disponibles: Optional[str] = Field(None, description="Opciones disponibles según tipo")

class ConversationState(TypedDict):
    messages: List[Dict[str, str]]
    nombre: Optional[str]
    tipo_maquinaria: Optional[MaquinariaType]
    detalles_maquinaria: Dict[str, Any]
    sitio_web: Optional[str]
    uso_empresa_o_venta: Optional[str]
    nombre_completo: Optional[str]
    nombre_empresa: Optional[str]
    giro_empresa: Optional[str]
    correo: Optional[str]
    telefono: Optional[str]
    completed: bool

# ============================================================================
# CONFIGURACIÓN DE AZURE OPENAI
# ============================================================================

class AzureOpenAIConfig:
    """Clase para manejar la configuración de Azure OpenAI"""
    
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
    
    def create_llm(self, temperature: float = 0.3, max_tokens: int = 1000):
        """Crea una instancia de AzureChatOpenAI"""
        return AzureChatOpenAI(
            azure_endpoint=self.endpoint,
            api_key=self.api_key,
            azure_deployment=self.deployment_name,
            api_version=self.api_version,
            model_name=self.model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=60,
            max_retries=3,
            verbose=True
        )

# ============================================================================
# SISTEMA DE SLOT-FILLING INTELIGENTE
# ============================================================================

class IntelligentSlotFiller:
    """Sistema inteligente de slot-filling que detecta información ya proporcionada"""
    
    def __init__(self, llm):
        self.llm = llm
        self.parser = JsonOutputParser()
        
    def extract_all_information(self, message: str, current_state: ConversationState, last_bot_question: Optional[str] = None) -> Dict[str, Any]:
        """
        Extrae TODA la información disponible en un solo mensaje
        Detecta qué slots se pueden llenar y cuáles ya están completos
        Incluye el contexto de la última pregunta del bot para mejor interpretación
        """
        
        # Crear prompt que considere el estado actual y la última pregunta del bot
        prompt = ChatPromptTemplate.from_template(
            """
            Eres un asistente experto en extraer información de mensajes de usuarios.
            
            Analiza el mensaje del usuario y extrae TODA la información disponible.
            Solo extrae campos que NO estén ya completos en el estado actual.
            
            ESTADO ACTUAL:
            - nombre: {current_nombre}
            - tipo_maquinaria: {current_tipo}
            - detalles_maquinaria: {current_detalles}
            - sitio_web: {current_sitio_web}
            - uso_empresa_o_venta: {current_uso}
            - nombre_completo: {current_nombre_completo}
            - nombre_empresa: {current_nombre_empresa}
            - giro_empresa: {current_giro}
            - correo: {current_correo}
            - telefono: {current_telefono}
            
            ÚLTIMA PREGUNTA DEL BOT: {last_bot_question}
            
            MENSAJE DEL USUARIO: {message}
            
            INSTRUCCIONES:
            1. Solo extrae campos que estén VACÍOS en el estado actual
            2. Si un campo ya tiene valor, NO lo incluyas en la respuesta
            3. Para detalles_maquinaria, solo incluye campos específicos que no estén ya llenos
            4. Responde SOLO en formato JSON válido
            5. IMPORTANTE: Si el mensaje del usuario no contiene información nueva para campos vacíos, responde con {{}} (JSON vacío)
            6. NO extraigas información de campos que ya están llenos, incluso si el usuario dice algo que podría interpretarse como información
            7. CONTEXTO DE LA ÚLTIMA PREGUNTA: Usa la última pregunta del bot para interpretar mejor la respuesta del usuario
            8. CLASIFICACIÓN INTELIGENTE: Si la última pregunta es sobre un campo específico, clasifica la respuesta en ese campo
            
            CAMPOS A EXTRAER (solo si están vacíos):
            - nombre: nombre de la persona
            - tipo_maquinaria: soldadoras, compresor, torre_iluminacion, lgmg, generadores, rompedores
            - detalles_maquinaria: objeto con campos específicos según tipo_maquinaria
            - sitio_web: URL del sitio web o "No tiene" (para respuestas negativas como "no", "no tenemos", "no cuenta", etc.)
            - uso_empresa_o_venta: "uso empresa" o "venta"
            - nombre_completo: nombre completo de la persona
            - nombre_empresa: nombre de la empresa
            - giro_empresa: giro o actividad de la empresa (ej: "venta de maquinaria", "construcción", "manufactura", "servicios", etc.)
            - correo: dirección de email
            - telefono: número telefónico
            
            REGLAS ESPECIALES PARA SITIO_WEB:
            - Si el usuario dice algo como "no", "no tenemos", "no hay", "no tenemos página", "no tenemos sitio", "no tenemos página web" → sitio_web: "No tiene"
            - Si el usuario proporciona una URL o sitio web → sitio_web: [URL]
            - Si el usuario dice "solo facebook", "solo instagram", "solo redes sociales" → sitio_web: "No tiene"
            
            REGLAS ESPECIALES PARA TODOS LOS CAMPOS:
            - Si el usuario dice "no tengo", "no sé", "no estoy seguro", "no lo sé", "no tengo idea", "aún no lo he decidido" → usar "No especificado" como valor
            - Si el usuario dice "no quiero dar esa información", "prefiero no decir", "es confidencial" → usar "No especificado" como valor
            - Si el usuario dice "no tengo correo", "no tengo teléfono", "no tengo empresa" → usar "No tiene" como valor
            
            REGLAS ESPECIALES PARA GIRO_EMPRESA:
            - Si el usuario describe la actividad de su empresa → giro_empresa: [descripción de la actividad]
            - Ejemplos: "venta de maquinaria pesada", "construcción", "manufactura", "servicios de mantenimiento", "distribución", "logística", etc.
            - Extrae la actividad principal, no solo palabras sueltas
            
            REGLAS ESPECIALES PARA NOMBRES:
            - Si el usuario dice "soy [nombre]", "me llamo [nombre]", "hola, soy [nombre]" → extraer nombre y nombre_completo
            - Para nombres de 1-2 palabras: llenar solo "nombre"
            - Para nombres de 3+ palabras: llenar tanto "nombre" como "nombre_completo"
            - Ejemplos: "soy Paco Perez" → nombre: "Paco Perez"
            - Ejemplos: "soy Paco Perez Diaz" →  nombre: "Paco Perez Diaz" y nombre_completo: "Paco Perez Diaz"
            
            REGLAS ESPECIALES PARA USO_EMPRESA_O_VENTA:
            - Si el usuario dice "para venta", "es para vender", "para comercializar" → uso_empresa_o_venta: "venta"
            - Si el usuario dice "para uso", "para usar", "para trabajo interno" → uso_empresa_o_venta: "uso empresa"
            
            EJEMPLOS DE EXTRACCIÓN:
            - Mensaje: "soy Renato Fuentes" → {{"nombre": "Renato Fuentes", "nombre_completo": None}}
            - Mensaje: "me llamo Mauricio Martinez Rodriguez" → {{"nombre": "Mauricio Martinez Rodriguez", "nombre_completo": "Mauricio Martinez Rodriguez"}}
            - Mensaje: "no hay pagina web" → {{"sitio_web": "No tiene"}}
            - Mensaje: "venta de maquinaria pesada" → {{"giro_empresa": "venta de maquinaria pesada"}}
            - Mensaje: "para venta" → {{"uso_empresa_o_venta": "venta"}}
            - Mensaje: "construcción y mantenimiento" → {{"giro_empresa": "construcción y mantenimiento"}}
            - Mensaje: "daniel@empresa.com" → {{"correo": "daniel@empresa.com"}}
            - Mensaje: "555-1234" → {{"telefono": "555-1234"}}
            
            EJEMPLOS DE RESPUESTAS SIN INFORMACIÓN NUEVA:
            - Mensaje: "no se" → {{}} (no hay información nueva)
            - Mensaje: "aun no lo he decidido" → {{}} (no hay información nueva)
            - Mensaje: "no estoy seguro" → {{}} (no hay información nueva)
            - Mensaje: "no tengo idea" → {{}} (no hay información nueva)
            
            EJEMPLOS DE USO DEL CONTEXTO DE LA ÚLTIMA PREGUNTA:
            - Última pregunta: "¿En qué compañía trabajas?" + Mensaje: "Facebook" → {{"nombre_empresa": "Facebook"}}
            - Última pregunta: "¿Cuál es el giro de su empresa?" + Mensaje: "Construcción" → {{"giro_empresa": "Construcción"}}
            - Última pregunta: "¿Cuál es su correo electrónico?" + Mensaje: "daniel@empresa.com" → {{"correo": "daniel@empresa.com"}}
            - Última pregunta: "¿Es para uso de la empresa o para venta?" + Mensaje: "Para venta" → {{"uso_empresa_o_venta": "venta"}}
            - Última pregunta: "¿Su empresa cuenta con algún sitio web?" + Mensaje: "Solo Facebook" → {{"sitio_web": "No tiene"}}
            
            IMPORTANTE: Analiza cuidadosamente el mensaje y extrae TODA la información disponible que corresponda a campos vacíos.
            
            Respuesta (solo JSON):
            """
        )
        
        try:
            # Preparar el estado actual para el prompt
            current_detalles_str = json.dumps(current_state.get("detalles_maquinaria", {}), ensure_ascii=False)
            
            response = self.llm.invoke(prompt.format_prompt(
                message=message,
                current_nombre=current_state.get("nombre", "No especificado"),
                current_tipo=current_state.get("tipo_maquinaria", "No especificado"),
                current_detalles=current_detalles_str,
                current_sitio_web=current_state.get("sitio_web", "No especificado"),
                current_uso=current_state.get("uso_empresa_o_venta", "No especificado"),
                current_nombre_completo=current_state.get("nombre_completo", "No especificado"),
                current_nombre_empresa=current_state.get("nombre_empresa", "No especificado"),
                current_giro=current_state.get("giro_empresa", "No especificado"),
                current_correo=current_state.get("correo", "No especificado"),
                current_telefono=current_state.get("telefono", "No especificado"),
                last_bot_question=last_bot_question or "No hay pregunta previa (inicio de conversación)"
            ))
            
            debug_print(f"DEBUG: Respuesta completa del LLM: '{response.content}'")
            
            # Parsear la respuesta JSON
            result = self.parser.parse(response.content)
            debug_print(f"DEBUG: Información extraída por LLM: {result}")
            return result
            
        except Exception as e:
            print(f"Error extrayendo información: {e}")
            return {}
    
    def get_next_question(self, current_state: ConversationState) -> Optional[str]:
        """
        Determina inteligentemente cuál es la siguiente pregunta necesaria
        basándose en qué slots están vacíos
        """
        
        # Definir el orden de prioridad de los slots
        slot_priority = [
            ("nombre", "¿Con quién tengo el gusto?"),
            ("tipo_maquinaria", "¿Qué tipo de maquinaria ligera requiere?"),
            ("detalles_maquinaria", None),  # Se maneja por separado
            ("sitio_web", "¿Su empresa cuenta con algún sitio web? Si es así, ¿me lo podría compartir?"),
            ("uso_empresa_o_venta", "¿Es para uso de la empresa o para venta?"),
            ("nombre_completo", "¿Cuál es su nombre completo?"),
            ("nombre_empresa", "¿Cuál es el nombre de su empresa?"),
            ("giro_empresa", "¿Cuál es el giro o actividad de su empresa?"),
            ("correo", "¿Cuál es su correo electrónico?"),
            ("telefono", "¿Cuál es su número telefónico?")
        ]
        
        # Verificar cada slot en orden de prioridad
        for slot_name, default_question in slot_priority:
            if slot_name == "detalles_maquinaria":
                # Manejar detalles específicos de maquinaria
                question = self._get_maquinaria_detail_question(current_state)
                if question:
                    return question
            else:
                # Verificar si el slot está vacío o tiene respuestas negativas
                value = current_state.get(slot_name)
                if not value or value in ["No tiene", "No especificado"]:
                    return default_question
        
        # Si todos los slots están llenos
        return None
    
    def _get_maquinaria_detail_question(self, current_state: ConversationState) -> Optional[str]:
        """Obtiene la siguiente pregunta específica sobre detalles de maquinaria"""
        
        tipo = current_state.get("tipo_maquinaria")
        if not tipo:
            debug_print(f"DEBUG: No hay tipo de maquinaria definido")
            return None
            
        detalles = current_state.get("detalles_maquinaria", {})
        debug_print(f"DEBUG: Tipo de maquinaria: {tipo}, detalles actuales: {detalles}")
        
        # Preguntas específicas por tipo de maquinaria
        questions_map = {
            MaquinariaType.SOLDADORAS: [
                ("amperaje", "¿Qué amperaje requiere?"),
                ("electrodo", "¿Qué tipo de electrodo quema?")
            ],
            MaquinariaType.COMPRESOR: [
                ("capacidad_volumen", "¿Qué capacidad de volumen de aire requiere?"),
                ("herramientas", "¿Qué herramientas le va a conectar?")
            ],
            MaquinariaType.TORRE_ILUMINACION: [
                ("es_led", "¿La requiere de LED?")
            ],
            MaquinariaType.LGMG: [
                ("altura_trabajo", "¿Qué altura de trabajo necesita?"),
                ("actividad", "¿Qué actividad va a realizar?"),
                ("ubicacion", "¿Es en exterior o interior?")
            ],
            MaquinariaType.GENERADORES: [
                ("actividad", "¿Para qué actividad lo requiere?"),
                ("capacidad", "¿Qué capacidad en kvas o kw necesita?")
            ],
            MaquinariaType.ROMPEDORES: [
                ("uso", "¿Para qué lo va a utilizar?"),
                ("tipo", "¿Lo requiere eléctrico o neumático?")
            ]
        }
        
        questions = questions_map.get(tipo, [])
        debug_print(f"DEBUG: Preguntas disponibles para {tipo}: {questions}")
        
        # Buscar la primera pregunta que no esté respondida
        for field, question in questions:
            if field not in detalles or detalles[field] is None or detalles[field] == "":
                debug_print(f"DEBUG: Encontrada pregunta pendiente: {field} - {question}")
                return question
            # Si el campo tiene "No especificado", se considera respondido
            if detalles[field] == "No especificado":
                debug_print(f"DEBUG: Campo '{field}' ya respondido con 'No especificado', continuando...")
                continue
        
        debug_print(f"DEBUG: Todas las preguntas de maquinaria están respondidas")
        return None
    
    def is_conversation_complete(self, current_state: ConversationState) -> bool:
        """Verifica si la conversación está completa (todos los slots llenos)"""
        
        required_fields = [
            "nombre", "tipo_maquinaria", "sitio_web", "uso_empresa_o_venta",
            "nombre_completo", "nombre_empresa", "giro_empresa", "correo", "telefono"
        ]
        
        # Verificar campos básicos
        for field in required_fields:
            value = current_state.get(field)
            if not value or value == "":
                return False
            # Solo considerar válidos los campos con información real, no respuestas negativas
            if value in ["No tiene", "No especificado"]:
                return False
        
        # Verificar detalles de maquinaria
        tipo = current_state.get("tipo_maquinaria")
        detalles = current_state.get("detalles_maquinaria", {})
        
        if not tipo or not detalles:
            return False
        
        # Verificar que los detalles específicos estén completos
        required_details = {
            MaquinariaType.SOLDADORAS: ["amperaje", "electrodo"],
            MaquinariaType.COMPRESOR: ["capacidad_volumen", "herramientas"],
            MaquinariaType.TORRE_ILUMINACION: ["es_led"],
            MaquinariaType.LGMG: ["altura_trabajo", "actividad", "ubicacion"],
            MaquinariaType.GENERADORES: ["actividad", "capacidad"],
            MaquinariaType.ROMPEDORES: ["uso", "tipo"]
        }
        
        required = required_details.get(tipo, [])
        return all(field in detalles and detalles[field] is not None and detalles[field] != "" and detalles[field] != "No especificado" for field in required)

# ============================================================================
# SISTEMA DE RESPUESTAS INTELIGENTES
# ============================================================================

class IntelligentResponseGenerator:
    """Genera respuestas inteligentes basadas en el contexto y la información extraída"""
    
    def __init__(self, llm):
        self.llm = llm
    
    def generate_response(self, message: str, extracted_info: Dict[str, Any], current_state: ConversationState) -> str:
        """Genera una respuesta contextual apropiada"""
        
        # Si se extrajo información nueva, confirmarla
        if extracted_info:
            response_parts = []
            
            # Confirmar información extraída
            if "nombre" in extracted_info:
                response_parts.append(f"¡Mucho gusto {extracted_info['nombre']}!")
            
            if "tipo_maquinaria" in extracted_info:
                tipo = extracted_info["tipo_maquinaria"]
                response_parts.append(f"Perfecto, veo que necesita una {tipo}.")
            
            if "detalles_maquinaria" in extracted_info:
                detalles = extracted_info["detalles_maquinaria"]
                if detalles:
                    response_parts.append("Excelente, he registrado esos detalles.")
            
            # Agregar la siguiente pregunta
            if response_parts:
                response_parts.append("")
                return " ".join(response_parts)
        
        # Si no se extrajo información nueva, hacer la siguiente pregunta
        return ""
    
    def generate_final_response(self, current_state: ConversationState) -> str:
        """Genera la respuesta final cuando la conversación está completa"""
        
        return f"""¡Perfecto, {current_state['nombre']}! 

He registrado toda su información:
- Maquinaria: {current_state['tipo_maquinaria'].value}
- Detalles: {json.dumps(current_state['detalles_maquinaria'], indent=2, ensure_ascii=False)}
- Sitio web: {current_state['sitio_web']}
- Uso: {current_state['uso_empresa_o_venta']}
- Nombre completo: {current_state['nombre_completo']}
- Empresa: {current_state['nombre_empresa']}
- Giro: {current_state['giro_empresa']}
- Correo: {current_state['correo']}
- Teléfono: {current_state['telefono']}

Procederé a generar su cotización. Nos pondremos en contacto con usted pronto.

¿Hay algo más en lo que pueda ayudarle?"""

# ============================================================================
# VALIDADOR DE RESPUESTAS ESPECÍFICAS
# ============================================================================

class SpecificAnswerValidator:
    """Valida si la respuesta del usuario es válida para la pregunta específica sobre maquinaria"""
    
    def __init__(self, llm):
        self.llm = llm
    
    def validate_answer(self, user_answer: str, current_question: str, tipo_maquinaria: MaquinariaType) -> Dict[str, Any]:
        """
        Valida si la respuesta del usuario es válida para la pregunta específica
        
        Returns:
            Dict con:
            - is_valid: bool - si la respuesta es válida
            - extracted_value: str - valor extraído si es válido
            - reason: str - razón por la que no es válida (si aplica)
        """
        
        debug_print(f"DEBUG: Validando respuesta: '{user_answer}' para pregunta: '{current_question}' sobre {tipo_maquinaria.value}")
        
        try:
            prompt = ChatPromptTemplate.from_template(
                """
                Eres un asistente especializado en validar respuestas sobre maquinaria industrial.
                
                CONTEXTO:
                - Tipo de maquinaria: {tipo_maquinaria}
                - Pregunta actual: {current_question}
                - Respuesta del usuario: {user_answer}
                
                TU TAREA:
                Determinar si la respuesta del usuario es válida para la pregunta específica sobre la maquinaria.
                
                REGLAS DE VALIDACIÓN:
                1. RESPUESTA VÁLIDA: Si el usuario responde directamente a la pregunta sobre la maquinaria
                   Ejemplos válidos:
                   - Pregunta: "¿Qué capacidad de volumen de aire requiere?" → Respuesta: "100 pies cúbicos" ✅
                   - Pregunta: "¿Qué herramientas le va a conectar?" → Respuesta: "Taladros y pistolas de aire" ✅
                   - Pregunta: "¿Qué amperaje requiere?" → Respuesta: "Necesito 200 amperios" ✅
                
                2. RESPUESTA NEGATIVA O INCERTIDUMBRE: Si el usuario no quiere dar la información o no está seguro
                   Ejemplos válidos para avanzar:
                   - Pregunta: "¿Qué capacidad necesita?" → Respuesta: "No estoy seguro", "No sé", "No tengo idea" ✅
                   - Pregunta: "¿Qué herramientas?" → Respuesta: "No tengo", "No sé qué herramientas", "Aún no lo he decidido" ✅
                   - Pregunta: "¿Qué amperaje?" → Respuesta: "No lo sé", "No estoy seguro", "No tengo esa información" ✅
                   - Pregunta: "¿Qué altura necesita?" → Respuesta: "No estoy seguro", "No lo he medido", "No tengo idea" ✅
                
                3. RESPUESTA INVÁLIDA: Si el usuario NO responde a la pregunta sobre la maquinaria
                   Ejemplos inválidos:
                   - Pregunta: "¿Qué capacidad necesita?" → Respuesta: "¿Quieres que te cuente un chiste?" ❌
                   - Pregunta: "¿Qué herramientas?" → Respuesta: "¿También venden otras máquinas?" ❌
                   - Pregunta: "¿Qué amperaje?" → Respuesta: "¿Cuánto cuesta?" ❌
                   - Pregunta: "¿Qué altura necesita?" → Respuesta: "Hola, ¿cómo estás?" ❌
                
                4. EXTRACCIÓN DE VALOR: Si la respuesta es válida, extraer el valor específico
                   - Para capacidad: extraer números y unidades (ej: "100 pies", "5 metros")
                   - Para herramientas: extraer nombres de herramientas
                   - Para amperaje: extraer números y unidades (ej: "200 amp", "150 amperios")
                   - Para altura: extraer números y unidades (ej: "10 metros", "30 pies")
                   - Para respuestas negativas: usar "No especificado" como valor
                
                RESPUESTA EN FORMATO JSON:
                {{
                    "is_valid": true/false,
                    "extracted_value": "valor extraído si es válido, null si no es válido",
                    "reason": "razón por la que no es válida (solo si is_valid es false)"
                }}
                
                IMPORTANTE: Solo responde en formato JSON válido.
                """
            )
            
            response = self.llm.invoke(prompt.format_prompt(
                tipo_maquinaria=tipo_maquinaria.value,
                current_question=current_question,
                user_answer=user_answer
            ))
            
            debug_print(f"DEBUG: Respuesta del LLM para validación: '{response.content}'")
            
            # Parsear la respuesta JSON
            import json
            result = json.loads(response.content)
            
            debug_print(f"DEBUG: Resultado parseado: {result}")
            
            return {
                "is_valid": result.get("is_valid", False),
                "extracted_value": result.get("extracted_value"),
                "reason": result.get("reason", "")
            }
            
        except Exception as e:
            print(f"Error validando respuesta: {e}")
            # En caso de error, asumir que la respuesta es válida para no bloquear el flujo
            return {
                "is_valid": True,
                "extracted_value": user_answer,
                "reason": ""
            }

# ============================================================================
# LIMPIADOR DE RESPUESTAS ESPECÍFICAS
# ============================================================================

class SpecificAnswerCleaner:
    """Limpia y extrae solo la información relevante para cada pregunta específica sobre maquinaria"""
    
    def __init__(self, llm):
        self.llm = llm
    
    def clean_answer(self, user_answer: str, current_question: str, tipo_maquinaria: MaquinariaType) -> str:
        """
        Limpia la respuesta del usuario y extrae solo la información relevante para la pregunta específica
        
        Args:
            user_answer: Respuesta completa del usuario
            current_question: Pregunta específica sobre maquinaria
            tipo_maquinaria: Tipo de maquinaria del usuario
            
        Returns:
            str: Solo la información relevante para la pregunta específica
        """
        
        try:
            prompt = ChatPromptTemplate.from_template(
                """
                Eres un asistente especializado en limpiar respuestas sobre maquinaria industrial.
                
                CONTEXTO:
                - Tipo de maquinaria: {tipo_maquinaria}
                - Pregunta específica: {current_question}
                - Respuesta completa del usuario: {user_answer}
                
                TU TAREA:
                Extraer SOLO la información que responde directamente a la pregunta específica sobre la maquinaria.
                Excluir cualquier información adicional que no esté relacionada con la pregunta.
                
                REGLAS DE LIMPIEZA:
                1. SOLO incluir información que responda a la pregunta específica
                2. EXCLUIR información no relacionada (sitios web, comentarios, preguntas, etc.)
                3. MANTENER la información técnica relevante
                4. SIMPLIFICAR la respuesta para que sea clara y directa
                
                EJEMPLOS:
                
                Pregunta: "¿Qué herramientas le va a conectar?"
                Respuesta: "un aire acondicionado, deberias ver nuestra pagina web de perezmachines.co"
                Resultado: "aire acondicionado"
                
                Pregunta: "¿Qué capacidad de volumen de aire requiere?"
                Respuesta: "la necesito de 100 pies cubicos, por cierto también vendemos otras maquinas"
                Resultado: "100 pies cubicos"
                
                Pregunta: "¿Qué amperaje requiere?"
                Respuesta: "necesito 200 amperios, ¿cuánto cuesta?"
                Resultado: "200 amperios"
                
                Pregunta: "¿Qué altura de trabajo necesita?"
                Respuesta: "aproximadamente 15 metros, es para trabajo en exteriores"
                Resultado: "15 metros"
                
                IMPORTANTE:
                - Solo devuelve la información relevante para la pregunta
                - No incluyas explicaciones ni texto adicional
                - Si no hay información relevante, devuelve "No especificado"
                - Mantén la respuesta lo más simple posible
                
                Respuesta limpia:
                """
            )
            
            response = self.llm.invoke(prompt.format_prompt(
                tipo_maquinaria=tipo_maquinaria.value,
                current_question=current_question,
                user_answer=user_answer
            ))
            
            cleaned_answer = response.content.strip()
            debug_print(f"DEBUG: Respuesta original: '{user_answer}'")
            debug_print(f"DEBUG: Respuesta limpia: '{cleaned_answer}'")
            
            return cleaned_answer
            
        except Exception as e:
            print(f"Error limpiando respuesta: {e}")
            # En caso de error, devolver la respuesta original
            return user_answer

# ============================================================================
# RESPONDEDOR DE INVENTARIO
# ============================================================================

class InventoryResponder:
    """Responde preguntas sobre el inventario de maquinaria"""
    
    def __init__(self, llm):
        self.llm = llm
        self.inventory = get_inventory()
    
    def is_inventory_question(self, message: str) -> bool:
        """Determina si el mensaje del usuario es una pregunta sobre el inventario"""
        try:
            # Obtener el inventario actual
            inventory_info = f"""
            INVENTARIO DISPONIBLE:
            - Tipo de maquinaria: {', '.join(self.inventory['tipo_maquinaria'])}
            - Modelo: {self.inventory['modelo_maquinaria']}
            - Ubicación: {self.inventory['ubicacion']}
            """
            
            prompt = ChatPromptTemplate.from_template(
                """
                Eres un asistente especializado en identificar si un mensaje del usuario es una pregunta sobre inventario de maquinaria.
                
                {inventory_info}
                
                TU TAREA:
                Determinar si el mensaje del usuario es una pregunta sobre:
                1. Disponibilidad de maquinaria
                2. Tipos de maquinaria que vendemos
                3. Modelos disponibles
                4. Ubicaciones de entrega
                5. Precios o cotizaciones
                6. Características de la maquinaria
                7. Cualquier consulta relacionada con el inventario
                
                REGLAS:
                - Si es pregunta sobre inventario → true
                - Si es respuesta a una pregunta del bot → false
                - Si es información personal del usuario → false
                - Si es pregunta general no relacionada → false
                
                EJEMPLOS DE PREGUNTAS SOBRE INVENTARIO:
                - "¿Qué tipos de maquinaria tienen?"
                - "¿Tienen soldadoras?"
                - "¿Cuánto cuesta un compresor?"
                - "¿En qué ubicaciones entregan?"
                - "¿Qué modelos de generadores manejan?"
                - "¿Tienen inventario disponible?"
                - "¿Pueden cotizar una torre de iluminación?"
                
                EJEMPLOS DE NO INVENTARIO:
                - "me llamo Juan"
                - "quiero un compresor"
                - "no tengo página web"
                - "es para venta"
                - "mi empresa se llama ABC"
                
                Mensaje del usuario: {message}
                
                Responde SOLO con "true" si es pregunta sobre inventario, o "false" si no lo es.
                """
            )
            
            response = self.llm.invoke(prompt.format_prompt(
                inventory_info=inventory_info,
                message=message
            ))
            
            result = response.content.strip().lower()
            
            debug_print(f"DEBUG: ¿Es pregunta sobre inventario? '{message}' → {result}")
            
            return result == "true"
            
        except Exception as e:
            print(f"Error detectando pregunta de inventario: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def generate_inventory_response(self, question: str) -> str:
        """Genera una respuesta sobre el inventario basada en la pregunta del usuario"""
        try:
            # Obtener el inventario actual
            inventory_info = f"""
            INVENTARIO DISPONIBLE:
            - Tipo de maquinaria: {', '.join(self.inventory['tipo_maquinaria'])}
            - Modelo: {self.inventory['modelo_maquinaria']}
            - Ubicación: {self.inventory['ubicacion']}
            """
            
            debug_print(f"DEBUG: Generando respuesta sobre inventario con: {inventory_info}")
            
            prompt = ChatPromptTemplate.from_template(
                """
                Eres un asistente especializado en inventario de maquinaria industrial.
                
                {inventory_info}
                
                PREGUNTA DEL USUARIO: {question}
                
                TU TAREA:
                Generar una respuesta útil y profesional sobre el inventario disponible.
                
                REGLAS:
                1. Sé específico sobre lo que tenemos disponible
                2. Menciona los tipos de maquinaria que manejamos
                3. Indica que podemos cotizar cualquier modelo
                4. Menciona que entregamos en cualquier ubicación de México
                5. Mantén un tono profesional y servicial
                6. No inventes precios específicos, solo menciona que podemos cotizar
                7. Invita al usuario a continuar con su consulta
                
                EJEMPLOS DE RESPUESTAS:
                
                Para preguntas sobre tipos:
                "Contamos con un amplio inventario que incluye soldadoras, compresores, torres de iluminación, LGMG, generadores y rompedores. Podemos cotizar cualquier modelo que necesite."
                
                Para preguntas sobre disponibilidad:
                "Tenemos inventario disponible de todos los tipos de maquinaria."
                
                Para preguntas sobre ubicación:
                "Entregamos en ciudades como Guadalajara, Monterrey, Ciudad de México, entre otras. Contamos con soldadoras, compresores, torres de iluminación, LGMG, generadores y rompedores. Podemos cotizar cualquier modelo que necesite."
                
                IMPORTANTE: Siempre termina invitando al usuario a continuar con su consulta para completar la información necesaria.
                
                Respuesta:
                """
            )
            
            debug_print(f"DEBUG: Enviando prompt al LLM para generar respuesta de inventario...")
            
            response = self.llm.invoke(prompt.format_prompt(
                inventory_info=inventory_info,
                question=question
            ))
            
            result = response.content.strip()
            
            debug_print(f"DEBUG: Respuesta sobre inventario generada: '{result}'")
            
            return result
            
        except Exception as e:
            print(f"Error generando respuesta de inventario: {e}")
            import traceback
            traceback.print_exc()
            return "Contamos con un amplio inventario de maquinaria industrial."

# ============================================================================
# CLASE PRINCIPAL DEL CHATBOT CON SLOT-FILLING INTELIGENTE
# ============================================================================

class IntelligentLeadQualificationChatbot:
    """Chatbot con slot-filling inteligente que detecta información ya proporcionada"""
    
    def __init__(self, azure_config: AzureOpenAIConfig):
        self.azure_config = azure_config
        self.llm = azure_config.create_llm()
        self.slot_filler = IntelligentSlotFiller(self.llm)
        self.response_generator = IntelligentResponseGenerator(self.llm)
        self.answer_validator = SpecificAnswerValidator(self.llm)
        self.answer_cleaner = SpecificAnswerCleaner(self.llm) # Agregar el nuevo limpiador
        self.inventory_responder = InventoryResponder(self.llm) # Agregar el nuevo respondedor
        self.reset_conversation()
    
    def reset_conversation(self):
        """Reinicia el estado de la conversación"""
        self.state = {
            "messages": [],
            "nombre": None,
            "tipo_maquinaria": None,
            "detalles_maquinaria": {},
            "sitio_web": None,
            "uso_empresa_o_venta": None,
            "nombre_completo": None,
            "nombre_empresa": None,
            "giro_empresa": None,
            "correo": None,
            "telefono": None,
            "completed": False
        }
    
    def send_message(self, user_message: str) -> str:
        """Procesa un mensaje del usuario con slot-filling inteligente, validación de respuestas específicas y respuestas sobre inventario"""
        
        try:
            debug_print(f"DEBUG: send_message llamado con mensaje: '{user_message}'")
            
            # Si el mensaje está vacío, no hacer nada y esperar al usuario
            if not user_message or not user_message.strip():
                return ""
            
            # Agregar mensaje del usuario
            self.state["messages"].append({
                "role": "user", 
                "content": user_message
            })
            
            # PRIMERO: Extraer TODA la información disponible del mensaje (SIEMPRE)
            # Obtener la última pregunta del bot para contexto
            last_bot_question = self._get_last_bot_question()
            extracted_info = self.slot_filler.extract_all_information(user_message, self.state, last_bot_question)
            debug_print(f"DEBUG: Información extraída: {extracted_info}")
            
            # Actualizar el estado con la información extraída
            self._update_state_with_extracted_info(extracted_info)
            debug_print(f"DEBUG: Estado después de actualización: {self.state}")
            
            # SEGUNDO: Verificar si es una pregunta sobre inventario
            if self.inventory_responder.is_inventory_question(user_message):
                debug_print(f"DEBUG: Pregunta sobre inventario detectada, generando respuesta...")
                inventory_response = self.inventory_responder.generate_inventory_response(user_message)
                
                # Obtener la siguiente pregunta necesaria para continuar el flujo
                next_question = self.slot_filler.get_next_question(self.state)
                
                if next_question:
                    # Combinar respuesta de inventario con la siguiente pregunta
                    full_response = f"{inventory_response}\n\n{next_question}"
                    self.state["messages"].append({"role": "assistant", "content": full_response})
                    debug_print(f"DEBUG: Respuesta combinada (inventario + siguiente pregunta): {full_response}")
                    return full_response
                else:
                    # No hay más preguntas, solo responder sobre inventario
                    self.state["messages"].append({"role": "assistant", "content": inventory_response})
                    return inventory_response
            
            # SEGUNDO: Si no es pregunta de inventario, continuar con el flujo normal
            debug_print(f"DEBUG: No es pregunta de inventario, continuando con flujo normal...")
            
            # Verificar si el mensaje anterior era una pregunta sobre maquinaria
            last_assistant_message = None
            for msg in reversed(self.state["messages"]):
                if msg["role"] == "assistant":
                    last_assistant_message = msg["content"]
                    break
            
            # Si la pregunta anterior era sobre detalles de maquinaria, validar la respuesta
            if last_assistant_message and self._is_maquinaria_detail_question(last_assistant_message, self.state):
                debug_print(f"DEBUG: Detectada pregunta sobre maquinaria, validando respuesta...")
                validation_result = self._validate_maquinaria_answer(user_message, last_assistant_message, self.state)
                debug_print(f"DEBUG: Resultado de validación: {validation_result}")
                
                if not validation_result["is_valid"]:
                    # La respuesta no es válida, repetir la pregunta con explicación
                    debug_print(f"DEBUG: Respuesta inválida, repitiendo pregunta...")
                    invalid_response = f"Disculpe, pero su respuesta no está relacionada con la pregunta sobre la maquinaria. {validation_result['reason']}\n\n{last_assistant_message}"
                    self.state["messages"].append({"role": "assistant", "content": invalid_response})
                    return invalid_response
                
                # La respuesta es válida, actualizar el estado con el valor extraído
                if validation_result["extracted_value"]:
                    debug_print(f"DEBUG: Respuesta válida, actualizando detalle: {validation_result['extracted_value']}")
                    self._update_maquinaria_detail(last_assistant_message, validation_result["extracted_value"], self.state)
                    debug_print(f"DEBUG: Estado actualizado: {self.state['detalles_maquinaria']}")
            
            # Log específico para sitio_web
            if "sitio_web" in extracted_info:
                debug_print(f"DEBUG: Sitio web extraído: '{extracted_info['sitio_web']}'")
            
            # Log específico para giro_empresa
            if "giro_empresa" in extracted_info:
                debug_print(f"DEBUG: Giro de empresa extraído: '{extracted_info['giro_empresa']}'")
            
            # Log específico para uso_empresa_o_venta
            if "uso_empresa_o_venta" in extracted_info:
                debug_print(f"DEBUG: Uso empresa o venta extraído: '{extracted_info['uso_empresa_o_venta']}'")
            
            # Log específico para correo
            if "correo" in extracted_info:
                debug_print(f"DEBUG: Correo extraído: '{extracted_info['correo']}'")
            
            # Log específico para telefono
            if "telefono" in extracted_info:
                debug_print(f"DEBUG: Teléfono extraído: '{extracted_info['telefono']}'")
            
            # Verificar si la conversación está completa
            if self.slot_filler.is_conversation_complete(self.state):
                debug_print(f"DEBUG: Conversación completa!")
                self.state["completed"] = True
                final_response = self.response_generator.generate_final_response(self.state)
                self.state["messages"].append({"role": "assistant", "content": final_response})
                return final_response
            
            # Generar respuesta contextual
            contextual_response = self.response_generator.generate_response(
                user_message, extracted_info, self.state
            )
            debug_print(f"DEBUG: Respuesta contextual: {contextual_response}")
            
            # Obtener la siguiente pregunta necesaria
            next_question = self.slot_filler.get_next_question(self.state)
            debug_print(f"DEBUG: Siguiente pregunta: {next_question}")
            debug_print(f"DEBUG: Estado actual de detalles_maquinaria: {self.state.get('detalles_maquinaria', {})}")
            
            if next_question:
                # Combinar respuesta contextual con siguiente pregunta
                if contextual_response:
                    full_response = f"{contextual_response}\n\n{next_question}"
                else:
                    full_response = next_question
                
                debug_print(f"DEBUG: Respuesta completa: {full_response}")
                self.state["messages"].append({"role": "assistant", "content": full_response})
                return full_response
            else:
                # No hay más preguntas, la conversación debería estar completa
                debug_print(f"DEBUG: No hay más preguntas, verificando si la conversación está completa...")
                debug_print(f"DEBUG: Estado completo: {self.state}")
                return "Gracias por toda la información. Estoy procesando su solicitud."
        
        except Exception as e:
            print(f"Error procesando mensaje: {e}")
            return "Disculpe, hubo un error técnico. ¿Podría intentar de nuevo?"
    
    def _update_state_with_extracted_info(self, extracted_info: Dict[str, Any]):
        """Actualiza el estado con la información extraída"""
        
        debug_print(f"DEBUG: Actualizando estado con información: {extracted_info}")
        
        for key, value in extracted_info.items():
            if key == "detalles_maquinaria" and isinstance(value, dict):
                # Actualizar detalles de maquinaria
                current_detalles = self.state.get("detalles_maquinaria", {})
                current_detalles.update(value)
                self.state["detalles_maquinaria"] = current_detalles
                debug_print(f"DEBUG: Detalles de maquinaria actualizados: {self.state['detalles_maquinaria']}")
            elif key == "tipo_maquinaria" and value:
                # Convertir string a enum
                try:
                    self.state[key] = MaquinariaType(value)
                    debug_print(f"DEBUG: Tipo de maquinaria actualizado: {self.state[key]}")
                except ValueError:
                    print(f"Tipo de maquinaria inválido: {value}")
            elif key == "nombre_completo" and value:
                # Lógica para manejar nombres: 3+ palabras = nombre completo, 1-2 palabras = solo nombre
                word_count = len(value.strip().split())
                if word_count >= 3:
                    # 3 o más palabras: llenar tanto nombre como nombre_completo
                    self.state[key] = value
                    self.state["nombre"] = value
                    debug_print(f"DEBUG: Nombre con {word_count} palabras, llenando 'nombre' y 'nombre_completo': '{value}'")
                else:
                    # 1 o 2 palabras: solo llenar nombre, no nombre_completo
                    self.state["nombre"] = value
                    debug_print(f"DEBUG: Nombre con {word_count} palabras, llenando solo 'nombre': '{value}'")
            elif value is not None:  # Solo actualizar si hay valor
                # NO sobrescribir campos que ya tienen información válida
                current_value = self.state.get(key)
                if current_value and current_value not in ["No especificado", "No tiene", None, ""]:
                    debug_print(f"DEBUG: Campo '{key}' ya tiene valor válido '{current_value}', no sobrescribiendo")
                    continue
                
                # Verificar si la respuesta es negativa o de incertidumbre
                negative_indicators = [
                    "no", "no sé", "no estoy seguro", "no lo sé", "no tengo idea", 
                    "aún no lo he decidido", "no quiero dar esa información", 
                    "prefiero no decir", "es confidencial", "no tengo", "no hay"
                ]
                
                is_negative_response = any(indicator in str(value).lower() for indicator in negative_indicators)
                
                if is_negative_response:
                    # Para campos específicos, usar valores apropiados para respuestas negativas
                    if key in ["correo", "telefono", "sitio_web"]:
                        final_value = "No tiene"
                    elif key in ["nombre_empresa", "giro_empresa"]:
                        final_value = "No especificado"
                    else:
                        final_value = "No especificado"
                    
                    self.state[key] = final_value
                    debug_print(f"DEBUG: Respuesta negativa detectada para '{key}', usando valor: '{final_value}'")
                else:
                    # Respuesta normal
                    self.state[key] = value
                    debug_print(f"DEBUG: Campo '{key}' actualizado con valor: '{value}'")
        
    def _get_last_bot_question(self) -> Optional[str]:
        """Obtiene la última pregunta que hizo el bot para proporcionar contexto"""
        # Buscar el último mensaje del bot en el historial
        for msg in reversed(self.state["messages"]):
            if msg["role"] == "assistant":
                content = msg["content"]
                # Si el mensaje contiene una pregunta, extraerla
                if "?" in content:
                    # Buscar la última línea que contenga una pregunta
                    lines = content.split('\n')
                    for line in reversed(lines):
                        if "?" in line and line.strip():
                            return line.strip()
                    # Si no se encuentra una línea específica, devolver todo el contenido
                    return content
                return content
        return None
    
    def _is_maquinaria_detail_question(self, question: str, state: ConversationState) -> bool:
        """Determina si la pregunta es sobre detalles específicos de maquinaria"""
        tipo = state.get("tipo_maquinaria")
        if not tipo:
            return False
        
        # Lista de preguntas específicas de maquinaria (debe coincidir con el mapeo en _update_maquinaria_detail)
        maquinaria_questions = [
            "¿Qué amperaje requiere?",
            "¿Qué tipo de electrodo quema?",
            "¿Qué capacidad de volumen de aire requiere?",
            "¿Qué herramientas le va a conectar?",
            "¿La requiere de LED?",
            "¿Qué altura de trabajo necesita?",
            "¿Qué actividad va a realizar?",
            "¿Es en exterior o interior?",
            "¿Para qué actividad lo requiere?",
            "¿Qué capacidad en kvas o kw necesita?",
            "¿Para qué lo va a utilizar?",
            "¿Lo requiere eléctrico o neumático?"
        ]
        
        # Verificar si alguna de las preguntas está contenida en el mensaje
        for maq_question in maquinaria_questions:
            if maq_question in question:
                return True
        
        debug_print(f"DEBUG: No es pregunta sobre maquinaria: '{question}'")
        return False
    
    def _validate_maquinaria_answer(self, user_answer: str, question: str, state: ConversationState) -> Dict[str, Any]:
        """Valida si la respuesta del usuario es válida para la pregunta sobre maquinaria"""
        tipo = state.get("tipo_maquinaria")
        if not tipo:
            return {"is_valid": True, "extracted_value": user_answer, "reason": ""}
        
        return self.answer_validator.validate_answer(user_answer, question, tipo)
    
    def _update_maquinaria_detail(self, question: str, value: str, state: ConversationState):
        """Actualiza el estado con el detalle de maquinaria extraído y limpiado"""
        tipo = state.get("tipo_maquinaria")
        if not tipo:
            return
        
        debug_print(f"DEBUG: Actualizando detalle de maquinaria para pregunta: '{question}' con valor: '{value}'")
        
        # Mapeo de preguntas a campos de detalles
        question_to_field = {
            "¿Qué amperaje requiere?": "amperaje",
            "¿Qué tipo de electrodo quema?": "electrodo",
            "¿Qué capacidad de volumen de aire requiere?": "capacidad_volumen",
            "¿Qué herramientas le va a conectar?": "herramientas",
            "¿La requiere de LED?": "es_led",
            "¿Qué altura de trabajo necesita?": "altura_trabajo",
            "¿Qué actividad va a realizar?": "actividad",
            "¿Es en exterior o interior?": "ubicacion",
            "¿Para qué actividad lo requiere?": "actividad",
            "¿Qué capacidad en kvas o kw necesita?": "capacidad",
            "¿Para qué lo va a utilizar?": "uso",
            "¿Lo requiere eléctrico o neumático?": "tipo"
        }
        
        # Buscar la pregunta que coincida
        field = None
        for question_pattern, field_name in question_to_field.items():
            if question_pattern in question:
                field = field_name
                debug_print(f"DEBUG: Pregunta '{question}' coincide con patrón '{question_pattern}' -> campo '{field_name}'")
                break
        
        if field:
            # Verificar si la respuesta es negativa o de incertidumbre
            negative_indicators = [
                "no", "no sé", "no estoy seguro", "no lo sé", "no tengo idea", 
                "aún no lo he decidido", "no quiero dar esa información", 
                "prefiero no decir", "es confidencial", "no tengo", "no hay"
            ]
            
            is_negative_response = any(indicator in value.lower() for indicator in negative_indicators)
            
            if is_negative_response:
                # Respuesta negativa o de incertidumbre
                cleaned_value = "No especificado"
                debug_print(f"DEBUG: Respuesta negativa detectada, usando 'No especificado'")
                # Agregar mensaje de confirmación para respuestas negativas
                self.state["messages"].append({
                    "role": "assistant", 
                    "content": "Entiendo, no hay problema. Continuemos con la siguiente pregunta."
                })
            else:
                # Respuesta normal, limpiar para obtener solo la información relevante
                cleaned_value = self.answer_cleaner.clean_answer(value, question, tipo)
                debug_print(f"DEBUG: Respuesta normal, valor limpio: '{cleaned_value}'")
            
            debug_print(f"DEBUG: Valor original: '{value}'")
            debug_print(f"DEBUG: Valor final: '{cleaned_value}'")
            
            if "detalles_maquinaria" not in state:
                state["detalles_maquinaria"] = {}
            state["detalles_maquinaria"][field] = cleaned_value
            debug_print(f"DEBUG: Campo '{field}' actualizado con valor '{cleaned_value}'")
            debug_print(f"DEBUG: Estado completo de detalles_maquinaria: {state['detalles_maquinaria']}")
        else:
            debug_print(f"DEBUG: No se pudo mapear la pregunta a un campo: '{question}'")
            debug_print(f"DEBUG: Patrones disponibles: {list(question_to_field.keys())}")
    
    def get_conversation_summary(self) -> Dict[str, Any]:
        """Obtiene un resumen completo del lead calificado"""
        return {
            "nombre": self.state["nombre"],
            "tipo_maquinaria": self.state["tipo_maquinaria"],
            "detalles_maquinaria": self.state["detalles_maquinaria"],
            "sitio_web": self.state["sitio_web"],
            "conversacion_completa": self.state["completed"],
            "mensajes_total": len(self.state["messages"])
        }
    
    def get_lead_data_json(self) -> str:
        """Obtiene los datos del lead en formato JSON"""
        return json.dumps(self.get_conversation_summary(), indent=2, ensure_ascii=False)
    

"""
# ============================================================================
# EJEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    # Configurar Azure OpenAI
    azure_config = AzureOpenAIConfig(
        endpoint=os.getenv("FOUNDRY_ENDPOINT"),
        api_key=os.getenv("FOUNDRY_API_KEY"),
        deployment_name="gpt-4.1-mini",
        api_version="2024-12-01-preview",
        model_name="gpt-4.1-mini"
    )
    
    try:
        print("🔄 Inicializando chatbot con slot-filling inteligente...")
        chatbot = IntelligentLeadQualificationChatbot(azure_config)
        print("✅ ¡Chatbot iniciado correctamente!")
        print("📝 Escriba 'salir' para terminar.")
        print("💬 ¡Usted inicia la conversación! Escriba su mensaje:\n")
        
        # Loop de conversación
        while True:
            try:
                user_input = input("\n👤 Usuario: ").strip()
                
                if user_input.lower() in ['salir', 'exit', 'quit']:
                    print("👋 ¡Gracias por usar el sistema de calificación de leads!")
                    break
                
                if user_input:
                    response = chatbot.send_message(user_input)
                    print(f"🤖 Bot: {response}")
                    
                    # Mostrar resumen si la conversación está completa
                    if chatbot.state["completed"]:
                        print("\n" + "="*60)
                        print("📊 RESUMEN DEL LEAD CALIFICADO:")
                        print("="*60)
                        print(chatbot.get_lead_data_json())
                        print("="*60)
                        
                        respuesta = input("\n🔄 ¿Desea iniciar una nueva conversación? (s/n): ").strip().lower()
                        if respuesta == 's':
                            chatbot.reset_conversation()
                            print("\n🔄 Nueva conversación iniciada. ¡Usted comienza! Escriba su mensaje:\n")
                        else:
                            print("👋 ¡Gracias por usar el sistema!")
                            break
                            
            except KeyboardInterrupt:
                print("\n\n👋 ¡Hasta luego!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                print("💡 Intente de nuevo o escriba 'salir' para terminar.")
    
    except Exception as e:
        print(f"❌ Error iniciando el chatbot: {e}")
        print("💡 Verifique su configuración de Azure OpenAI:")
        print("   - Endpoint correcto")
        print("   - API Key válida") 
        print("   - Nombre del deployment correcto")
        print("   - Versión de API compatible")
"""