import json
import os
from typing import Dict, Any, Optional, List
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
import langchain
from state_management import MaquinariaType, ConversationState, ConversationStateStore, InMemoryStateStore
from datetime import datetime, timezone
import logging
from hubspot_manager import HubSpotManager

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
# MODELOS DE DATOS
# ============================================================================

class DetallesSoldadora(BaseModel):
    amperaje: Optional[str] = Field(None, description="Amperaje requerido para la soldadora")
    electrodo: Optional[str] = Field(None, description="Tipo de electrodo que quema")

class DetallesCompresor(BaseModel):
    capacidad_volumen: Optional[str] = Field(None, description="Capacidad de volumen de aire requerida")
    herramientas_conectar: Optional[str] = Field(None, description="Herramientas que va a conectar")

class DetallesTorre(BaseModel):
    es_led: Optional[bool] = Field(None, description="Si requiere LED o no")

class DetallesPlataforma(BaseModel):
    altura_trabajo: Optional[str] = Field(None, description="Altura de trabajo necesaria")
    actividad: Optional[str] = Field(None, description="Actividad que va a realizar")
    ubicacion: Optional[str] = Field(None, description="Si es en interior o exterior")

class DetallesGenerador(BaseModel):
    actividad: Optional[str] = Field(None, description="Para qué actividad lo requiere")
    capacidad: Optional[str] = Field(None, description="Capacidad en kvas o kw necesaria")

class DetallesRompedor(BaseModel):
    uso: Optional[str] = Field(None, description="Para qué lo va a utilizar")
    tipo: Optional[str] = Field(None, description="Si lo requiere eléctrico o neumático")

class DetallesApisonador(BaseModel):
    uso: Optional[str] = Field(None, description="Para qué lo va a utilizar")
    motor: Optional[str] = Field(None, description="Qué tipo de motor trae")
    es_diafragma: Optional[bool] = Field(None, description="Si es de diafragma o no")

class DetallesMontacargas(BaseModel):
    capacidad: Optional[str] = Field(None, description="Capacidad requerida")
    tipo_energia: Optional[str] = Field(None, description="Si lo requiere eléctrico, a combustión a gasolina o gas lp")
    posicion_operador: Optional[str] = Field(None, description="Si lo requiere para hombre parado o sentado")
    altura: Optional[str] = Field(None, description="Altura requerida")

class DetallesManipulador(BaseModel):
    capacidad: Optional[str] = Field(None, description="Capacidad requerida")
    altura: Optional[str] = Field(None, description="Altura necesaria")
    actividad: Optional[str] = Field(None, description="Actividad que va a realizar")
    tipo_energia: Optional[str] = Field(None, description="Si lo requiere eléctrico o a combustión")

# ============================================================================
# DICCIONARIO CON CONFIGURACIÓN DE MAQUINARIA
# ============================================================================

MAQUINARIA_CONFIG = {
    MaquinariaType.SOLDADORAS: {
        "model": DetallesSoldadora,
        "fields": [
            {
                "name": "amperaje", 
                "reason": "Para recomendarte el modelo adecuado según tu trabajo",
                "question": "¿cuál es el amperaje que necesitas?",
                "required": True
            },
            {
                "name": "electrodo", 
                "reason": "Para asegurar compatibilidad con tus materiales",
                "question": "¿qué tipo de electrodo quemas?",
                "required": True
            }
        ]
    },
    MaquinariaType.COMPRESOR: {
        "model": DetallesCompresor,
        "fields": [
            {
                "name": "capacidad_volumen", 
                "reason": "Para seleccionar la potencia correcta",
                "question": "¿cuál es la capacidad de volumen de aire necesitas?",
                "required": True
            },
            {
                "name": "herramientas_conectar", 
                "reason": "Para verificar compatibilidad con tus equipos",
                "question": "¿qué herramientas le vas a conectar?",
                "required": True
            }
        ]
    },
    MaquinariaType.TORRE_ILUMINACION: {
        "model": DetallesTorre,
        "fields": [
            {
                "name": "es_led", 
                "reason": "Para determinar el tipo de iluminación necesario",
                "question": "¿prefieres iluminación LED?",
                "required": True
            }
        ]
    },
    MaquinariaType.PLATAFORMA: {
        "model": DetallesPlataforma,
        "fields": [
            {
                "name": "altura_trabajo", 
                "reason": "Para asegurar que la máquina alcance la altura necesaria",
                "question": "¿cuál es la altura de trabajo que necesitas?",
                "required": True
            },
            {
                "name": "actividad", 
                "reason": "Para entender el contexto de uso",
                "question": "¿qué actividad vas a realizar?",
                "required": True
            },
            {
                "name": "ubicacion", 
                "reason": "Para determinar el modelo más conveniente",
                "question": "¿es para interior o exterior?",
                "required": True
            }
        ]
    },
    MaquinariaType.GENERADORES: {
        "model": DetallesGenerador,
        "fields": [
            {
                "name": "actividad", 
                "reason": "Para entender el contexto de uso",
                "question": "¿para qué actividad lo requiere?",
                "required": True
            },
            {
                "name": "capacidad", 
                "reason": "Para determinar la potencia necesaria",
                "question": "¿qué capacidad en kvas o kw necesitas?",
                "required": True
            }
        ]
    },
    MaquinariaType.ROMPEDORES: {
        "model": DetallesRompedor,
        "fields": [
            {
                "name": "uso", 
                "reason": "Para entender el contexto de uso",
                "question": "¿para qué lo va a utilizar?",
                "required": True
            },
            {
                "name": "tipo", 
                "reason": "Para determinar el tipo de energía necesaria",
                "question": "¿lo requiere eléctrico o neumático?",
                "required": True
            }
        ]
    },
    MaquinariaType.APISONADOR: {
        "model": DetallesApisonador,
        "fields": [
            {
                "name": "uso", 
                "reason": "Para entender el contexto de uso",
                "question": "¿para qué lo va a utilizar?",
                "required": True
            },
            {
                "name": "motor", 
                "reason": "Para determinar las características del equipo",
                "question": "¿qué tipo de motor debe tener?",
                "required": True
            },
            {
                "name": "es_diafragma", 
                "reason": "Para determinar si lo requiere",
                "question": "¿el equipo debe ser de diafragma?",
                "required": True
            }
        ]
    },
    MaquinariaType.MONTACARGAS: {
        "model": DetallesMontacargas,
        "fields": [
            {
                "name": "capacidad", 
                "reason": "Para determinar la capacidad necesaria",
                "question": "¿qué peso requiere levantar?",
                "required": True
            },
            {
                "name": "tipo_energia", 
                "reason": "Para determinar el tipo de energía adecuado",
                "question": "¿lo requiere eléctrico, a combustión a gasolina o gas lp?",
                "required": True
            },
            {
                "name": "posicion_operador", 
                "reason": "Para determinar la posición del operador",
                "question": "¿lo requiere para hombre parado o sentado?",
                "required": True
            },
            {
                "name": "altura", 
                "reason": "Para determinar la altura necesaria",
                "question": "¿qué altura requiere?",
                "required": True
            }
        ]
    },
    MaquinariaType.MANIPULADOR: {
        "model": DetallesManipulador,
        "fields": [
            {
                "name": "capacidad", 
                "reason": "Para determinar la capacidad necesaria",
                "question": "¿qué peso requiere mover?",
                "required": True
            },
            {
                "name": "altura", 
                "reason": "Para determinar la altura necesaria",
                "question": "¿qué altura necesita?",
                "required": True
            },
            {
                "name": "actividad", 
                "reason": "Para entender el contexto de uso",
                "question": "¿qué actividad va a realizar?",
                "required": True
            },
            {
                "name": "tipo_energia", 
                "reason": "Para determinar el tipo de energía adecuado",
                "question": "¿lo requiere eléctrico o a combustión?",
                "required": True
            }
        ]
    }
}

# ============================================================================
# FUNCIONES HELPER PARA LA CONFIGURACIÓN DE MAQUINARIA
# ============================================================================

def get_required_fields_for_tipo(tipo: MaquinariaType) -> List[str]:
    """Obtiene lista de campos obligatorios para un tipo de maquinaria"""
    if tipo not in MAQUINARIA_CONFIG:
        return []
    
    config = MAQUINARIA_CONFIG[tipo]
    return [field["name"] for field in config["fields"] if field.get("required", True)]

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
            - apellido: {current_apellido}
            - tipo_maquinaria: {current_tipo}
            - detalles_maquinaria: {current_detalles}
            - sitio_web: {current_sitio_web}
            - uso_empresa_o_venta: {current_uso}
            - nombre_empresa: {current_nombre_empresa}
            - giro_empresa: {current_giro}
            - lugar_requerimiento: {current_lugar_requerimiento}
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
            - tipo_maquinaria: soldadora, compresor, torre_iluminacion, plataforma, generador, rompedor, apisonador, montacargas, manipulador
            - detalles_maquinaria: objeto con campos específicos según tipo_maquinaria
            - lugar_requerimiento: lugar donde se requiere la máquina
            - sitio_web: URL del sitio web o "No tiene" (para respuestas negativas como "no", "no tenemos", "no cuenta", etc.)
            - uso_empresa_o_venta: "uso empresa" o "venta"
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
            - Si el usuario dice "soy [nombre]", "me llamo [nombre]", "hola, soy [nombre]" → extraer nombre y apellido
            - Para nombres de 1 palabra: llenar solo "nombre"
            - Para nombres de 2+ palabras: llenar "nombre" con la primera palabra y "apellido" con el resto
            - Ejemplos: "soy Paco" → nombre: "Paco"
            - Ejemplos: "soy Paco Perez" → nombre: "Paco", apellido: "Perez"
            - Ejemplos: "soy Paco Perez Diaz" → nombre: "Paco", apellido: "Perez Diaz"
            
            REGLAS ESPECIALES PARA USO_EMPRESA_O_VENTA:
            - Si el usuario dice "para venta", "es para vender", "para comercializar" → uso_empresa_o_venta: "venta"
            - Si el usuario dice "para uso", "para usar", "para trabajo interno" → uso_empresa_o_venta: "uso empresa"
            
            EJEMPLOS DE EXTRACCIÓN:
            - Mensaje: "soy Renato Fuentes" → {{"nombre": "Renato", "apellido": "Fuentes"}}
            - Mensaje: "me llamo Mauricio Martinez Rodriguez" → {{"nombre": "Mauricio", "apellido": "Martinez Rodriguez"}}
            - Mensaje: "no hay pagina web" → {{"sitio_web": "No tiene"}}
            - Mensaje: "venta de maquinaria pesada" → {{"giro_empresa": "venta de maquinaria pesada"}}
            - Mensaje: "para venta" → {{"uso_empresa_o_venta": "venta"}}
            - Mensaje: "construcción y mantenimiento" → {{"giro_empresa": "construcción y mantenimiento"}}
            - Mensaje: "en la Ciudad de México" → {{"lugar_requerimiento": "Ciudad de México"}}
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

            REGLAS ESPECIALES PARA PREGUNTAS SOBRE INVENTARIO:
            - Si el usuario pregunta "¿tienen [tipo]?" → extraer [tipo] como tipo_maquinaria
            - Si el usuario pregunta "¿manejan [tipo]?" → extraer [tipo] como tipo_maquinaria  
            - Si el usuario pregunta "necesito [tipo]" → extraer [tipo] como tipo_maquinaria
            - Ejemplos: "¿tienen generadores?" → {{"tipo_maquinaria": "generador"}}
            - Ejemplos: "¿manejan soldadoras?" → {{"tipo_maquinaria": "soldadora"}}
            - Ejemplos: "necesito un compresor" → {{"tipo_maquinaria": "compresor"}}
            IMPORTANTE: Incluso en preguntas sobre inventario, SIEMPRE extraer tipo_maquinaria si se menciona
            
            REGLAS ADICIONALES PARA DETALLES DE MAQUINARIA - USA ESTOS NOMBRES EXACTOS:
            - Para TORRE_ILUMINACION: es_led (true/false para LED)
            - Para SOLDADORAS: amperaje, electrodo
            - Para COMPRESOR: capacidad_volumen, herramientas_conectar
            - Para PLATAFORMA: altura_trabajo, actividad, ubicacion
            - Para GENERADORES: actividad, capacidad
            - Para ROMPEDORES: uso, tipo
            - Para APISONADOR: uso, motor, es_diafragma
            - Para MONTACARGAS: capacidad, tipo_energia, posicion_operador, altura
            - Para MANIPULADOR: capacidad, altura, actividad, tipo_energia
            - IMPORTANTE: Usa exactamente estos nombres de campos, NO inventes nombres alternativos
            - NO extraer campos que no estén en esta lista exacta
            - NO inventar campos adicionales como "proyecto", "aplicación", "capacidad_de_volumen", etc.
            
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
                current_apellido=current_state.get("apellido", "No especificado"),
                current_tipo=current_state.get("tipo_maquinaria", "No especificado"),
                current_detalles=current_detalles_str,
                current_sitio_web=current_state.get("sitio_web", "No especificado"),
                current_uso=current_state.get("uso_empresa_o_venta", "No especificado"),
                current_nombre_empresa=current_state.get("nombre_empresa", "No especificado"),
                current_giro=current_state.get("giro_empresa", "No especificado"),
                current_lugar_requerimiento=current_state.get("lugar_requerimiento", "No especificado"),
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
            # Definir el orden de prioridad de los slots con explicaciones centralizadas
            slot_priority = [
                ("nombre", "¿Con quién tengo el gusto?", "Para brindarte atención personalizada"),
                ("apellido", "¿Cuál es tu apellido?", "Para completar tu información personal"), # Solo se pregunta si en nombre solo dice 1 palabra
                ("tipo_maquinaria", "¿Qué tipo de maquinaria requiere?", "Para revisar nuestro inventario disponible"),
                ("detalles_maquinaria", None, None),  # Se maneja por separado
                ("nombre_empresa", "¿Cuál es el nombre de su empresa?", "Para generar la cotización a nombre de su empresa"),
                ("giro_empresa", "¿Cuál es el giro de su empresa?", "Para entender mejor sus necesidades específicas"), # Se pregunta junto con nombre_empresa
                ("lugar_requerimiento", "¿En qué lugar necesita el equipo?", "Para coordinar la entrega del equipo"),
                ("uso_empresa_o_venta", "¿El equipo es para uso de la empresa o para venta?", "Para ofrecerle los mejores precios"),
                ("sitio_web", "¿Cuál es el sitio web de su empresa?", "Para conocer mejor su empresa y generar una cotización más precisa"),
                ("correo", "¿Cuál es su correo electrónico?", "Para enviarle la cotización"),
                ("telefono", "¿Cuál es su teléfono?", "Para darle seguimiento personalizado") # TODO: Solo se pregunta si está respondiendo todo de forma fluida
            ]
            
            # Verificar cada slot en orden de prioridad
            for slot_name, question, reason in slot_priority:
                if slot_name == "detalles_maquinaria":
                    # Manejar detalles específicos de maquinaria
                    question = self._get_maquinaria_detail_question_with_reason(current_state)
                    if question:
                        return {"question": question, "reason": "", "question_type": "detalles_maquinaria"}
                else:
                    # Verificar si el slot está vacío o tiene respuestas negativas
                    value = current_state.get(slot_name)
                    if not value:
                        # Si se debe preguntar por el nombre de la empresa y no se tiene el giro, preguntar por el giro de la empresa también
                        if slot_name == "nombre_empresa" and not current_state.get("giro_empresa"):
                            question = "¿Cuál es el nombre y giro de su empresa?"
                        
                        return {
                            "question": question, 
                            "reason": reason, 
                            "question_type": slot_name
                        }
            
            # Si todos los slots están llenos
            return None
            
        except Exception as e:
            print(f"Error generando siguiente pregunta: {e}")
            return None
    
    def _get_maquinaria_detail_question_with_reason(self, current_state: ConversationState) -> Optional[str]:
        """Obtiene la siguiente pregunta específica sobre detalles de maquinaria de manera conversacional con el motivo"""
        
        tipo = current_state.get("tipo_maquinaria")

        if not tipo or tipo not in MAQUINARIA_CONFIG:
            return None

        config = MAQUINARIA_CONFIG[tipo]
        detalles = current_state.get("detalles_maquinaria", {})

        # Buscar el primer campo de la configuración que no esté en los detalles
        for field_info in config["fields"]:
            field_name = field_info["name"]
            if not detalles.get(field_name):
                # Encontrado el siguiente campo a preguntar
                # Devolver la pregunta fija definida en la configuración centralizada
                full_text = field_info.get("reason") + ", " + field_info.get("question")
                return full_text

        return None # Todos los detalles están completos
    
    def is_conversation_complete(self, current_state: ConversationState) -> bool:
        """Verifica si la conversación está completa (todos los slots llenos)"""

        # Verificar si el nombre tiene al menos dos palabras (nombre + apellido)
        nombre = current_state.get("nombre", "")
        if not nombre or len(nombre.split()) < 2:
            return False
        
        required_fields = [
            "tipo_maquinaria", "lugar_requerimiento", "nombre_empresa", "giro_empresa",
            "sitio_web", "uso_empresa_o_venta", "correo", "telefono"
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
        
        # Usar la configuración centralizada para obtener campos obligatorios
        required_fields = get_required_fields_for_tipo(tipo)
        
        return all(
            field in detalles and 
            detalles[field] is not None and 
            detalles[field] != "" and 
            detalles[field] != "No especificado" 
            for field in required_fields
        )

# ============================================================================
# SISTEMA DE RESPUESTAS INTELIGENTES
# ============================================================================

class IntelligentResponseGenerator:
    """Genera respuestas inteligentes basadas en el contexto y la información extraída"""
    
    def __init__(self, llm):
        self.llm = llm
    
    def generate_response(self, message: str, extracted_info: Dict[str, Any], current_state: ConversationState, next_question: str = None, next_question_reason: str = None) -> str:
        """Genera una respuesta contextual apropiada usando un enfoque conversacional"""
        
        try:
            # Crear prompt conversacional basado en el estilo de llm.py
            prompt_str = """
                Eres un asesor comercial en Alpha C y un asistente de ventas profesional especializado en maquinaria de la empresa.
                Tu trabajo es calificar leads de manera natural y conversacional.
                
                REGLAS IMPORTANTES:
                - Sé amigable pero profesional
                - No te presentes, ni digas palabras como "Hola", "Soy un asesor comercial en Alpha C"
                - Mantén respuestas CORTAS (máximo 50 palabras)
                - Explica brevemente por qué necesitas cada información cuando sea apropiado
                - Si el usuario hace preguntas sobre por qué necesitas ciertos datos, explícaselo de manera clara

                INFORMACIÓN EXTRAÍDA DEL ÚLTIMO MENSAJE:
                {extracted_info_str}
                
                ESTADO ACTUAL DE LA CONVERSACIÓN:
                - Nombre: {current_nombre}
                - Tipo de maquinaria: {current_tipo}
                - Detalles: {current_detalles}
                - Empresa: {current_empresa}
                - Giro: {current_giro}
                - Lugar requerimiento: {current_lugar_requerimiento}
                - Sitio web: {current_sitio_web}
                - Uso: {current_uso}
                - Correo: {current_correo}
                - Teléfono: {current_telefono}
                
                SIGUIENTE PREGUNTA A HACER: {next_question}
                RAZÓN: {next_question_reason}
           
                MENSAJE DEL USUARIO: {user_message}
                
                INSTRUCCIONES:
                1. Si se extrajo información nueva, confirma de manera amigable
                2. Si el usuario pregunta por qué necesitas ciertos datos, explica el propósito
                3. Si hay una siguiente pregunta, hazla de manera natural
                4. Mantén un tono profesional pero cálido
                5. No repitas información que ya confirmaste anteriormente
                
                Genera una respuesta natural y apropiada:
            """
            
            prompt = ChatPromptTemplate.from_template(prompt_str)

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

            formatedPrompt = prompt.format_prompt(
                user_message=message,
                extracted_info_str=extracted_info_str,
                current_nombre=current_state.get("nombre", "No especificado"),
                current_tipo=current_state.get("tipo_maquinaria", "No especificado"),
                current_detalles=json.dumps(current_state.get("detalles_maquinaria", {}), ensure_ascii=False),
                current_sitio_web=current_state.get("sitio_web", "No especificado"),
                current_uso=current_state.get("uso_empresa_o_venta", "No especificado"),
                current_lugar_requerimiento=current_state.get("lugar_requerimiento", "No especificado"),
                current_empresa=current_state.get("nombre_empresa", "No especificado"),
                current_giro=current_state.get("giro_empresa", "No especificado"),
                current_correo=current_state.get("correo", "No especificado"),
                current_telefono=current_state.get("telefono", "No especificado"),
                next_question=next_question or "No hay siguiente pregunta",
                next_question_reason=next_question_reason or "No hay razón para la siguiente pregunta"
            )
            
            response = self.llm.invoke(formatedPrompt)
            
            result = response.content.strip()
            debug_print(f"DEBUG: Respuesta conversacional generada: '{result}'")
            return result
            
        except Exception as e:
            print(f"Error generando respuesta conversacional: {e}")
            # Fallback a la lógica simple si no se puede generar la respuesta
            if next_question and next_question_reason:
                return next_question + " " + next_question_reason
            else:
                return "En un momento le responderemos."
    
    def generate_final_response(self, current_state: ConversationState) -> str:
        """Genera la respuesta final cuando la conversación está completa"""
        
        return f"""¡Perfecto, {current_state['nombre']}! 

He registrado toda su información:
- Nombre: {current_state['nombre']}
- Maquinaria: {current_state['tipo_maquinaria'].value}
- Detalles: {json.dumps(current_state['detalles_maquinaria'], indent=2, ensure_ascii=False)}
- Empresa: {current_state['nombre_empresa']}
- Giro: {current_state['giro_empresa']}
- Lugar requerimiento: {current_state['lugar_requerimiento']}
- Uso: {current_state['uso_empresa_o_venta']}
- Sitio web: {current_state['sitio_web']}
- Correo: {current_state['correo']}
- Teléfono: {current_state['telefono']}

Procederé a generar su cotización. Nos pondremos en contacto con usted pronto.

¿Hay algo más en lo que pueda ayudarle?"""

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
            # TODO: Usar la pregunta para consultar inventario
            debug_print(f"DEBUG: Generando respuesta de inventario para pregunta: '{question}'")

            # Obtener el inventario actual
            result = "Actualmente tenemos el siguiente inventario:\n"
            result += f"- Tipo de maquinaria: {', '.join(self.inventory['tipo_maquinaria'])}\n"
            result += f"- Modelo: {self.inventory['modelo_maquinaria']}\n"
            result += f"- Ubicación: {self.inventory['ubicacion']}\n"

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
    
    def __init__(self, azure_config: AzureOpenAIConfig, state_store: Optional[ConversationStateStore] = None):
        self.azure_config = azure_config
        self.llm = azure_config.create_llm()
        self.slot_filler = IntelligentSlotFiller(self.llm)
        self.response_generator = IntelligentResponseGenerator(self.llm)
        self.inventory_responder = InventoryResponder(self.llm)
        
        # Usar el state_store proporcionado o crear uno en memoria por defecto
        self.state_store = state_store or InMemoryStateStore()
        self.current_user_id = None
        
        # El estado local sigue existiendo para compatibilidad con código existente
        self.state = self._create_empty_state()

    def _create_empty_state(self) -> ConversationState:
        """Crea un estado vacío"""
        return {
            "messages": [],
            "nombre": None,
            "apellido": None,
            "tipo_maquinaria": None,
            "detalles_maquinaria": {},
            "sitio_web": None,
            "uso_empresa_o_venta": None,
            "nombre_empresa": None,
            "giro_empresa": None,
            "correo": None,
            "telefono": None,
            "completed": False,
            "lugar_requerimiento": None,
            "conversation_mode": "bot",
            "asignado_asesor": None,
            "hubspot_contact_id": None
        }
    
    def load_conversation(self, user_id: str):
        """Carga la conversación de un usuario específico"""
        self.current_user_id = user_id
        stored_state = self.state_store.get_conversation_state(user_id)
        
        if stored_state:
            self.state = stored_state
            debug_print(f"DEBUG: Estado cargado para usuario {user_id}")
        else:
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
    
    def send_message(self, user_message: str, hubspot_manager: HubSpotManager = None) -> str:
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

            # Si es el primer mensaje (no hay mensajes anteriores), generar saludo inicial
            if not self.state["messages"]:
                contextual_response += "¡Hola! Soy un asesor comercial en Alpha C. "
            
            # Agregar mensaje del usuario
            self.state["messages"].append({
                "role": "user", 
                "content": user_message,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sender": "lead"
            })

            # Extraer TODA la información disponible del mensaje (SIEMPRE)
            # Obtener la última pregunta del bot para contexto
            last_bot_question = self._get_last_bot_question()
            extracted_info = self.slot_filler.extract_all_information(user_message, self.state, last_bot_question)
            debug_print(f"DEBUG: Información extraída: {extracted_info}") 
            
            # Actualizar el contacto en HubSpot
            if hubspot_manager:
                hubspot_manager.update_contact(self.state, extracted_info)

            # Actualizar el estado con la información extraída
            self._update_state_with_extracted_info(extracted_info)
            debug_print(f"DEBUG: Estado después de actualización: {self.state}")

            # Verificar modo de conversación antes de generar respuesta
            current_mode = self.state.get("conversation_mode", "bot")
            
            if current_mode == "agente":
                # Modo agente: solo guardar estado, no generar respuesta automática
                debug_print(f"DEBUG: Modo agente activo, no generando respuesta automática")
                self.save_conversation()
                return None  # No response en modo agente
            
            # Verificar si es una pregunta sobre inventario
            if self.inventory_responder.is_inventory_question(user_message):
                debug_print(f"DEBUG: Pregunta sobre inventario detectada, generando respuesta...")
                inventory_response = self.inventory_responder.generate_inventory_response(user_message)

                # Si es el primer mensaje, agregar saludo inicial, el cual ya se agregó al contextual_response
                inventory_response = contextual_response + inventory_response
                
                # Obtener la siguiente pregunta necesaria para continuar el flujo
                next_question = self.slot_filler.get_next_question(self.state)
                
                if next_question:
                    # TODO: Usar el generador de respuestas para generar la respuesta de la siguiente pregunta cuando se haga una pregunta de inventario
                    # Combinar respuesta de inventario con la siguiente pregunta
                    inventory_response = inventory_response + "\n\n" + next_question["question"] + "\n\n" + next_question['reason']
                    debug_print(f"DEBUG: Respuesta combinada (inventario + siguiente pregunta): {inventory_response}")
                
                return self._add_message_and_return_response("assistant", inventory_response)
            
            # Si no es pregunta de inventario ni de requerimientos, continuar con el flujo normal
            debug_print(f"DEBUG: Flujo normal de calificación de leads...")

            # Verificar si la conversación está completa (solo en modo bot)
            if self.slot_filler.is_conversation_complete(self.state):
                debug_print(f"DEBUG: Conversación completa!")
                self.state["completed"] = True
                final_response = self.response_generator.generate_final_response(self.state)
                return self._add_message_and_return_response("assistant", final_response)
            
            # Obtener la siguiente pregunta necesaria
            next_question = self.slot_filler.get_next_question(self.state)

            if next_question == None:
                debug_print(f"DEBUG: Estado completo: {self.state}")
                final_message = "Gracias por toda la información. Estoy procesando su solicitud."
                return self._add_message_and_return_response("assistant", final_message)

            next_question_str = next_question["question"]
            next_question_reason = next_question["reason"]

            debug_print(f"DEBUG: Siguiente pregunta: {next_question_str}")

            next_question_type = next_question['question_type']
            debug_print(f"DEBUG: Tipo de siguiente pregunta: {next_question_type}")

            # Para preguntas específicas de maquinaria, generar respuesta simple sin LLM
            if next_question["question_type"] == "detalles_maquinaria":
                if extracted_info and extracted_info.get("tipo_maquinaria"):
                    contextual_response += f"Entendido. {next_question_str}"
                else:
                    # Si solo hay confirmación de información extraída
                    confirmation_parts = []
                    if extracted_info:
                        for key, value in extracted_info.items():
                            if key == "nombre" and value:
                                confirmation_parts.append(f"¡Perfecto, {value}!")
                            elif key == "tipo_maquinaria" and value:
                                confirmation_parts.append(f"Entendido.")
                    
                    if confirmation_parts:
                        contextual_response += " ".join(confirmation_parts) + " " + next_question_str
                    else:
                        contextual_response += next_question_str
            else:
                # Para preguntas normales, usar el LLM
                generated_response = self.response_generator.generate_response(
                    user_message, extracted_info, self.state, next_question_str, next_question_reason
                )
                contextual_response += generated_response

            return self._add_message_and_return_response("assistant", contextual_response)
        
        except Exception as e:
            print(f"Error procesando mensaje: {e}")
            return "Disculpe, hubo un error técnico. ¿Podría intentar de nuevo?"
        
    def _add_message_and_return_response(self, message_type: str, response: str) -> str:
        """
        Añade un mensaje al estado y devuelve la respuesta final
        """
        self.state["messages"].append({
            "role": message_type, 
            "content": response,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sender": "bot" if message_type == "assistant" else "lead"
        })
        
        # Al final, guardar el estado
        self.save_conversation()

        return response
    
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

            # 2. No sobrescribir campos que ya tienen un valor válido a excepción de detalles_maquinaria.
            # detalles_maquinaria se actualiza múltiples veces porque tiene varios subcampos.
            # Esto es clave para evitar que una respuesta ambigua posterior
            # borre un dato que ya se había confirmado.
            current_value = self.state.get(key)
            if key != "detalles_maquinaria" and current_value and current_value not in ["No especificado", "No tiene", None, ""]:
                debug_print(f"DEBUG: Campo '{key}' ya tiene valor válido '{current_value}', no se sobrescribe.")
                continue

            # 3. Manejo de casos especiales
            if key == "detalles_maquinaria" and isinstance(value, dict):
                current_detalles = self.state.get("detalles_maquinaria", {})
                current_detalles.update(value)
                self.state["detalles_maquinaria"] = current_detalles
                debug_print(f"DEBUG: Detalles de maquinaria actualizados: {self.state['detalles_maquinaria']}")
            
            elif key == "tipo_maquinaria":
                try:
                    self.state[key] = MaquinariaType(value)
                    debug_print(f"DEBUG: Campo '{key}' actualizado a (Enum): {self.state[key]}")
                except ValueError:
                    # Si el LLM extrae un tipo inválido, lo registramos pero no detenemos el flujo.
                    print(f"ADVERTENCIA: Tipo de maquinaria inválido '{value}' extraído por el LLM.")
            
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
    
    def get_conversation_summary(self) -> Dict[str, Any]:
        """Obtiene un resumen completo del lead calificado"""
        return {
            "nombre": self.state["nombre"],
            "apellido": self.state["apellido"],
            "tipo_maquinaria": self.state["tipo_maquinaria"],
            "detalles_maquinaria": self.state["detalles_maquinaria"],
            "nombre_empresa": self.state["nombre_empresa"],
            "sitio_web": self.state["sitio_web"],
            "giro_empresa": self.state["giro_empresa"],
            "lugar_requerimiento": self.state["lugar_requerimiento"],
            "uso_empresa_o_venta": self.state["uso_empresa_o_venta"],
            "correo": self.state["correo"],
            "telefono": self.state["telefono"],
            "conversacion_completa": self.state["completed"],
            "mensajes_total": len(self.state["messages"])
        }
    
    def get_lead_data_json(self) -> str:
        """Obtiene los datos del lead en formato JSON"""
        return json.dumps(self.get_conversation_summary(), indent=2, ensure_ascii=False)