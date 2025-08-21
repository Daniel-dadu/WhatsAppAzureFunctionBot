"""
Gestión del LLM (Azure OpenAI GPT-4.1-mini)
"""

import json
import re
from typing import List, Dict
from openai import AzureOpenAI
from models import ConversationState, InventoryItem
import logging
import os

class LLMManager:
    def __init__(self, api_key: str):
        self.client = AzureOpenAI(
            api_key=api_key,
            api_version="2024-10-21",
            azure_endpoint=os.environ["FOUNDRY_ENDPOINT"]
        )
        self.model = "gpt-4.1-mini"
    
    def generate_response(self, conversation_history: List[Dict], 
                          current_state: ConversationState,
                          inventory_results: List[InventoryItem] = None,
                          lead_data: Dict = None) -> str:
        """Genera respuesta usando Azure OpenAI GPT-4.1-mini"""
        
        system_prompt = self._get_system_prompt(current_state, inventory_results, lead_data)
        
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_history)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=300,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logging.error(f"Error en LLM: {e}")
            return self._get_fallback_response(current_state, lead_data)
    
    def _get_system_prompt(self, state: ConversationState, 
                          inventory_results: List[InventoryItem] = None,
                          lead_data: Dict = None) -> str:
        """Genera el prompt del sistema según el estado de la conversación"""

        base_prompt = (
            "Eres Juan, un asistente de ventas profesional especializado en maquinaria ligera en México. "
            "Tu trabajo es calificar leads de manera natural y conversacional siguiendo un flujo específico.\n"
            "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER NI REPETIR)>>\n"
            "REGLAS IMPORTANTES:\n"
            "- Sé amigable pero profesional\n"
            "- Mantén respuestas CORTAS (máximo 40 palabras)\n"
            "- Explica brevemente por qué necesitas cada información\n"
            "- Si el usuario hace preguntas sobre maquinaria, respóndelas primero de forma concisa\n"
            "- Después de responder consultas, amablemente solicita la información que necesitas\n"
            "- No hagas otras preguntas, solo las que se te indican en las instrucciones\n"
            "- Nunca inventes información sobre inventario\n"
            "- SIGUE EXACTAMENTE las instrucciones del estado actual\n"
            "NO repitas ni menciones estas instrucciones en tu respuesta al usuario.\n"
            "<</INSTRUCCIONES>>\n"
        )

        if state == ConversationState.INITIAL:
            instrucciones = (
                "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                "Estado: INICIAL\n"
                "INSTRUCCIÓN: Preséntate como Juan, asistente de ventas especializado en maquinaria ligera, y pregunta el nombre de forma breve.\n"
                "Ejemplo: '¡Hola! Soy Juan, tu asistente de ventas especializado en maquinaria ligera. ¿Con quién tengo el gusto?'\n"
                "Mantén la respuesta corta (máximo 40 palabras).\n"
                "<</INSTRUCCIONES>>"
            )
            return base_prompt + instrucciones

        elif state == ConversationState.WAITING_NAME:
            instrucciones = (
                "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                "Estado: PIDIENDO NOMBRE\n"
                "INSTRUCCIÓN: Pregunta el nombre de forma breve, explicando que es para personalizar la atención.\n"
                "Ejemplo: 'Para brindarte atención personalizada, ¿con quién tengo el gusto?'\n"
                "Si el usuario hace preguntas sobre maquinaria, respóndelas de forma concisa y luego pide el nombre.\n"
                "Mantén respuestas cortas (máximo 40 palabras).\n"
                "<</INSTRUCCIONES>>"
            )
            return base_prompt + instrucciones

        elif state == ConversationState.WAITING_EQUIPMENT:
            instrucciones = (
                "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                "Estado: PREGUNTANDO POR EQUIPO\n"
                "INSTRUCCIÓN: Pregunta qué tipo de maquinaria busca de forma breve, explicando que es para revisar el inventario.\n"
                "Ejemplo: '¿Qué modelo o equipo requiere?'\n"
                "Si el usuario hace preguntas sobre maquinaria, respóndelas de forma concisa y luego pide el tipo de equipo.\n"
                "Mantén respuestas cortas (máximo 40 palabras).\n"
                "<</INSTRUCCIONES>>"
            )
            return base_prompt + instrucciones

        elif state == ConversationState.WAITING_EQUIPMENT_QUESTIONS:
            equipment_type = lead_data.get('equipment_interest', '').lower() if lead_data else ''
            current_question_index = lead_data.get('current_question_index', 0) if lead_data else 0
            
            if 'soldadora' in equipment_type or 'soldar' in equipment_type:
                instrucciones = (
                    "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                    "Estado: PREGUNTANDO CARACTERÍSTICAS DE SOLDADORA\n"
                    "INSTRUCCIÓN: Pregunta SOLO UNA pregunta específica sobre el amperaje o tipo de electrodo.\n"
                    "Ejemplo: '¿Qué amperaje requiere?'\n"
                    "Mantén respuestas cortas (máximo 40 palabras).\n"
                    "<</INSTRUCCIONES>>"
                )
            elif 'compresor' in equipment_type:
                instrucciones = (
                    "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                    "Estado: PREGUNTANDO CARACTERÍSTICAS DE COMPRESOR\n"
                    "INSTRUCCIÓN: Pregunta SOLO UNA pregunta específica sobre la capacidad de volumen de aire o herramienta.\n"
                    "Ejemplo: '¿Qué capacidad de volumen de aire requiere?'\n"
                    "Mantén respuestas cortas (máximo 40 palabras).\n"
                    "<</INSTRUCCIONES>>"
                )
            elif 'torre' in equipment_type and 'iluminacion' in equipment_type:
                instrucciones = (
                    "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                    "Estado: PREGUNTANDO CARACTERÍSTICAS DE TORRE DE ILUMINACIÓN\n"
                    "INSTRUCCIÓN: Pregunta SOLO UNA pregunta específica sobre el requerimiento LED.\n"
                    "Ejemplo: '¿La requiere de LED?'\n"
                    "Mantén respuestas cortas (máximo 40 palabras).\n"
                    "<</INSTRUCCIONES>>"
                )
            elif 'lgmg' in equipment_type:
                # LGMG tiene 3 preguntas, hacer una por vez
                if current_question_index == 0:
                    instrucciones = (
                        "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                        "Estado: PREGUNTANDO CARACTERÍSTICAS DE LGMG - PREGUNTA 1\n"
                        "INSTRUCCIÓN: Pregunta SOLO la primera pregunta sobre la altura de trabajo.\n"
                        "Ejemplo: '¿Qué altura de trabajo necesita?'\n"
                        "Mantén respuestas cortas (máximo 40 palabras).\n"
                        "<</INSTRUCCIONES>>"
                    )
                elif current_question_index == 1:
                    instrucciones = (
                        "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                        "Estado: PREGUNTANDO CARACTERÍSTICAS DE LGMG - PREGUNTA 2\n"
                        "INSTRUCCIÓN: Pregunta SOLO la segunda pregunta sobre la actividad.\n"
                        "Ejemplo: '¿Qué actividad va a realizar?'\n"
                        "Mantén respuestas cortas (máximo 40 palabras).\n"
                        "<</INSTRUCCIONES>>"
                    )
                elif current_question_index == 2:
                    instrucciones = (
                        "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                        "Estado: PREGUNTANDO CARACTERÍSTICAS DE LGMG - PREGUNTA 3\n"
                        "INSTRUCCIÓN: Pregunta SOLO la tercera pregunta sobre la ubicación.\n"
                        "Ejemplo: '¿Es en exterior o interior?'\n"
                        "Mantén respuestas cortas (máximo 40 palabras).\n"
                        "<</INSTRUCCIONES>>"
                    )
                else:
                    instrucciones = (
                        "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                        "Estado: PREGUNTANDO CARACTERÍSTICAS DE LGMG - PREGUNTA FINAL\n"
                        "INSTRUCCIÓN: Pregunta SOLO la pregunta final sobre la ubicación.\n"
                        "Ejemplo: '¿Es en exterior o interior?'\n"
                        "Mantén respuestas cortas (máximo 40 palabras).\n"
                        "<</INSTRUCCIONES>>"
                    )
            elif 'generador' in equipment_type:
                # Generador tiene 2 preguntas, hacer una por vez
                if current_question_index == 0:
                    instrucciones = (
                        "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                        "Estado: PREGUNTANDO CARACTERÍSTICAS DE GENERADOR - PREGUNTA 1\n"
                        "INSTRUCCIÓN: Pregunta SOLO la primera pregunta sobre la actividad.\n"
                        "Ejemplo: '¿Para qué actividad lo requiere?'\n"
                        "Mantén respuestas cortas (máximo 40 palabras).\n"
                        "<</INSTRUCCIONES>>"
                    )
                elif current_question_index == 1:
                    instrucciones = (
                        "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                        "Estado: PREGUNTANDO CARACTERÍSTICAS DE GENERADOR - PREGUNTA 2\n"
                        "INSTRUCCIÓN: Pregunta SOLO la segunda pregunta sobre la capacidad.\n"
                        "Ejemplo: '¿Qué capacidad en kVA o kW?'\n"
                        "Mantén respuestas cortas (máximo 40 palabras).\n"
                        "<</INSTRUCCIONES>>"
                    )
                else:
                    instrucciones = (
                        "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                        "Estado: PREGUNTANDO CARACTERÍSTICAS DE GENERADOR - PREGUNTA FINAL\n"
                        "INSTRUCCIÓN: Pregunta SOLO la pregunta final sobre la capacidad.\n"
                        "Ejemplo: '¿Qué capacidad en kVA o kW?'\n"
                        "Mantén respuestas cortas (máximo 40 palabras).\n"
                        "<</INSTRUCCIONES>>"
                    )
            elif 'rompedor' in equipment_type:
                instrucciones = (
                    "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                    "Estado: PREGUNTANDO CARACTERÍSTICAS DE ROMPEDOR\n"
                    "INSTRUCCIÓN: Pregunta SOLO UNA pregunta específica sobre el uso.\n"
                    "Ejemplo: '¿Para qué lo vas a utilizar?'\n"
                    "Mantén respuestas cortas (máximo 40 palabras).\n"
                    "<</INSTRUCCIONES>>"
                )
            else:
                instrucciones = (
                    "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                    "Estado: PREGUNTANDO CARACTERÍSTICAS GENERALES\n"
                    "INSTRUCCIÓN: Pregunta características específicas del equipo mencionado.\n"
                    "Ejemplo: '¿Podrías darme más detalles sobre las características que necesitas?'\n"
                    "Mantén respuestas cortas (máximo 40 palabras).\n"
                    "<</INSTRUCCIONES>>"
                )
            return base_prompt + instrucciones

        elif state == ConversationState.WAITING_DISTRIBUTOR:
            instrucciones = (
                "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                "Estado: PREGUNTANDO SI ES DISTRIBUIDOR\n"
                "INSTRUCCIÓN: Pregunta si es distribuidor de forma breve.\n"
                "Ejemplo: '¿Es distribuidor?'\n"
                "Mantén respuestas cortas (máximo 40 palabras).\n"
                "<</INSTRUCCIONES>>"
            )
            return base_prompt + instrucciones

        elif state == ConversationState.WAITING_QUOTATION_DATA:
            instrucciones = (
                "<<INSTRUCCIONES DEL SISTEMA (NO RESPONDER)>>\n"
                "Estado: PIDIENDO DATOS DE COTIZACIÓN\n"
                "INSTRUCCIÓN: Solicita todos los datos necesarios para la cotización en un solo mensaje.\n"
                "Ejemplo: 'Para poder ayudarte con la cotización necesito estos datos:\n"
                "1. ¿Es para uso de la empresa o para venta?\n"
                "2. Nombre completo\n"
                "3. Nombre y giro de tu empresa\n"
                "4. Correo electrónico\n"
                "5. Número telefónico'\n"
                "Mantén respuestas claras y organizadas.\n"
                "<</INSTRUCCIONES>>"
            )
            return base_prompt + instrucciones

        return base_prompt

    def _get_fallback_response(self, state: ConversationState, lead_data: Dict = None) -> str:
        """Respuestas de respaldo si falla el LLM"""
        fallbacks = {
            ConversationState.INITIAL: "¡Hola! Soy Juan, tu asistente de ventas especializado en maquinaria ligera. ¿Con quién tengo el gusto?",
            ConversationState.WAITING_NAME: "Para brindarte atención personalizada, ¿con quién tengo el gusto?",
            ConversationState.WAITING_EQUIPMENT: "¿Qué modelo o equipo requiere?",
            ConversationState.WAITING_EQUIPMENT_QUESTIONS: "¿Podrías darme más detalles sobre las características que necesitas?",
            ConversationState.WAITING_DISTRIBUTOR: "¿Es distribuidor?",
            ConversationState.WAITING_QUOTATION_DATA: "Para poder ayudarte con la cotización necesito estos datos:\n1. ¿Es para uso de la empresa o para venta?\n2. Nombre completo\n3. Nombre y giro de tu empresa\n4. Correo electrónico\n5. Número telefónico"
        }
        return fallbacks.get(state, "¿Podrías repetir esa información?")
    
    def extract_field(self, message: str, field_type: str) -> str:
        """Extrae un campo específico usando Azure OpenAI y devuelve el valor limpio"""
        
        extraction_prompts = {
            "company_name": (
                "Extrae el nombre de la empresa del siguiente mensaje si el mensaje solo contiene la empresa o si el usuario indica explícitamente que trabaja en, representa, pertenece a, es de, o su empresa es la mencionada. "
                "Ignora marcas, equipos o palabras genéricas. Si no hay una indicación clara de relación laboral o pertenencia, responde con 'value': null. "
                "Responde ÚNICAMENTE en formato JSON con la clave 'value'."
            ),
            "company_business": (
                "Extrae el giro o actividad de la empresa del siguiente mensaje si el usuario menciona explícitamente el tipo de negocio, giro, actividad o sector de su empresa. "
                "Ignora nombres de empresas, marcas o equipos. Si no hay una indicación clara del giro empresarial, responde con 'value': null. "
                "Responde ÚNICAMENTE en formato JSON con la clave 'value'."
            ),
            "name": (
                "Extrae el nombre de la persona del siguiente mensaje si el mensaje solo contiene un nombre o si el usuario lo menciona explícitamente como su nombre, o si se presenta como tal. "
                "Ignora saludos, apodos, nombres de empresas, marcas o equipos. Si no hay una indicación clara de nombre personal, responde con 'value': null. "
                "Responde ÚNICAMENTE en formato JSON con la clave 'value'."
            ),
            "phone": (
                "Extrae el número de teléfono del siguiente mensaje si el usuario lo proporciona de cualquier forma, por ejemplo: 'mi número es', 'puedes contactarme al', 'es', 'te dejo mi número', etc. "
                "Acepta cualquier número con formato de teléfono (dígitos, espacios, guiones, paréntesis, etc.) que parezca un número de contacto. Si no hay un número de teléfono válido, responde con 'value': null. "
                "Responde ÚNICAMENTE en formato JSON con la clave 'value'."
            ),
            "email": (
                "Extrae la dirección de email del siguiente mensaje si el mensaje solo contiene un email o si el usuario la proporciona explícitamente como su correo electrónico, el correo de su empresa o el correo al que se puede contactar. "
                "Ignora textos que no tengan formato de email o que no estén acompañados de una indicación clara de ser un email. Si no hay un email válido, responde con 'value': null. "
                "Responde ÚNICAMENTE en formato JSON con la clave 'value'."
            ),
            "equipment": (
                "Extrae el tipo de equipo o maquinaria del siguiente mensaje si el mensaje solo contiene un tipo de equipo o maquinaria o si el usuario lo menciona explícitamente como el equipo que busca, requiere o le interesa. "
                "Ignora menciones genéricas, marcas, empresas o equipos que no sean solicitados explícitamente. Si no hay una indicación clara de equipo de interés, responde con 'value': null. "
                "Responde ÚNICAMENTE en formato JSON con la clave 'value'."
            ),
            "is_distributor": (
                "Determina si el usuario es distribuidor basándote en el siguiente mensaje. "
                "Si el usuario menciona que es distribuidor, revendedor, que va a revender, distribuir, rentar, o cualquier actividad comercial, responde con 'value': true. "
                "Si el usuario menciona que es para uso propio, de su empresa, o uso final, responde con 'value': false. "
                "Si no hay una indicación clara, responde con 'value': null. "
                "Responde ÚNICAMENTE en formato JSON con la clave 'value'."
            ),
            "use_type": (
                "Determina el tipo de uso del equipo basándote en el siguiente mensaje. "
                "Si el usuario menciona que es para uso propio, de su empresa, o uso final, responde con 'value': 'uso_empresa'. "
                "Si el usuario menciona que es para revender, distribuir, rentar, o cualquier actividad comercial, responde con 'value': 'venta'. "
                "Si no hay una indicación clara, responde con 'value': null. "
                "Responde ÚNICAMENTE en formato JSON con la clave 'value'."
            )
        }
        
        prompt = f"{extraction_prompts[field_type]}\n\nMensaje: {message}"
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            return self._parse_json_response(result)
            
        except Exception as e:
            logging.error(f"Error extrayendo {field_type}: {e}")
            return ""

    def extract_quotation_data(self, message: str) -> Dict[str, str]:
        """Extrae todos los datos de cotización de un mensaje usando Azure OpenAI"""
        
        prompt = (
            "Extrae los siguientes datos de cotización del mensaje del usuario:\n"
            "1. Tipo de uso (uso_empresa o venta)\n"
            "2. Nombre completo\n"
            "3. Nombre de la empresa\n"
            "4. Giro de la empresa\n"
            "5. Correo electrónico\n"
            "6. Número telefónico\n\n"
            "Responde ÚNICAMENTE en formato JSON con las claves: use_type, name, company_name, company_business, email, phone.\n"
            "Si algún dato no está presente, usa 'value': null para ese campo.\n\n"
            f"Mensaje: {message}"
        )
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            return self._parse_quotation_data_response(result)
            
        except Exception as e:
            logging.error(f"Error extrayendo datos de cotización: {e}")
            return {}

    def _parse_quotation_data_response(self, result: str) -> Dict[str, str]:
        """Parsea la respuesta JSON de datos de cotización"""
        
        # Limpiar markdown si está presente
        result = re.sub(r'^```.*?\n', '', result)
        result = re.sub(r'\n```$', '', result)
        result = result.strip('`')
        
        # Extraer solo el objeto JSON
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            result = json_match.group(0)
        
        try:
            parsed = json.loads(result)
            return {
                'use_type': parsed.get('use_type', ''),
                'name': parsed.get('name', ''),
                'company_name': parsed.get('company_name', ''),
                'company_business': parsed.get('company_business', ''),
                'email': parsed.get('email', ''),
                'phone': parsed.get('phone', '')
            }
        except json.JSONDecodeError:
            logging.warning(f"JSON inválido en datos de cotización: {result}")
            return {}

    def _parse_json_response(self, result: str) -> str:
        """Parsea la respuesta JSON del LLM y extrae el valor"""
        
        # Limpiar markdown si está presente
        result = re.sub(r'^```.*?\n', '', result)  # Remover ```json
        result = re.sub(r'\n```$', '', result)    # Remover ``` final
        result = result.strip('`')                # Remover backticks simples
        
        # Extraer solo el objeto JSON (desde { hasta })
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            result = json_match.group(0)
        
        try:
            # Intentar parsear como JSON
            parsed = json.loads(result)
            value = parsed.get('value')
            
            # Normalizar valores nulos o vacíos
            if value is None or (isinstance(value, str) and value.strip().lower() in ('null', '', 'n/a')):
                return ""
            
            return str(value).strip()
            
        except json.JSONDecodeError:
            # Fallback: extraer valor usando regex
            logging.warning(f"JSON inválido, usando fallback: {result}")
            
            # Buscar patrón "value": "contenido"
            value_match = re.search(r'"value":\s*"([^"]*)"', result)
            if value_match:
                value = value_match.group(1)
                return "" if value.lower() in ('null', 'n/a') else value
            
            # Buscar patrón value: contenido (sin comillas)
            value_match = re.search(r'"?value"?:\s*([^,}\n]+)', result)
            if value_match:
                value = value_match.group(1).strip().strip('"')
                return "" if value.lower() in ('null', 'n/a') else value
            
            # Si todo falla, devolver vacío
            return ""