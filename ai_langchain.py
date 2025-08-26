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
            
            REGLAS ADICIONALES PARA DETALLES DE MAQUINARIA:
            - Para TORRE_ILUMINACION solo extraer información sobre LED (es_led: true/false)
            - Para SOLDADORAS solo extraer amperaje y tipo de electrodo
            - Para COMPRESOR solo extraer capacidad de volumen y herramientas
            - Para LGMG solo extraer altura, actividad y ubicación (exterior/interior)
            - Para GENERADORES solo extraer actividad y capacidad
            - Para ROMPEDORES solo extraer uso y tipo (eléctrico/neumático)
            - NO extraer campos que no estén definidos para cada tipo de maquinaria
            - NO inventar campos adicionales como "proyecto", "aplicación", etc.
            
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
        generándola de manera conversacional y natural
        """
        
        try:
            # Definir el orden de prioridad de los slots
            slot_priority = [
                ("nombre", "Para brindarte atención personalizada"),
                ("tipo_maquinaria", "Para revisar nuestro inventario disponible"),
                ("detalles_maquinaria", None),  # Se maneja por separado
                ("sitio_web", "Para conocer mejor su empresa y generar una cotización más precisa"),
                ("uso_empresa_o_venta", "Para ofrecerle las mejores opciones comerciales"),
                ("nombre_completo", "Para los documentos oficiales de cotización"),
                ("nombre_empresa", "Para generar la cotización a nombre de su empresa"),
                ("giro_empresa", "Para entender mejor sus necesidades específicas"),
                ("correo", "Para enviarle la cotización"),
                ("telefono", "Para darle seguimiento personalizado")
            ]
            
            # Verificar cada slot en orden de prioridad
            for slot_name, reason in slot_priority:
                if slot_name == "detalles_maquinaria":
                    # Manejar detalles específicos de maquinaria
                    question = self._get_maquinaria_detail_question(current_state)
                    if question:
                        return question
                else:
                    # Verificar si el slot está vacío o tiene respuestas negativas
                    value = current_state.get(slot_name)
                    if not value or value in ["No tiene", "No especificado"]:
                        return self._generate_conversational_question(slot_name, reason, current_state)
            
            # Si todos los slots están llenos
            return None
            
        except Exception as e:
            print(f"Error generando siguiente pregunta: {e}")
            return None
    
    def _generate_conversational_question(self, field_name: str, reason: str, current_state: ConversationState) -> str:
        """
        Genera una pregunta conversacional natural basándose en el campo y el contexto
        """
        
        try:
            prompt = ChatPromptTemplate.from_template(
                """
                Eres Juan, un asistente de ventas profesional especializado en maquinaria ligera en México.
                
                Tu tarea es generar UNA pregunta natural y conversacional para obtener la siguiente información:
                
                CAMPO A PREGUNTAR: {field_name}
                RAZÓN POR LA QUE LO NECESITAS: {reason}
                
                ESTADO ACTUAL:
                - Nombre: {current_nombre}
                - Tipo de maquinaria: {current_tipo}
                
                REGLAS PARA LA PREGUNTA:
                1. Sé amigable y profesional
                2. Explica brevemente por qué necesitas esta información
                3. Para campos como sitio_web, correo, teléfono: haz la pregunta completa en una sola oración
                4. Mantén la pregunta corta pero completa (máximo 50 palabras)
                5. Usa un tono conversacional natural
                6. Si ya tienes el nombre del usuario, púédelo usar para personalizar
                
                EJEMPLOS PARA CADA CAMPO:
                
                Para "nombre":
                - "¿Con quién tengo el gusto? Esto me ayuda a personalizar nuestra conversación."
                - "Para brindarte atención personalizada, ¿podrías decirme tu nombre?"
                
                Para "tipo_maquinaria":
                - "¿Qué tipo de maquinaria ligera estás buscando? Esto me permite revisar nuestro inventario."
                - "¿Qué equipo necesitas? Así puedo verificar disponibilidad."
                
                Para "sitio_web":
                - "¿Su empresa cuenta con algún sitio web? Si es así, ¿me lo podría compartir?"
                - "¿Tienen página web? Si es así, me gustaría conocerla para entender mejor su giro."
                
                Para "uso_empresa_o_venta":
                - "¿Es para uso de tu empresa o para venta? Esto me permite ofrecerte las mejores opciones."
                - "¿Lo van a usar internamente o es para comercializar? Así ajusto la propuesta."
                
                Para "nombre_completo":
                - "¿Cuál es tu nombre completo? Lo necesito para los documentos oficiales."
                - "Para la cotización formal, ¿podrías darme tu nombre completo?"
                
                Para "nombre_empresa":
                - "¿Cuál es el nombre de tu empresa? La cotización irá a su nombre."
                - "¿En qué empresa trabajas? Necesito este dato para el documento."
                
                Para "giro_empresa":
                - "¿A qué se dedica tu empresa? Esto me ayuda a entender mejor sus necesidades."
                - "¿Cuál es el giro de su negocio? Me permite personalizar la recomendación."
                
                Para "correo":
                - "¿Cuál es su correo electrónico? Por ahí le enviaré la cotización."
                - "Para enviarle la propuesta, ¿me comparte su email?"
                
                Para "telefono":
                - "¿Cuál es su número de teléfono? Así puedo darle seguimiento personalizado a su cotización."
                - "Para contactarlo después con la propuesta, ¿me comparte su teléfono?"
                
                IMPORTANTE - FORMATO DE PREGUNTAS:
                - Para sitio_web: SIEMPRE usar el formato "¿Su empresa cuenta con algún sitio web? Si es así, ¿me lo podría compartir?"
                - Para campos que pueden no existir: incluir tanto la consulta como la solicitud del dato
                - Hacer preguntas completas en una sola oración, no dividir en partes
                
                Genera SOLO la pregunta (sin explicaciones adicionales):
                """
            )
            
            response = self.llm.invoke(prompt.format_prompt(
                field_name=field_name,
                reason=reason,
                current_nombre=current_state.get("nombre", "No especificado"),
                current_tipo=current_state.get("tipo_maquinaria", "No especificado")
            ))
            
            question = response.content.strip()
            debug_print(f"DEBUG: Pregunta conversacional generada para '{field_name}': '{question}'")
            return question
            
        except Exception as e:
            print(f"Error generando pregunta conversacional: {e}")
            # Fallback a preguntas predefinidas
            fallback_questions = {
                "nombre": "¿Con quién tengo el gusto?",
                "tipo_maquinaria": "¿Qué tipo de maquinaria requiere?",
                "sitio_web": "¿Su empresa cuenta con sitio web?",
                "uso_empresa_o_venta": "¿Es para uso de la empresa o para venta?",
                "nombre_completo": "¿Cuál es su nombre completo?",
                "nombre_empresa": "¿Cuál es el nombre de su empresa?",
                "giro_empresa": "¿Cuál es el giro de su empresa?",
                "correo": "¿Cuál es su correo electrónico?",
                "telefono": "¿Cuál es su teléfono?"
            }
            return fallback_questions.get(field_name, "¿Podría proporcionar esa información?")
    
    def _get_maquinaria_detail_question(self, current_state: ConversationState) -> Optional[str]:
        """Obtiene la siguiente pregunta específica sobre detalles de maquinaria de manera conversacional"""
        
        tipo = current_state.get("tipo_maquinaria")
        if not tipo:
            debug_print(f"DEBUG: No hay tipo de maquinaria definido")
            return None
            
        detalles = current_state.get("detalles_maquinaria", {})
        debug_print(f"DEBUG: Tipo de maquinaria: {tipo}, detalles actuales: {detalles}")
        
        # Definir campos y razones por tipo de maquinaria
        maquinaria_fields_map = {
            MaquinariaType.SOLDADORAS: [
                ("amperaje", "Para recomendarte el modelo adecuado según tu trabajo"),
                ("electrodo", "Para asegurar compatibilidad con tus materiales")
            ],
            MaquinariaType.COMPRESOR: [
                ("capacidad_volumen", "Para seleccionar la potencia correcta"),
                ("herramientas", "Para verificar compatibilidad con tus equipos")
            ],
            MaquinariaType.TORRE_ILUMINACION: [
                ("es_led", "Para cotizar la tecnología más eficiente")
            ],
            MaquinariaType.LGMG: [
                ("altura_trabajo", "Para garantizar que alcance la altura necesaria"),
                ("actividad", "Para recomendar el modelo más seguro"),
                ("ubicacion", "Para seleccionar las características apropiadas")
            ],
            MaquinariaType.GENERADORES: [
                ("actividad", "Para calcular la potencia necesaria"),
                ("capacidad", "Para seleccionar el generador adecuado")
            ],
            MaquinariaType.ROMPEDORES: [
                ("uso", "Para recomendarte el tipo más eficiente"),
                ("tipo", "Para cotizar según tu fuente de energía disponible")
            ]
        }
        
        fields = maquinaria_fields_map.get(tipo, [])
        debug_print(f"DEBUG: Campos disponibles para {tipo}: {fields}")
        
        # Buscar el primer campo que no esté respondido
        for field, reason in fields:
            field_value = detalles.get(field)
            # Verificar también variaciones del nombre del campo para compatibilidad
            alt_field_names = self._get_field_alternatives(field)
            for alt_field in alt_field_names:
                if alt_field in detalles and detalles[alt_field]:
                    field_value = detalles[alt_field]
                    # Normalizar el campo al nombre estándar
                    if alt_field != field:
                        debug_print(f"DEBUG: Normalizando campo '{alt_field}' a '{field}'")
                        detalles[field] = field_value
                        if alt_field in detalles:
                            del detalles[alt_field]
                    break
            
            # Verificar si el campo está vacío o no definido
            if not field_value or field_value in ["", None]:
                debug_print(f"DEBUG: Encontrado campo pendiente: {field}")
                return self._generate_maquinaria_question(field, reason, tipo, current_state)
            
            # Si el campo tiene "No especificado", se considera respondido
            if field_value == "No especificado":
                debug_print(f"DEBUG: Campo '{field}' ya respondido con 'No especificado', continuando...")
                continue
            else:
                debug_print(f"DEBUG: Campo '{field}' ya tiene valor: '{field_value}', continuando...")
        
        debug_print(f"DEBUG: Todas las preguntas de maquinaria están respondidas")
        return None
    
    def _get_field_alternatives(self, field: str) -> List[str]:
        """Obtiene nombres alternativos para un campo para manejar inconsistencias"""
        alternatives = {
            "capacidad_volumen": ["capacidad_volumen", "capacidad_de_volumen", "capacidad"],
            "altura_trabajo": ["altura_trabajo", "altura_de_trabajo", "altura"],
            "es_led": ["es_led", "led", "tipo_led"],
            "amperaje": ["amperaje", "amp", "corriente"],
            "electrodo": ["electrodo", "tipo_electrodo"],
            "herramientas": ["herramientas", "equipos", "herramienta"],
            "actividad": ["actividad", "trabajo", "tarea"],
            "ubicacion": ["ubicacion", "ubicación", "lugar"],
            "capacidad": ["capacidad", "potencia", "kva", "kw"],
            "uso": ["uso", "utilizacion", "aplicacion"],
            "tipo": ["tipo", "alimentacion", "energia"]
        }
        return alternatives.get(field, [field])
    
    def _generate_maquinaria_question(self, field: str, reason: str, tipo: MaquinariaType, current_state: ConversationState) -> str:
        """Genera una pregunta conversacional específica sobre maquinaria"""
        
        try:
            prompt = ChatPromptTemplate.from_template(
                """
                Eres Juan, un asistente de ventas profesional especializado en maquinaria ligera en México.
                
                Tu tarea es generar UNA pregunta natural y conversacional para obtener información específica sobre la maquinaria:
                
                TIPO DE MAQUINARIA: {tipo_maquinaria}
                CAMPO ESPECÍFICO: {field}
                RAZÓN: {reason}
                NOMBRE DEL USUARIO: {nombre}
                
                REGLAS:
                1. Sé amigable y profesional
                2. Explica brevemente por qué necesitas esta información técnica
                3. Mantén la pregunta corta (máximo 40 palabras)
                4. Usa un tono conversacional
                5. Si tienes el nombre del usuario, úsalo para personalizar
                
                EJEMPLOS POR TIPO DE MAQUINARIA:
                
                SOLDADORAS:
                - Para amperaje: "¿Qué amperaje necesitas? Esto me ayuda a recomendarte el modelo correcto."
                - Para electrodo: "¿Qué tipo de electrodo vas a usar? Así verifico compatibilidad."
                
                COMPRESOR:
                - Para capacidad: "¿Qué capacidad de aire necesitas? Esto define la potencia adecuada."
                - Para herramientas: "¿Qué herramientas vas a conectar? Me ayuda a verificar compatibilidad."
                
                TORRE DE ILUMINACIÓN:
                - Para LED: "¿La prefieres con tecnología LED? Es más eficiente en consumo."
                
                LGMG:
                - Para altura: "¿Qué altura de trabajo necesitas? Debo asegurar que sea segura."
                - Para actividad: "¿Qué tipo de trabajo vas a realizar? Esto define el modelo más seguro."
                - Para ubicación: "¿Será en interior o exterior? Cada uno tiene características diferentes."
                
                GENERADORES:
                - Para actividad: "¿Para qué actividad lo usaras? Me ayuda a calcular la potencia."
                - Para capacidad: "¿Qué capacidad necesitas en kVA o kW? Esto define el tamaño."
                
                ROMPEDORES:
                - Para uso: "¿Para qué tipo de trabajo lo usarás? Esto define las características."
                - Para tipo: "¿Lo prefieres eléctrico o neumático? Depende de tu fuente de energía."
                
                Genera SOLO la pregunta (sin explicaciones adicionales):
                """
            )
            
            response = self.llm.invoke(prompt.format_prompt(
                tipo_maquinaria=tipo.value,
                field=field,
                reason=reason,
                nombre=current_state.get("nombre", "")
            ))
            
            question = response.content.strip()
            debug_print(f"DEBUG: Pregunta de maquinaria generada para '{field}': '{question}'")
            return question
            
        except Exception as e:
            print(f"Error generando pregunta de maquinaria: {e}")
            # Fallback a preguntas predefinidas basadas en llm.py
            fallback_questions = {
                "amperaje": "¿Qué amperaje requiere?",
                "electrodo": "¿Qué tipo de electrodo quema?",
                "capacidad_volumen": "¿Qué capacidad de volumen de aire requiere?",
                "herramientas": "¿Qué herramientas le va a conectar?",
                "es_led": "¿La requiere de LED?",
                "altura_trabajo": "¿Qué altura de trabajo necesita?",
                "actividad": "¿Qué actividad va a realizar?",
                "ubicacion": "¿Es en exterior o interior?",
                "capacidad": "¿Qué capacidad en kVA o kW necesita?",
                "uso": "¿Para qué lo va a utilizar?",
                "tipo": "¿Lo requiere eléctrico o neumático?"
            }
            return fallback_questions.get(field, "¿Podría darme más detalles?")
    
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
    
    def generate_response(self, message: str, extracted_info: Dict[str, Any], current_state: ConversationState, next_question: str = None) -> str:
        """Genera una respuesta contextual apropiada usando un enfoque conversacional similar a llm.py"""
        
        try:
            # Crear prompt conversacional basado en el estilo de llm.py
            prompt = ChatPromptTemplate.from_template(
                """
                Eres Juan, un asistente de ventas profesional especializado en maquinaria ligera en México.
                Tu trabajo es calificar leads de manera natural y conversacional.
                
                REGLAS IMPORTANTES:
                - Sé amigable pero profesional
                - Mantén respuestas CORTAS (máximo 50 palabras)
                - Explica brevemente por qué necesitas cada información cuando sea apropiado
                - Si el usuario hace preguntas sobre por qué necesitas ciertos datos, explícaselo de manera clara
                - Responde de manera natural y conversacional
                - Si se extrajo información nueva, confírmala de manera amigable
                - Si hay una siguiente pregunta, hazla de manera natural
                
                INFORMACIÓN EXTRAÍDA DEL ÚLTIMO MENSAJE:
                {extracted_info_str}
                
                ESTADO ACTUAL DE LA CONVERSACIÓN:
                - Nombre: {current_nombre}
                - Tipo de maquinaria: {current_tipo}
                - Detalles: {current_detalles}
                - Sitio web: {current_sitio_web}
                - Uso: {current_uso}
                - Nombre completo: {current_nombre_completo}
                - Empresa: {current_empresa}
                - Giro: {current_giro}
                - Correo: {current_correo}
                - Teléfono: {current_telefono}
                
                SIGUIENTE PREGUNTA A HACER (si aplica): {next_question}
                
                MENSAJE DEL USUARIO: {user_message}
                
                INSTRUCCIONES:
                1. Si se extrajo información nueva, confirma de manera amigable
                2. Si el usuario pregunta por qué necesitas ciertos datos, explica el propósito
                3. Si hay una siguiente pregunta, hazla de manera natural
                4. Mantén un tono profesional pero cálido
                5. No repitas información que ya confirmaste anteriormente
                
                EJEMPLOS DE RESPUESTAS:
                - Si se extrajo nombre: "¡Mucho gusto [nombre]!"
                - Si se extrajo maquinaria: "Perfecto, veo que necesita [tipo]. Esto me ayuda a revisar nuestro inventario."
                - Si se extrajo empresa: "Excelente, [empresa]. Esto me permite personalizar la cotización."
                - Para explicar por qué necesitas datos: "Necesito esta información para generar una cotización precisa y contactarlo después."
                
                Genera una respuesta natural y apropiada:
                """
            )
            
            # Preparar información extraída como string
            extracted_info_str = "Ninguna información nueva" if not extracted_info else json.dumps(extracted_info, ensure_ascii=False, indent=2)
            
            response = self.llm.invoke(prompt.format_prompt(
                user_message=message,
                extracted_info_str=extracted_info_str,
                current_nombre=current_state.get("nombre", "No especificado"),
                current_tipo=current_state.get("tipo_maquinaria", "No especificado"),
                current_detalles=json.dumps(current_state.get("detalles_maquinaria", {}), ensure_ascii=False),
                current_sitio_web=current_state.get("sitio_web", "No especificado"),
                current_uso=current_state.get("uso_empresa_o_venta", "No especificado"),
                current_nombre_completo=current_state.get("nombre_completo", "No especificado"),
                current_empresa=current_state.get("nombre_empresa", "No especificado"),
                current_giro=current_state.get("giro_empresa", "No especificado"),
                current_correo=current_state.get("correo", "No especificado"),
                current_telefono=current_state.get("telefono", "No especificado"),
                next_question=next_question or "No hay siguiente pregunta"
            ))
            
            result = response.content.strip()
            debug_print(f"DEBUG: Respuesta conversacional generada: '{result}'")
            return result
            
        except Exception as e:
            print(f"Error generando respuesta conversacional: {e}")
            # Fallback a la lógica simple anterior
            return self._generate_simple_response(extracted_info, next_question)
    
    def _generate_simple_response(self, extracted_info: Dict[str, Any], next_question: str = None) -> str:
        """Genera una respuesta simple como fallback"""
        response_parts = []
        
        # Confirmar información extraída
        if extracted_info:
            if "nombre" in extracted_info:
                response_parts.append(f"¡Mucho gusto {extracted_info['nombre']}!")
            
            if "tipo_maquinaria" in extracted_info:
                tipo = extracted_info["tipo_maquinaria"]
                response_parts.append(f"Perfecto, veo que necesita {tipo}.")
            
            if "detalles_maquinaria" in extracted_info:
                detalles = extracted_info["detalles_maquinaria"]
                if detalles:
                    response_parts.append("Excelente, he registrado esos detalles.")
        
        # Agregar la siguiente pregunta si existe
        if next_question:
            if response_parts:
                response_parts.append("")
                response_parts.append(next_question)
            else:
                return next_question
        
        return " ".join(response_parts) if response_parts else ""
    
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
# DETECTOR Y RESPONDEDOR DE PREGUNTAS SOBRE REQUERIMIENTOS
# ============================================================================

class RequirementQuestionHandler:
    """Maneja preguntas del usuario sobre por qué se necesita cierta información"""
    
    def __init__(self, llm):
        self.llm = llm
    
    def is_requirement_question(self, message: str) -> bool:
        """Determina si el usuario está preguntando por qué se necesita cierta información"""
        try:
            prompt = ChatPromptTemplate.from_template(
                """
                Analiza si el usuario está preguntando por qué necesitas cierta información o datos.
                
                EJEMPLOS DE PREGUNTAS SOBRE REQUERIMIENTOS:
                - "¿Por qué necesitas mi nombre?"
                - "¿Para qué quieres el teléfono?"
                - "¿Por qué preguntas sobre el giro de la empresa?"
                - "¿Para qué necesitas el correo?"
                - "¿Por qué me pides esa información?"
                - "¿Qué vas a hacer con mis datos?"
                - "¿Por qué es importante el sitio web?"
                - "¿Para qué necesitas saber el amperaje?"
                
                EJEMPLOS QUE NO SON PREGUNTAS SOBRE REQUERIMIENTOS:
                - "Mi nombre es Juan"
                - "No tengo sitio web"
                - "La empresa se llama ABC"
                - "¿Tienen soldadoras?"
                - "¿Cuánto cuesta?"
                
                Mensaje del usuario: {message}
                
                Responde SOLO con "true" si es pregunta sobre requerimientos, o "false" si no lo es.
                """
            )
            
            response = self.llm.invoke(prompt.format_prompt(message=message))
            result = response.content.strip().lower()
            
            debug_print(f"DEBUG: ¿Es pregunta sobre requerimientos? '{message}' → {result}")
            return result == "true"
            
        except Exception as e:
            print(f"Error detectando pregunta sobre requerimientos: {e}")
            return False
    
    def generate_requirement_explanation(self, message: str, current_state: ConversationState) -> str:
        """Genera una explicación sobre por qué se necesita cierta información"""
        try:
            # Obtener la última pregunta del bot para contexto
            last_bot_question = self._get_last_bot_question(current_state)
            
            prompt = ChatPromptTemplate.from_template(
                """
                Eres Juan, un asistente de ventas profesional especializado en maquinaria ligera en México.
                
                El usuario está preguntando por qué necesitas cierta información. Explícaselo de manera clara y profesional.
                
                PREGUNTA DEL USUARIO: {user_question}
                ÚLTIMA PREGUNTA QUE HICISTE: {last_question}
                
                ESTADO ACTUAL:
                - Nombre: {current_nombre}
                - Tipo de maquinaria: {current_tipo}
                
                REGLAS PARA LA EXPLICACIÓN:
                1. Sé honesto y transparente
                2. Explica el propósito específico de cada dato
                3. Tranquiliza sobre el uso responsable de la información
                4. Mantén un tono profesional y confiable
                5. Después de explicar, vuelve a hacer la pregunta de manera amable
                
                EXPLICACIONES COMUNES:
                
                Para NOMBRE:
                "Tu nombre me ayuda a personalizar la atención y generar una cotización formal. Es solo para identificarte en nuestro sistema."
                
                Para TELÉFONO:
                "El teléfono me permite darte seguimiento personalizado y resolver cualquier duda sobre la cotización de manera rápida."
                
                Para CORREO:
                "El correo es necesario para enviarte la cotización oficial con precios y detalles técnicos. Es la vía formal de entrega."
                
                Para EMPRESA Y GIRO:
                "Esta información me ayuda a entender mejor tus necesidades específicas y personalizar la recomendación. Cada industria tiene requerimientos diferentes."
                
                Para SITIO WEB:
                "Conocer su empresa me permite generar una cotización más precisa y entender el contexto de uso de la maquinaria."
                
                Para DATOS TÉCNICOS (amperaje, capacidad, etc.):
                "Estos detalles técnicos son fundamentales para recomendarte exactamente el equipo que necesitas y evitar problemas de compatibilidad."
                
                Para USO EMPRESA/VENTA:
                "Esto me permite ofrecerte las mejores condiciones comerciales. Tenemos opciones diferentes para usuarios finales y distribuidores."
                
                IMPORTANTE: Después de explicar, vuelve a hacer la pregunta original de manera amable.
                
                Genera tu respuesta:
                """
            )
            
            response = self.llm.invoke(prompt.format_prompt(
                user_question=message,
                last_question=last_bot_question or "No hay pregunta previa",
                current_nombre=current_state.get("nombre", "No especificado"),
                current_tipo=current_state.get("tipo_maquinaria", "No especificado")
            ))
            
            explanation = response.content.strip()
            debug_print(f"DEBUG: Explicación de requerimientos generada: '{explanation}'")
            return explanation
            
        except Exception as e:
            print(f"Error generando explicación de requerimientos: {e}")
            return "Te pido esta información para generar una cotización precisa y personalizada. Todos los datos son tratados de manera confidencial."
    
    def _get_last_bot_question(self, current_state: ConversationState) -> Optional[str]:
        """Obtiene la última pregunta que hizo el bot"""
        messages = current_state.get("messages", [])
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if "?" in content:
                    lines = content.split('\n')
                    for line in reversed(lines):
                        if "?" in line and line.strip():
                            return line.strip()
                    return content
        return None

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
        self.answer_cleaner = SpecificAnswerCleaner(self.llm)
        self.inventory_responder = InventoryResponder(self.llm)
        self.requirement_handler = RequirementQuestionHandler(self.llm)  # Nuevo manejador de preguntas sobre requerimientos
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
        """Procesa un mensaje del usuario con slot-filling inteligente, validación de respuestas específicas, respuestas sobre inventario y manejo de preguntas sobre requerimientos"""
        
        try:
            debug_print(f"DEBUG: send_message llamado con mensaje: '{user_message}'")
            
            # Si el mensaje está vacío, no hacer nada y esperar al usuario
            if not user_message or not user_message.strip():
                return ""
            
            # Si es el primer mensaje (no hay mensajes anteriores), generar saludo inicial
            if not self.state["messages"]:
                return self._generate_initial_greeting(user_message)
            
            # Agregar mensaje del usuario
            self.state["messages"].append({
                "role": "user", 
                "content": user_message
            })
            
            # PRIMERO: Verificar si es una pregunta sobre por qué se necesita cierta información
            if self.requirement_handler.is_requirement_question(user_message):
                debug_print(f"DEBUG: Pregunta sobre requerimientos detectada, generando explicación...")
                explanation = self.requirement_handler.generate_requirement_explanation(user_message, self.state)
                self.state["messages"].append({"role": "assistant", "content": explanation})
                debug_print(f"DEBUG: Explicación de requerimientos: {explanation}")
                return explanation
            
            # SEGUNDO: Extraer TODA la información disponible del mensaje (SIEMPRE)
            # Obtener la última pregunta del bot para contexto
            last_bot_question = self._get_last_bot_question()
            extracted_info = self.slot_filler.extract_all_information(user_message, self.state, last_bot_question)
            debug_print(f"DEBUG: Información extraída: {extracted_info}")
            
            # Actualizar el estado con la información extraída
            self._update_state_with_extracted_info(extracted_info)
            debug_print(f"DEBUG: Estado después de actualización: {self.state}")
            
            # ESPECIAL: Si la última pregunta era sobre detalles de maquinaria, procesar la respuesta específicamente
            if last_bot_question and self._is_maquinaria_detail_question(last_bot_question, self.state):
                debug_print(f"DEBUG: Procesando respuesta específica de maquinaria para pregunta: '{last_bot_question}'")
                self._process_maquinaria_response(user_message, last_bot_question, self.state)
                debug_print(f"DEBUG: Estado después de procesar respuesta de maquinaria: {self.state.get('detalles_maquinaria', {})}")
            
            # TERCERO: Verificar si es una pregunta sobre inventario
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
            
            # CUARTO: Si no es pregunta de inventario ni de requerimientos, continuar con el flujo normal
            debug_print(f"DEBUG: Flujo normal de calificación de leads...")
            
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
            
            # Obtener la siguiente pregunta necesaria
            next_question = self.slot_filler.get_next_question(self.state)
            debug_print(f"DEBUG: Siguiente pregunta: {next_question}")
            debug_print(f"DEBUG: Estado actual de detalles_maquinaria: {self.state.get('detalles_maquinaria', {})}")
            
            # Generar respuesta contextual usando el nuevo sistema mejorado
            contextual_response = self.response_generator.generate_response(
                user_message, extracted_info, self.state, next_question
            )
            debug_print(f"DEBUG: Respuesta contextual: {contextual_response}")
            
            if contextual_response:
                self.state["messages"].append({"role": "assistant", "content": contextual_response})
                return contextual_response
            elif next_question:
                # Si no hay respuesta contextual pero hay siguiente pregunta
                self.state["messages"].append({"role": "assistant", "content": next_question})
                return next_question
            else:
                # No hay más preguntas, la conversación debería estar completa
                debug_print(f"DEBUG: No hay más preguntas, verificando si la conversación está completa...")
                debug_print(f"DEBUG: Estado completo: {self.state}")
                final_message = "Gracias por toda la información. Estoy procesando su solicitud."
                self.state["messages"].append({"role": "assistant", "content": final_message})
                return final_message
        
        except Exception as e:
            print(f"Error procesando mensaje: {e}")
            return "Disculpe, hubo un error técnico. ¿Podría intentar de nuevo?"
    
    def _generate_initial_greeting(self, user_message: str) -> str:
        """Genera un saludo inicial conversacional basado en el primer mensaje del usuario"""
        try:
            # Agregar el mensaje del usuario al historial
            self.state["messages"].append({
                "role": "user", 
                "content": user_message
            })
            
            # Extraer información del primer mensaje
            extracted_info = self.slot_filler.extract_all_information(user_message, self.state)
            self._update_state_with_extracted_info(extracted_info)
            
            prompt = ChatPromptTemplate.from_template(
                """
                Eres Juan, un asistente de ventas profesional especializado en maquinaria ligera en México.
                
                El usuario acaba de iniciar una conversación contigo. Genera un saludo inicial natural y profesional.
                
                PRIMER MENSAJE DEL USUARIO: {user_message}
                
                INFORMACIÓN EXTRAÍDA: {extracted_info}
                
                REGLAS:
                1. Saluda de manera amigable y profesional
                2. Preséntate como Juan, especialista en maquinaria ligera
                3. Si extrajiste información, reconocéla de manera natural
                4. Haz la primera pregunta necesaria para continuar
                5. Mantén el mensaje corto pero cálido
                
                EJEMPLOS:
                
                Si el usuario solo saluda:
                "¡Hola! Soy Juan, tu asistente especializado en maquinaria ligera. ¿Con quién tengo el gusto?"
                
                Si el usuario menciona maquinaria:
                "¡Hola! Soy Juan, especialista en maquinaria ligera. Veo que necesitas [tipo]. ¿Con quién tengo el gusto?"
                
                Si el usuario da su nombre:
                "¡Hola [nombre]! Soy Juan, tu asistente especializado en maquinaria ligera. ¿Qué tipo de equipo estás buscando?"
                
                Genera tu saludo inicial:
                """
            )
            
            response = self.llm.invoke(prompt.format_prompt(
                user_message=user_message,
                extracted_info=json.dumps(extracted_info, ensure_ascii=False) if extracted_info else "Ninguna información extraída"
            ))
            
            initial_response = response.content.strip()
            
            # Agregar la respuesta al historial
            self.state["messages"].append({
                "role": "assistant", 
                "content": initial_response
            })
            
            debug_print(f"DEBUG: Saludo inicial generado: '{initial_response}'")
            return initial_response
            
        except Exception as e:
            print(f"Error generando saludo inicial: {e}")
            # Fallback a saludo simple
            fallback = "¡Hola! Soy Juan, tu asistente especializado en maquinaria ligera. ¿Con quién tengo el gusto?"
            self.state["messages"].append({
                "role": "assistant", 
                "content": fallback
            })
            return fallback
    
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
    
    def _process_maquinaria_response(self, user_message: str, last_question: str, state: ConversationState):
        """Procesa específicamente las respuestas a preguntas sobre detalles de maquinaria"""
        
        tipo = state.get("tipo_maquinaria")
        if not tipo:
            return
        
        # Determinar qué campo específico se está respondiendo basándose en la pregunta
        field = self._detect_maquinaria_field(last_question, tipo)
        
        if field:
            debug_print(f"DEBUG: Campo detectado para respuesta: '{field}'")
            
            # Extraer y limpiar el valor específico
            try:
                # Usar el sistema de limpieza para obtener solo la información relevante
                cleaned_value = self.answer_cleaner.clean_answer(user_message, last_question, tipo)
                
                # Verificar si la respuesta es negativa
                negative_indicators = ["no", "no sé", "no estoy seguro", "no tengo"]
                is_negative = any(indicator in user_message.lower() for indicator in negative_indicators)
                
                if is_negative:
                    cleaned_value = "No especificado"
                
                # Para el caso específico de LED, procesar respuestas de sí/no
                if field == "es_led":
                    if any(word in user_message.lower() for word in ["sí", "si", "yes", "claro", "por supuesto"]):
                        cleaned_value = "Sí"
                    elif any(word in user_message.lower() for word in ["no", "nope", "negativo"]):
                        cleaned_value = "No"
                
                # Actualizar el estado
                if "detalles_maquinaria" not in state:
                    state["detalles_maquinaria"] = {}
                
                # Limpiar campos alternativos para evitar duplicación
                alt_fields = self._get_field_alternatives(field)
                for alt_field in alt_fields:
                    if alt_field != field and alt_field in state["detalles_maquinaria"]:
                        debug_print(f"DEBUG: Eliminando campo alternativo '{alt_field}' para usar estándar '{field}'")
                        del state["detalles_maquinaria"][alt_field]
                
                state["detalles_maquinaria"][field] = cleaned_value
                debug_print(f"DEBUG: Campo '{field}' actualizado con valor '{cleaned_value}' en detalles de maquinaria")
                debug_print(f"DEBUG: Estado completo de detalles: {state['detalles_maquinaria']}")
                
            except Exception as e:
                debug_print(f"DEBUG: Error procesando respuesta de maquinaria: {e}")
    
    def _detect_maquinaria_field(self, question: str, tipo: MaquinariaType) -> Optional[str]:
        """Detecta qué campo de maquinaria se está preguntando basándose en keywords"""
        
        question_lower = question.lower()
        
        # Mapear keywords específicos por tipo de maquinaria (nombres estándar)
        field_keywords = {
            MaquinariaType.SOLDADORAS: {
                "amperaje": ["amperaje", "amp", "amperios", "corriente"],
                "electrodo": ["electrodo", "varilla", "material"]
            },
            MaquinariaType.COMPRESOR: {
                "capacidad_volumen": ["capacidad", "volumen", "aire", "pies", "litros", "cfm"],
                "herramientas": ["herramientas", "conectar", "equipos", "usar", "alimentar"]
            },
            MaquinariaType.TORRE_ILUMINACION: {
                "es_led": ["led", "tecnología", "luz", "iluminación", "prefieres", "requiere"]
            },
            MaquinariaType.LGMG: {
                "altura_trabajo": ["altura", "trabajo", "metros", "elevación"],
                "actividad": ["actividad", "trabajo", "realizar", "función"],
                "ubicacion": ["exterior", "interior", "ubicación", "lugar"]
            },
            MaquinariaType.GENERADORES: {
                "actividad": ["actividad", "para qué", "usar", "función"],
                "capacidad": ["capacidad", "potencia", "kva", "kw"]
            },
            MaquinariaType.ROMPEDORES: {
                "uso": ["utilizar", "trabajo", "usar", "función"],
                "tipo": ["eléctrico", "neumático", "tipo", "energía"]
            }
        }
        
        tipo_keywords = field_keywords.get(tipo, {})
        
        for field, keywords in tipo_keywords.items():
            for keyword in keywords:
                if keyword in question_lower:
                    debug_print(f"DEBUG: Campo '{field}' detectado por keyword '{keyword}'")
                    return field
        
        return None
    
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
                    
                if user_input.lower() == "estado":
                    estado = chatbot.get_lead_data_json()
                    print(f"🤖 Estado actual de la conversación:\n{estado}")
                    continue
                
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