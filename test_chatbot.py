import os
import json
import argparse
import copy
from typing import List, Dict, Any, Optional, Set
import re
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

# Importa las clases necesarias de tu archivo de chatbot
from ai_langchain import IntelligentLeadQualificationChatbot, AzureOpenAIConfig

# Importar la clase de los guardrails
from check_guardrails import ContentSafetyGuardrails

# Agregar después de la línea 6 (from datetime import datetime)
import time

_selected_test_numbers: Optional[Set[int]] = None
_defined_test_numbers: Set[int] = set()
_executed_test_numbers: Set[int] = set()
_failed_test_numbers: Set[int] = set()


def parse_test_selection(value: str) -> Set[int]:
    """Convierte selecciones como ``5-15,20,22`` en números de flujo."""
    selected: Set[int] = set()
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            raise argparse.ArgumentTypeError("La selección contiene un elemento vacío.")

        if "-" in part:
            bounds = [bound.strip() for bound in part.split("-", 1)]
            if not all(bound.isdigit() for bound in bounds):
                raise argparse.ArgumentTypeError(f"Rango inválido: '{part}'.")
            start, end = map(int, bounds)
            if start < 1 or end < 1 or start > end:
                raise argparse.ArgumentTypeError(f"Rango inválido: '{part}'.")
            selected.update(range(start, end + 1))
        elif part.isdigit() and int(part) > 0:
            selected.add(int(part))
        else:
            raise argparse.ArgumentTypeError(f"Número de prueba inválido: '{part}'.")

    return selected


def _flow_number(test_name: str) -> int:
    match = re.match(r"Flujo\s+(\d+):", test_name)
    if not match:
        raise ValueError(f"El nombre de prueba no incluye un número de flujo: {test_name}")
    return int(match.group(1))

# Agregar después de la función _sanitize_filename (línea 51)
def _get_timestamp() -> str:
    """Genera un timestamp en formato HH:MM:SS.MS"""
    now = datetime.now()
    return now.strftime("%H:%M:%S") + f".{now.microsecond // 10000:02d}"

# ============================================================================
# CONFIGURACIÓN INICIAL
# ============================================================================

from azure.cosmos import CosmosClient
from maquinaria_config import machinery_config_service

def setup_chatbot() -> IntelligentLeadQualificationChatbot:
    """
    Configura y devuelve una instancia del chatbot.
    Asegúrate de tener tus variables de entorno configuradas.
    """
    # Verifica que las variables de entorno estén configuradas
    if "FOUNDRY_ENDPOINT" not in os.environ or "FOUNDRY_API_KEY" not in os.environ:
        print("\n❌ ERROR: Variables de entorno no encontradas.")
        print("Por favor, asegúrate de configurar 'FOUNDRY_ENDPOINT' y 'FOUNDRY_API_KEY' para continuar.")
        exit()

    # Configurar Cosmos DB
    cosmos_client = None
    db_name = None
    if "COSMOS_CONNECTION_STRING" in os.environ and "COSMOS_DB_NAME" in os.environ:
        try:
            print("🔌 Conectando a Cosmos DB...")
            cosmos_client = CosmosClient.from_connection_string(os.environ["COSMOS_CONNECTION_STRING"])
            db_name = os.environ["COSMOS_DB_NAME"]
            
            # Re-inicializar servicios globales con el cliente
            machinery_config_service.__init__(cosmos_client, db_name)
            print("✅ Conexión a Cosmos DB exitosa.")
        except Exception as e:
            print(f"⚠️ Error conectando a Cosmos DB: {e}")
            print("⚠️ Se usará inventario local (fallback).")

    # Configura las credenciales de Azure OpenAI desde las variables de entorno
    azure_config = AzureOpenAIConfig(
        endpoint=os.getenv("FOUNDRY_ENDPOINT"),
        api_key=os.getenv("FOUNDRY_API_KEY"),
        deployment_name="gpt-4.1-mini", # O el nombre de tu deployment
        api_version="2024-12-01-preview",
        model_name="gpt-4.1-mini"
    )
    
    chatbot = IntelligentLeadQualificationChatbot(azure_config, cosmos_client=cosmos_client, db_name=db_name)
    return chatbot

# ============================================================================
# FUNCIÓN DE PRUEBA
# ============================================================================

def _sanitize_filename(name: str) -> str:
    s = re.sub(r"[^\w\-_. ]", "_", name)
    s = s.replace(" ", "_")
    return s

def run_conversation_test(
    test_name: str,
    chatbot: IntelligentLeadQualificationChatbot,
    conversation_flow: List[str],
    expected_data: Dict[str, Any],
    expected_substrings: List[str] = None,
    forbidden_substrings: List[str] = None,
    expected_minimum_occurrences: Dict[str, int] = None,
    expected_maximum_occurrences: Dict[str, int] = None,
    expected_first_response_substrings: List[str] = None,
    initial_state: Dict[str, Any] = None,
    simulate_pdf_send: bool = False
):
    """
    Ejecuta un flujo de conversación de prueba y compara los resultados.
    Guarda todo el output de la prueba en un archivo .txt y solo imprime
    en consola cuando inicia y cuando termina la prueba.

    Parámetros opcionales para verificar el TEXTO del bot (no solo el estado):
    - expected_substrings: subcadenas que DEBEN aparecer en alguna respuesta del bot.
    - forbidden_substrings: subcadenas que NO deben aparecer en ninguna respuesta
      (ej: "$" para confirmar que no se filtró un precio).
        - expected_minimum_occurrences: número mínimo de respuestas del bot que deben
            contener cada texto; permite detectar mensajes repetidos o ciclos.
        - expected_maximum_occurrences: número máximo de respuestas del bot que pueden
            contener cada texto; permite comprobar que un aviso no se repita.
        - expected_first_response_substrings: textos que deben aparecer en la primera
            respuesta del bot.
        - initial_state: estado previo opcional para probar de forma determinista un
            tramo específico de una conversación real.
    - simulate_pdf_send: si True, instala un callback stub de envío de PDF y un
      current_user_id temporal para que `_try_send_pdf_quotation` pueda completarse
      (en modo prueba normal no hay callback, así que siempre devolvería False).
      El estado sigue guardándose SOLO en memoria (InMemoryStateStore). Se restaura
      el estado original del chatbot al terminar.
    """
    test_number = _flow_number(test_name)
    _defined_test_numbers.add(test_number)
    if _selected_test_numbers is not None and test_number not in _selected_test_numbers:
        return

    _executed_test_numbers.add(test_number)

    # Solo informar inicio en consola
    print(f"INICIANDO PRUEBA: {test_name}")

    output_lines: List[str] = []
    output_lines.append("==================================================")
    output_lines.append(f"✨ Resultado de la prueba: {test_name}")
    output_lines.append("==================================================\n")
    output_lines.append(f"--- INICIANDO PRUEBA: {test_name} ---\n")

    # Reinicia el estado del chatbot para una prueba limpia
    chatbot.reset_conversation()
    if initial_state:
        chatbot.state.update(copy.deepcopy(initial_state))

    # Opcional: simular contexto de WhatsApp para poder verificar el envío/re-envío
    # del PDF de cotización. Se restaura en el finally para no contaminar otras pruebas.
    _saved_user_id = chatbot.current_user_id
    _saved_pdf_cb = chatbot.send_pdf_callback
    if simulate_pdf_send:
        chatbot.current_user_id = "test_pdf_user"
        chatbot.send_pdf_callback = lambda *args, **kwargs: "stub_pdf_msg_id"

    try:
        # Una sola instancia del guardrails
        guardrails = ContentSafetyGuardrails()

        # Simula la conversación
        bot_responses: List[str] = []
        for i, user_message in enumerate(conversation_flow):
            time.sleep(2) # Evitar rate limits
            timestamp = _get_timestamp()
            output_lines.append(f"[{timestamp}] 👤 Usuario: {user_message}")

            # safety_result = guardrails.check_message_safety(user_message)
            # if safety_result:
            #     timestamp = _get_timestamp()
            #     output_lines.append(f"[{timestamp}] ❌ Bot: {safety_result['message']}")
            #     continue

            bot_response = chatbot.send_message(user_message)
            bot_responses.append(bot_response or "")
            timestamp = _get_timestamp()
            output_lines.append(f"[{timestamp}] 🤖 Bot: {bot_response}\n")

        # Al final del flujo, obtenemos el estado final
        final_state = chatbot.state

        # Comparar los resultados
        output_lines.append(f"--- FINALIZANDO PRUEBA: {test_name} ---")
        output_lines.append("📊 Comparando resultados extraídos vs. esperados...\n")

        has_errors = False
        for key, expected_value in expected_data.items():
            extracted_value = final_state.get(key)

            # Manejo especial para comparar enums y diccionarios
            if isinstance(expected_value, dict):
                try:
                    ev = json.dumps(expected_value, sort_keys=True)
                    xv = json.dumps(extracted_value, sort_keys=True)
                except TypeError:
                    ev = str(expected_value)
                    xv = str(extracted_value)
                if ev != xv:
                    has_errors = True
                    output_lines.append(f"❌ ERROR en '{key}':")
                    output_lines.append(f"   -> Esperado: {ev}")
                    output_lines.append(f"   -> Extraído: {xv}")
            else:
                if extracted_value != expected_value:
                    has_errors = True
                    output_lines.append(f"❌ ERROR en '{key}':")
                    output_lines.append(f"   -> Esperado: '{expected_value}'")
                    output_lines.append(f"   -> Extraído: '{extracted_value}'")

        # Verificación opcional del TEXTO de las respuestas del bot
        all_bot_text = "\n".join(bot_responses)
        if expected_substrings:
            for needle in expected_substrings:
                if needle.lower() not in all_bot_text.lower():
                    has_errors = True
                    output_lines.append(f"❌ ERROR de mensaje: se esperaba que el bot dijera algo con '{needle}', pero no apareció.")
        if forbidden_substrings:
            for needle in forbidden_substrings:
                if needle.lower() in all_bot_text.lower():
                    has_errors = True
                    output_lines.append(f"❌ ERROR de mensaje: el bot NO debía decir '{needle}', pero apareció.")
        if expected_minimum_occurrences:
            for needle, minimum in expected_minimum_occurrences.items():
                occurrences = sum(needle.lower() in response.lower() for response in bot_responses)
                if occurrences < minimum:
                    has_errors = True
                    output_lines.append(
                        f"❌ ERROR de repetición: '{needle}' apareció en {occurrences} respuestas; "
                        f"se esperaban al menos {minimum}."
                    )
                else:
                    output_lines.append(
                        f"🔁 REPETICIÓN DETECTADA: '{needle}' apareció en {occurrences} respuestas."
                    )
        if expected_maximum_occurrences:
            for needle, maximum in expected_maximum_occurrences.items():
                occurrences = sum(needle.lower() in response.lower() for response in bot_responses)
                if occurrences > maximum:
                    has_errors = True
                    output_lines.append(
                        f"❌ ERROR de repetición: '{needle}' apareció en {occurrences} respuestas; "
                        f"se permitían como máximo {maximum}."
                    )
                else:
                    output_lines.append(
                        f"✅ SIN CICLO: '{needle}' apareció en {occurrences} respuestas."
                    )
        if expected_first_response_substrings:
            first_response = bot_responses[0] if bot_responses else ""
            for needle in expected_first_response_substrings:
                if needle.lower() not in first_response.lower():
                    has_errors = True
                    output_lines.append(
                        f"❌ ERROR de presentación: la primera respuesta debía incluir '{needle}'."
                    )

        if not has_errors:
            output_lines.append("✅ ¡ÉXITO! Toda la información fue extraída correctamente.")
        else:
            _failed_test_numbers.add(test_number)
            output_lines.append("\n⚠️ PRUEBA FALLIDA. Se encontraron discrepancias.")

        output_lines.append(f"\n--- RESUMEN FINAL DEL ESTADO PARA '{test_name}' ---")
        output_lines.append(json.dumps(final_state, default=str, indent=2, ensure_ascii=False))
        output_lines.append("--------------------------------------------------\n")

        # Preparar carpeta y archivo de salida
        out_dir = os.path.join(os.path.dirname(__file__), "test_results")
        os.makedirs(out_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = _sanitize_filename(test_name)
        filename = f"test_{safe_name}_{timestamp}.txt"
        filepath = os.path.join(out_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(output_lines))

        # Solo informar finalización en consola
        print(f"TERMINADA PRUEBA: {test_name} -> {filepath}\n")
    finally:
        # Restaurar el contexto original del chatbot
        if simulate_pdf_send:
            chatbot.current_user_id = _saved_user_id
            chatbot.send_pdf_callback = _saved_pdf_cb

# ============================================================================
# DEFINICIÓN DE LOS FLUJOS DE CONVERSACIÓN
# ============================================================================

def define_test_flows(chatbot: IntelligentLeadQualificationChatbot):
    """
    Define y ejecuta los 3 flujos de conversación de prueba.
    """
    
    # ------------------------------------------------------------------------
    # Flujo 1: Usuario Directo y Colaborador
    # Este usuario responde a las preguntas de manera clara y una por una.
    # ------------------------------------------------------------------------
    flujo_1 = [
        "Hola",
        "Me llamo Ana",
        "Mi apellido es Gómez",
        "Busco una torre de iluminación.",
        "Sí, quiero la maquina 1",
        "No nos dedicamos a la venta de maquinaria, es para uso de nuestra empresa. Mi correo es ana.gomez@constresol.com y estamos ubicados en Puebla",
        "Claro. La empresa se llama 'Construcciones del Sol' y nos dedicamos a la construcción de carreteras."
    ]
    
    esperado_1 = {
        "nombre": "Ana Gómez",
        "apellido": "Gómez",
        "tipo_maquinaria": "torre_iluminacion",
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Shindaiwa SL433IDG-B/S1W",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "Construcciones del Sol",
        "giro_empresa": "construcción de carreteras",
        "lugar_requerimiento": "Puebla",
        "correo": "ana.gomez@constresol.com"
    }
    
    run_conversation_test("Flujo 1: Usuario Directo", chatbot, flujo_1, esperado_1)
    
    # ------------------------------------------------------------------------
    # Flujo 2: Usuario que da Múltiples Datos
    # Este usuario proporciona varios datos en una sola respuesta.
    # ------------------------------------------------------------------------
    flujo_2 = [
        "Qué tal, soy Roberto. Necesito una plataforma de elevación.",
        "mi apellido es Marquez",
        "La prefiero de articulada",
        "la necesito de 11 metros",
        "alimentacion electrica",
        "Me interesa la primera",
        "sí, me dedico a la venta. mi email es rob@ventas.com y estoy en CDMX",
        "claro, aquí te dejo mi constancia"
    ]
    
    esperado_2 = {
        "nombre": "Roberto Marquez",
        "apellido": "Marquez",
        "tipo_maquinaria": "plataforma",
        "detalles_maquinaria": {
            "tipo_plataforma": "articulada",
            "altura_trabajo_m": 11,
            "tipo_alimentacion": "electrica"
        },
        "quiere_cotizacion": True,
        "tipo_cliente": "distribuidor",
        "lugar_requerimiento": "CDMX",
        "correo": "rob@ventas.com",
        "constancia_fiscal_entregada": True
    }
    
    run_conversation_test("Flujo 2: Usuario con Múltiples Datos", chatbot, flujo_2, esperado_2)

    # ------------------------------------------------------------------------
    # Flujo 3: Usuario que Pregunta y se Desvía
    # Este usuario hace preguntas al bot, probando los manejadores de inventario y requerimientos.
    # ------------------------------------------------------------------------
    flujo_3 = [
        "Hola, ¿tienen generadores en existencia?",
        "Ok, necesito uno para mineria. Soy Lucía Martinez.",
        "La potencia debe ser de 7.2 kW",
        "En qué estados pueden hacer entrega?, quiero cotizarla",
        "Sí, dadu@gmail.com, la necesito en Tamaulipas",
        "Construcciones del Norte, 8112345678"
    ]
    
    esperado_3 = {
        "nombre": "Lucía Martinez",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {
            "potencia_kw": 7.2
        },
        "quiere_cotizacion": True,
        "tipo_cliente": "distribuidor",
        "nombre_empresa": "Construcciones del Norte",
        "lugar_requerimiento": "Tamaulipas",
        "correo": "dadu@gmail.com",
        "telefono": "8112345678"
    }
    
    run_conversation_test("Flujo 3: Usuario que Pregunta", chatbot, flujo_3, esperado_3)

    # ------------------------------------------------------------------------
    # Flujo 4: Bot no hace pregunta del tipo de alimentación de plataforma porque es de tijera
    # ------------------------------------------------------------------------
    flujo_4 = [
        "hola, soy Daniel Maldonado y quiero una plataforma",
        "la quiero de tijera",
        "de 10 metros",
        "quiero la segunda",
        "no",
        "trabajo en MachinesCorp, nos dedicamos a la construcción, en Puebla. correo mi@mail.com y tel 529931340372"
    ]

    esperado_4 = {
        "nombre": "Daniel Maldonado",
        "apellido": "Maldonado",
        "tipo_maquinaria": "plataforma",
        "detalles_maquinaria": {
            "tipo_plataforma": "tijera",
            "altura_trabajo_m": 10
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "LGMG S2632E II",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "MachinesCorp",
        "giro_empresa": "construcción",
        "lugar_requerimiento": "Puebla",
        "correo": "mi@mail.com",
        "telefono": "529931340372"
    }

    run_conversation_test("Flujo 4: Usuario con Múltiples Datos", chatbot, flujo_4, esperado_4)

    # ------------------------------------------------------------------------
    # Flujo 5: Usuario que selecciona máquina específica
    # ------------------------------------------------------------------------
    flujo_5 = [
        "Hola, quiero una torre de luz",
        "Soy Juan Perez",
        "quiero la segunda",
        "si, me dedico a la venta de maquinaria, mi correo es juan@gmail.com y estamos en Tlaxcala",
        "no la tengo",
        "nos dedicamos a la construcción",
        "ConstruccionesTop Inc."
    ]

    esperado_5 = {
        "nombre": "Juan Perez",
        "apellido": "Perez",
        "tipo_maquinaria": "torre_iluminacion",
        "quiere_cotizacion": True,
        "tipo_cliente": "distribuidor",
        "correo": "juan@gmail.com",
        "lugar_requerimiento": "Tlaxcala",
        "constancia_fiscal_entregada": "No tiene",
        "giro_empresa": "construcción",
        "nombre_empresa": "ConstruccionesTop Inc."
    }

    run_conversation_test("Flujo 5: Selección de máquina específica", chatbot, flujo_5, esperado_5)

    # ------------------------------------------------------------------------
    # Flujo 6: Selección de máquina con nombre específico
    # Este flujo prueba que se extraiga correctamente el modelo de la máquina
    # seleccionada y que solo se muestre el precio de esa máquina al final.
    # ------------------------------------------------------------------------
    flujo_6 = [
        "hola, Soy Daniel Maldonado",
        "quiero un generador",
        "20 kw",
        "si, cotizame el primero que es Shindaiwa DGM250MK-D",
        "es para uso de la empresa",
        "trabajo en Alfa Construcciones, nos dedicamos a la construcción, en Puebla. correo mi@mail.com y tel 529931340372"
    ]

    esperado_6 = {
        "nombre": "Daniel Maldonado",
        "apellido": "Maldonado",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {
            "potencia_kw": 20
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Shindaiwa DGM250MK-D",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "Alfa Construcciones",
        "giro_empresa": "construcción",
        "lugar_requerimiento": "Puebla",
        "correo": "mi@mail.com",
        "telefono": "529931340372"
    }

    run_conversation_test("Flujo 6: Selección de máquina con nombre específico", chatbot, flujo_6, esperado_6)

    # ------------------------------------------------------------------------
    # Flujo 8: Selección por código parcial de una máquina SIN precio
    # El usuario selecciona "DG100MI-400" (→ "Shindaiwa DG100MI-400"), modelo que
    # NO tiene mapping de precio en model_code_mapping.py. Verifica que:
    #   - La selección por nombre parcial sí resuelve el modelo completo.
    #   - Al no haber precio, el bot deriva a un asesor y NO genera cotización/PDF.
    # (Antes este flujo estaba mal etiquetado como validación de precio.)
    # ------------------------------------------------------------------------
    flujo_8 = [
        "Hola, soy María López",
        "Necesito un generador",
        "25 kw",
        "Me interesa la DG100MI-400, quiero cotización por favor",
        "No, estamos en Chiapas",
        "Trabajo en IndustrialMex, nos dedicamos a la manufactura, mi correo es maria@industrialmex.com y tel 442 111 2233"
    ]

    esperado_8 = {
        "nombre": "María López",
        "apellido": "López",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {
            "potencia_kw": 25
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Shindaiwa DG100MI-400",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "IndustrialMex",
        "giro_empresa": "manufactura",
        "lugar_requerimiento": "Chiapas",
        "correo": "maria@industrialmex.com",
        "telefono": "442 111 2233"
    }

    run_conversation_test(
        "Flujo 8: Selección por código parcial (máquina sin precio)", chatbot, flujo_8, esperado_8,
        expected_substrings=["asesor"],
        forbidden_substrings=["Procederé a generar su cotización", "$"]
    )

    # ------------------------------------------------------------------------
    # Flujo 9: Selección de máquina con código parcial (sin marca)
    # Este flujo prueba que el bot muestre el precio incluso cuando el usuario
    # selecciona una máquina usando solo el código del modelo (ej: "DGM250MK-D")
    # sin el nombre completo de la marca (ej: "Shindaiwa DGM250MK-D").
    # Valida el fuzzy matching del pricing service.
    # ------------------------------------------------------------------------
    flujo_9 = [
        "hola, quiero un generador",
        "Daniel Maldonado",
        "7.2 kw",
        "y me puedes cotizar también una plataforma de 10 metros de altura",
        "de tijera",
        "Quiero esa",
        "es para uso de la empresa",
        "nos dedicamos a la construcción",
        "trabajo en MachinesCorp en Puebla",
        "mi correo es dan@gmail.com y mi teléfono es 5555555555"
    ]

    esperado_9 = {
        "nombre": "Daniel Maldonado",
        "apellido": "Maldonado",
        "tipo_maquinaria": "plataforma",
        "detalles_maquinaria": {"altura_trabajo_m": 10, "tipo_plataforma": "tijera"},
        "quiere_cotizacion": True,
        "maquina_seleccionada": "LGMG S2632E II",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "MachinesCorp",
        "giro_empresa": "construcción",
        "lugar_requerimiento": "Puebla",
        "correo": "dan@gmail.com",
        "telefono": "5555555555"
    }

    run_conversation_test("Flujo 9: Selección de máquina con código parcial", chatbot, flujo_9, esperado_9)

    # ------------------------------------------------------------------------
    # Flujo 10: Plataforma Unipersonal
    # Este flujo prueba que el sistema extraiga 'unipersonal' y recomiende 
    # correctamente el modelo LGMG MP0607SE.
    # ------------------------------------------------------------------------
    flujo_10 = [
        "Hola, me llamo Laura Mendoza",
        "Busco una plataforma",
        "unipersonal",
        "de 8 metros de altura de trabajo",
        "Me interesa la LGMG MP0607SE",
        "dadu@gmail.com",
        "ah sí, nos dedicamos a la renta de maquinaria",
        "estamos ubicados en Querétaro, pero no tengo la constancia",
        "bueno, en realidad nos dedicamos a la construcción",
        "trabajo en MachinesTop"
    ]

    esperado_10 = {
        "nombre": "Laura Mendoza",
        "apellido": "Mendoza",
        "tipo_maquinaria": "plataforma",
        "detalles_maquinaria": {
            "tipo_plataforma": "unipersonal",
            "altura_trabajo_m": 8,
        },
        "quiere_cotizacion": True,
        "tipo_cliente": "cliente_final",
        "lugar_requerimiento": "Querétaro",
        "correo": "dadu@gmail.com",
        "constancia_fiscal_entregada": "No tiene",
        "giro_empresa": "construcción",
        "nombre_empresa": "MachinesTop",
        "maquina_seleccionada": "LGMG MP0607SE"
    }

    run_conversation_test("Flujo 10: Plataforma Unipersonal", chatbot, flujo_10, esperado_10)

    # ------------------------------------------------------------------------
    # Flujo 11: Plataforma Mástil
    # Este flujo prueba que el sistema extraiga 'mástil' y recomiende
    # correctamente el modelo LGMG M2640JE.
    # ------------------------------------------------------------------------
    flujo_11 = [
        "Buenas, soy Ricardo Silva",
        "necesito rentar maquinaria",
        "plataforma de elevacion",
        "mástil",
        "10 metros",
        "Si",
        "cliente_final",
        "Empresa Silva Construcciones, construcción, Estado de Mexico, rs@silvacons.com"
    ]

    esperado_11 = {
        "nombre": "Ricardo Silva",
        "apellido": "Silva",
        "tipo_maquinaria": "plataforma",
        "detalles_maquinaria": {
            "tipo_plataforma": "mástil",
            "altura_trabajo_m": 10
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "LGMG M2640JE",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "Silva Construcciones",
        "giro_empresa": "construcción",
        "lugar_requerimiento": "Estado de Mexico",
        "correo": "rs@silvacons.com"
    }

    run_conversation_test("Flujo 11: Plataforma Mástil", chatbot, flujo_11, esperado_11)

    # ------------------------------------------------------------------------
    # Flujo 13: Selección de máquina implícita por contexto único
    # Prueba la refactorización para inferir el nombre de modelo (ej. SDG150S)
    # cuando el bot le da solo una opción al lead y este contesta "ok esa opción".
    # ------------------------------------------------------------------------
    flujo_13 = [
        "hola, quiero un rompedor",
        "Soy Daniel Maldonado",
        "quiero la segunda máquina",
        "es para uso propio",
        "trabajo en Alfa Construcciones, nos dedicamos a la construcción, en Puebla. correo mi@mail.com y tel 529931340372"
    ]

    esperado_13 = {
        "nombre": "Daniel Maldonado",
        "apellido": "Maldonado",
        "tipo_maquinaria": "rompedor",
        "detalles_maquinaria": {},
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Toku TPB-90",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "Alfa Construcciones",
        "giro_empresa": "construcción",
        "lugar_requerimiento": "Puebla",
        "correo": "mi@mail.com",
        "telefono": "529931340372"
    }

    run_conversation_test("Flujo 13: Selección de máquina implícita", chatbot, flujo_13, esperado_13)

    # ------------------------------------------------------------------------
    # Flujo 15: Soldadora <= 200A 
    # ------------------------------------------------------------------------
    flujo_15 = [
        "Hola, soy Daniel Perez, quiero una soldadora de 200 amperes",
        "quiero esa opción",
        "cliente_final",
        "trabajo en X, giro industrial, Ciudad de Mexico, correo d@mail.com tel 555"
    ]

    esperado_15 = {
        "nombre": "Daniel Perez",
        "apellido": "Perez",
        "tipo_maquinaria": "soldadora",
        "detalles_maquinaria": {
            "amperaje_amps_max": 200
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Shindaiwa EGW185MS",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "X",
        "giro_empresa": "giro industrial",
        "lugar_requerimiento": "Ciudad de Mexico",
        "correo": "d@mail.com",
        "telefono": "555"
    }

    run_conversation_test("Flujo 15: Soldadora", chatbot, flujo_15, esperado_15)

    # ------------------------------------------------------------------------
    # Flujo 16: Soldadora > 200A (Omite Combustible)
    # ------------------------------------------------------------------------
    flujo_16 = [
        "quiero una soldadora de 300 amperes, soy Luis Torres",
        "quiero la primera",
        "para venta",
        "Soy de la Cdmx, luis@mail.com, tel 555"
    ]

    esperado_16 = {
        "nombre": "Luis Torres",
        "apellido": "Torres",
        "tipo_maquinaria": "soldadora",
        "detalles_maquinaria": {
            "amperaje_amps_max": 300
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Shindaiwa DGW340DM",
        "tipo_cliente": "distribuidor",
        "nombre_empresa": None,
        "giro_empresa": None,
        "lugar_requerimiento": "Ciudad de México",
        "correo": "luis@mail.com",
        "telefono": "555"
    }

    run_conversation_test("Flujo 16: Soldadora (Omite fuel)", chatbot, flujo_16, esperado_16)

    # ------------------------------------------------------------------------
    # Flujo 17: Cambio de tipo de maquinaria (plataforma → soldadora)
    # ------------------------------------------------------------------------
    flujo_17 = [
        "hola, soy Daniel Maldonado y quiero una plataforma",
        "la quiero de tijera",
        "no, prefiero que me coticemos una soldadora",
        "200 amperes",
        "cotizame la primera",
        "me dedico a la venta de maquinaria, mi correo es dan@gmail.com y estamos en Guanajuato",
        "ya mandé la constancia"
    ]

    esperado_17 = {
        "nombre": "Daniel Maldonado",
        "apellido": "Maldonado",
        "tipo_maquinaria": "soldadora",
        "detalles_maquinaria": {
            "amperaje_amps_max": 200
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Shindaiwa EGW185MS",
        "tipo_cliente": "distribuidor",
        "lugar_requerimiento": "Guanajuato",
        "correo": "dan@gmail.com",
        "constancia_fiscal_entregada": True
    }

    run_conversation_test("Flujo 17: Cambio de tipo de maquinaria", chatbot, flujo_17, esperado_17)

    # ------------------------------------------------------------------------
    # Flujo 18: Generador Portátil < 5 kW → Ofrecer modelo de 5 kW (GV-5500s)
    # ------------------------------------------------------------------------
    flujo_18 = [
        "Hola, soy Carlos Ruiz y necesito un generador",
        "3 kw",
        "quiero esa opción",
        "cliente_final",
        "trabajo en ElectroServ, nos dedicamos al mantenimiento, Monterrey, correo carlos@electroserv.com tel 8181234567"
    ]

    esperado_18 = {
        "nombre": "Carlos Ruiz",
        "apellido": "Ruiz",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {
            "potencia_kw": 3
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Koshin GV-5500s",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "ElectroServ",
        "giro_empresa": "mantenimiento",
        "lugar_requerimiento": "Monterrey",
        "correo": "carlos@electroserv.com",
        "telefono": "8181234567"
    }

    run_conversation_test("Flujo 18: Generador Portátil", chatbot, flujo_18, esperado_18)

    # ------------------------------------------------------------------------
    # Flujo 20: Generador Portátil > 8 kW → Saltar a modelo de 25 kW (DGM250MK-D)
    # ------------------------------------------------------------------------
    flujo_20 = [
        "Hola, soy Pedro Méndez y necesito un generador",
        "10 kw",
        "quiero esa opción",
        "no, es para uso de mi empresa",
        "trabajo en ConstruMex, giro construcción, Querétaro, correo pedro@construmex.com tel 4421234567"
    ]

    esperado_20 = {
        "nombre": "Pedro Méndez",
        "apellido": "Méndez",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {
            "potencia_kw": 10
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Shindaiwa DGM250MK-D",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "ConstruMex",
        "giro_empresa": "construcción",
        "lugar_requerimiento": "Querétaro",
        "correo": "pedro@construmex.com",
        "telefono": "4421234567"
    }

    run_conversation_test("Flujo 20: Generador Portátil", chatbot, flujo_20, esperado_20)

    # ------------------------------------------------------------------------
    # Flujo 21: Compresor Portátil ≤ 185 CFM → SOLO AIRMAN PDS185S-6C2
    # ------------------------------------------------------------------------
    flujo_21 = [
        "Hola, soy Roberto Díaz y necesito un compresor",
        "portátil",
        "150 cfm",
        "quiero esa opción",
        "cliente_final",
        "trabajo en AireTech, giro industrial, Monterrey, correo roberto@airetech.com tel 8187654321"
    ]

    esperado_21 = {
        "nombre": "Roberto Díaz",
        "apellido": "Díaz",
        "tipo_maquinaria": "compresor",
        "detalles_maquinaria": {
            "tipo_compresor": "portátil",
            "caudal_cfm_max": 150
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "AIRMAN PDS185S-6C2",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "AireTech",
        "giro_empresa": "industrial",
        "lugar_requerimiento": "Monterrey",
        "correo": "roberto@airetech.com",
        "telefono": "8187654321"
    }

    run_conversation_test("Flujo 21: Compresor Portátil", chatbot, flujo_21, esperado_21)

    # ------------------------------------------------------------------------
    # Flujo 22: Compresor Portátil > 185 CFM y ≤ 375 CFM → SOLO AIRMAN PDSF375S-DP
    # ------------------------------------------------------------------------
    flujo_22 = [
        "Hola, soy Laura Vega y necesito un compresor",
        "portátil",
        "300 cfm",
        "quiero esa opción",
        "cliente_final",
        "trabajo en CompresoresMX, giro minería, Chihuahua, correo laura@compresores.mx tel 6141234567"
    ]

    esperado_22 = {
        "nombre": "Laura Vega",
        "apellido": "Vega",
        "tipo_maquinaria": "compresor",
        "detalles_maquinaria": {
            "tipo_compresor": "portátil",
            "caudal_cfm_max": 300
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "AIRMAN PDSF375S-DP",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "CompresoresMX",
        "giro_empresa": "minería",
        "lugar_requerimiento": "Chihuahua",
        "correo": "laura@compresores.mx",
        "telefono": "6141234567"
    }

    run_conversation_test("Flujo 22: Compresor Portátil", chatbot, flujo_22, esperado_22)

    # ------------------------------------------------------------------------
    # Flujo 23: Compresor Portátil > 375 CFM → Recomendaciones normales
    # ------------------------------------------------------------------------
    flujo_23 = [
        "Hola, soy Miguel Sánchez y necesito un compresor",
        "portátil",
        "400 cfm",
        "quiero la primera",
        "cliente_final",
        "trabajo en IndustrialNorte, giro manufactura, Saltillo, correo miguel@industrialnorte.com tel 8441234567"
    ]

    esperado_23 = {
        "nombre": "Miguel Sánchez",
        "apellido": "Sánchez",
        "tipo_maquinaria": "compresor",
        "detalles_maquinaria": {
            "tipo_compresor": "portátil",
            "caudal_cfm_max": 400
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "AIRMAN PDS750S-4B1",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "IndustrialNorte",
        "giro_empresa": "manufactura",
        "lugar_requerimiento": "Saltillo",
        "correo": "miguel@industrialnorte.com",
        "telefono": "8441234567"
    }

    run_conversation_test("Flujo 23: Compresor Portátil", chatbot, flujo_23, esperado_23)

    # ------------------------------------------------------------------------
    # Flujo 25: Montacargas
    # ------------------------------------------------------------------------
    flujo_25 = [
        "Hola, soy Roberto García y necesito un montacargas",
        "2.5 toneladas",
        "si",
        "me dedico al mantenimiento",
        "trabajo en LogísticaMX, giro mantenimiento industrial, Monterrey, correo roberto@logisticamx.com tel 8112345678"
    ]

    esperado_25 = {
        "nombre": "Roberto García",
        "apellido": "García",
        "tipo_maquinaria": "montacargas",
        "detalles_maquinaria": {
            "capacidad_toneladas": 2.5
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Noblelift FE4P25Q",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "LogísticaMX",
        "giro_empresa": "mantenimiento industrial",
        "lugar_requerimiento": "Monterrey",
        "correo": "roberto@logisticamx.com",
        "telefono": "8112345678"
    }

    run_conversation_test("Flujo 25: Montacargas", chatbot, flujo_25, esperado_25)

    # ------------------------------------------------------------------------
    # Flujo 27: Torre de Luz - Selección tardía (usuario dice "sí" sin elegir)
    # ------------------------------------------------------------------------
    flujo_27 = [
        "Hola, soy Daniel Maldonado y quiero una torre de luz",
        "si",
        "la segunda",
        "me dedico al mantenimiento",
        "trabajo en ConstruNorte, giro mantenimiento industrial, Chihuahua, correo fernando@construnorte.com tel 6141234567"
    ]

    esperado_27 = {
        "nombre": "Daniel Maldonado",
        "apellido": "Maldonado",
        "tipo_maquinaria": "torre_iluminacion",
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Trime X-START",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "ConstruNorte",
        "giro_empresa": "mantenimiento industrial",
        "lugar_requerimiento": "Chihuahua",
        "correo": "fernando@construnorte.com",
        "telefono": "6141234567"
    }

    run_conversation_test("Flujo 27: Torre de Luz (selección tardía)", chatbot, flujo_27, esperado_27)

    # ------------------------------------------------------------------------
    # Flujo 28: Re-cotización post-completada (soldadora → generador)
    # ------------------------------------------------------------------------
    flujo_28 = [
        "Hola, soy Carlos Mendoza y quiero una soldadora de 300 amperes",
        "quiero la segunda opción",
        "no, es para uso propio",
        "trabajo en Edifica, giro mantenimiento, Saltillo, correo carlos@edifica.com tel 8441234567",
        "Muy bien, también quiero un generador",
        "7.2 kw",
        "si",
    ]

    esperado_28 = {
        "nombre": "Carlos Mendoza",
        "apellido": "Mendoza",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {
            "potencia_kw": 7.2
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Koshin GV-8000S",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "Edifica",
        "giro_empresa": "mantenimiento",
        "lugar_requerimiento": "Saltillo",
        "correo": "carlos@edifica.com",
        "telefono": "8441234567"
    }

    run_conversation_test("Flujo 28: Re-cotización post-completada", chatbot, flujo_28, esperado_28)

    # ------------------------------------------------------------------------
    # Flujo 30: Re-cotización explícita post-completada (generador 20kW → generador 35kW)
    # Verifica que el bot NO cicle repitiendo la cotización anterior
    # ------------------------------------------------------------------------
    flujo_30 = [
        "Hola, soy Daniel Maldonado y quiero un generador de 20 kw",
        "si",
        "no, es para uso propio",
        "trabajo en ConstruNorte, giro mantenimiento industrial, Chihuahua, correo fernando@construnorte.com tel 6141234567",
        "Oye, también cotízame un generador de 35 kw de potencia",
        "si, quiero esa",
    ]

    esperado_30 = {
        "nombre": "Daniel Maldonado",
        "apellido": "Maldonado",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {
            "potencia_kw": 35
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Shindaiwa DGM450MK-D",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "ConstruNorte",
        "giro_empresa": "mantenimiento industrial",
        "lugar_requerimiento": "Chihuahua",
        "correo": "fernando@construnorte.com",
        "telefono": "6141234567"
    }

    run_conversation_test("Flujo 30: Re-cotización explícita (sin ciclo)", chatbot, flujo_30, esperado_30)

    # ------------------------------------------------------------------------
    # Flujo 31: Distribuidor sin constancia con giro distribuidor (no re-pedir constancia)
    # Verifica que cuando un distribuidor dice que NO tiene la constancia
    # y luego proporciona un giro que confirma que es distribuidor (ej: renta de
    # maquinaria), el bot NO vuelve a pedir la constancia sino que responde
    # con el mensaje de asesor: "En un momento te contactará el asesor de la
    # zona para darle el precio preferencial."
    # ------------------------------------------------------------------------
    flujo_31 = [
        "Hola, soy Carlos Herrera y quiero un compresor",
        "portátil",
        "700 cfm",
        "okay, quiero la 750",
        "sí me dedico, mi correo es dan@gmail.com y estoy en Jalisco",
        "no la tengo",
        "renta de maquinaria",
    ]

    esperado_31 = {
        "nombre": "Carlos Herrera",
        "apellido": "Herrera",
        "tipo_maquinaria": "compresor",
        "detalles_maquinaria": {
            "tipo_compresor": "portátil",
            "caudal_cfm_max": 700
        },
        "maquina_seleccionada": "AIRMAN PDS750S-4B1",
        "quiere_cotizacion": True,
        "tipo_cliente": "distribuidor",
        "correo": "dan@gmail.com",
        "lugar_requerimiento": "Jalisco",
        "constancia_fiscal_entregada": "No tiene",
        "giro_empresa": "renta de maquinaria",
        "completed": True,
    }

    run_conversation_test("Flujo 31: Distribuidor sin constancia con giro distribuidor", chatbot, flujo_31, esperado_31)

    # ------------------------------------------------------------------------
    # Flujo 32: Distribuidor sin constancia con giro distribuidor (no re-pedir constancia)
    # Verifica que cuando un distribuidor dice que NO tiene la constancia
    # y luego proporciona un giro que confirma que es distribuidor (ej: renta de
    # maquinaria), el bot NO vuelve a pedir la constancia sino que responde
    # con el mensaje de asesor: "En un momento te contactará el asesor de la
    # zona para darle el precio preferencial."
    # ------------------------------------------------------------------------
    flujo_32 = [
        "Hola, tienen generadores?",
        "soy Carlos Herrera",
        "7",
        "si",
        "Cuánto cuesta la máquina que me recomendaste?",
        "Okay, me dedico a la construcción, 2 dadu@gmail.com, 3 Puebla",
        "Mi empresa se llama Constructora Top y el giro es construcción",
    ]

    esperado_32 = {
        "nombre": "Carlos Herrera",
        "apellido": "Herrera",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {
            "potencia_kw": 7
        },
        "maquina_seleccionada": "Koshin GV-8000S",
        "quiere_cotizacion": True,
        "tipo_cliente": "cliente_final",
        "correo": "dadu@gmail.com",
        "lugar_requerimiento": "Puebla",
        "giro_empresa": "construcción",
        "completed": True,
    }

    run_conversation_test("Flujo 32: Distribuidor sin constancia con giro distribuidor", chatbot, flujo_32, esperado_32)

    # ------------------------------------------------------------------------
    # Flujo 33: Cliente final cotiza un montacargas Noblelift CPCD30
    # Verifica el mapping de precio recién agregado para "Noblelift CPCD30"
    # ("Noblelift CPCD30" -> "CPCD30" en model_code_mapping.py).
    #
    # Hay dos montacargas de 3 toneladas (CPQYD30 a gasolina y CPCD30 a diésel),
    # por lo que el usuario debe elegir explícitamente el diésel para que
    # maquina_seleccionada quede en "Noblelift CPCD30".
    #
    # CÓMO VERIFICAR EL PRECIO (al ejecutar): en el archivo .txt de resultados,
    # la cotización final (y el PDF) deben incluir el precio del CPCD30
    # (~$20,371 USD). Antes de agregar el mapping, ese precio NO se resolvía.
    # El flujo también ejerce la regla de "no revelar precio antes de la
    # cotización": en el turno de "¿Cuánto cuesta?" el bot NO debe dar una cifra.
    # ------------------------------------------------------------------------
    flujo_33 = [
        "Hola, necesito un montacargas",
        "Soy Laura Mendoza",
        "3 toneladas",
        "Quiero el de diésel, el Noblelift CPCD30",
        "¿Cuánto cuesta?",
        "Es para uso propio, mi correo es laura.mendoza@constructora.com y estamos en Nuevo León",
        "Mi empresa se llama Edificaciones del Norte y nos dedicamos a la construcción",
    ]

    esperado_33 = {
        "nombre": "Laura Mendoza",
        "apellido": "Mendoza",
        "tipo_maquinaria": "montacargas",
        "detalles_maquinaria": {
            "capacidad_toneladas": 3
        },
        "maquina_seleccionada": "Noblelift CPCD30",
        "quiere_cotizacion": True,
        "tipo_cliente": "cliente_final",
        "correo": "laura.mendoza@constructora.com",
        "lugar_requerimiento": "Nuevo León",
        "giro_empresa": "construcción",
        "completed": True,
    }

    run_conversation_test("Flujo 33: Cliente final cotiza montacargas Noblelift CPCD30", chatbot, flujo_33, esperado_33)

    # ------------------------------------------------------------------------
    # Flujo 34: Seguimiento tras handoff a asesor por máquina SIN precio
    # cliente_final selecciona un manipulador (LGMG H1840), que NO tiene precio.
    # Al completar, el bot deriva a un asesor (no cotiza ni manda PDF). Luego:
    #   - El lead pide "¿me mandas la cotización?": como no hay PDF que reenviar,
    #     el bot debe reiterar la derivación a asesor, NO decir "Te reenvío la cotización".
    #   - El lead hace una pregunta libre sobre la máquina: el bot debe responder
    #     con normalidad (sin ciclarse en el mensaje de cierre ni revelar precio).
    # Verificaciones automáticas: aparece "asesor"; NUNCA aparece "Te reenvío la
    # cotización", ni "Procederé a generar su cotización", ni "$".
    # (Revisar en el .txt que la última respuesta conteste la pregunta de altura.)
    # ------------------------------------------------------------------------
    flujo_34 = [
        "Hola, soy Fernando López y busco un manipulador telescópico",
        "4 toneladas",
        "si, quiero cotización",
        "uso propio",
        "trabajo en ConstruNorte, giro construcción, Chihuahua, correo fernando@construnorte.com tel 6141234567",
        "oye, ¿me mandas la cotización?",
        "y ¿qué altura máxima alcanza ese manipulador?",
    ]

    esperado_34 = {
        "nombre": "Fernando López",
        "apellido": "López",
        "tipo_maquinaria": "manipulador",
        "detalles_maquinaria": {
            "capacidad_toneladas": 4
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "LGMG H1840",
        "tipo_cliente": "cliente_final",
        "giro_empresa": "construcción",
        "lugar_requerimiento": "Chihuahua",
        "correo": "fernando@construnorte.com",
        "telefono": "6141234567",
        "completed": True,
    }

    run_conversation_test(
        "Flujo 34: Seguimiento tras handoff sin precio", chatbot, flujo_34, esperado_34,
        expected_substrings=["asesor"],
        forbidden_substrings=["Te reenvío la cotización", "Procederé a generar su cotización", "$"]
    )

    # ------------------------------------------------------------------------
    # Flujo 35: Re-envío del PDF de cotización cuando SÍ hay precio
    # cliente_final cotiza un generador de 7 kW (→ Koshin GV-8000S, que SÍ tiene
    # precio). Al completar, se genera y "envía" la cotización (callback stub).
    # Luego el lead pide reenviarla: como el PDF sí se envió, el bot debe responder
    # "¡Claro! Te reenvío la cotización." (rama pdf_sent=True).
    # Usa simulate_pdf_send=True para instalar el callback stub (sin esto, en modo
    # prueba no hay callback y _try_send_pdf_quotation siempre devolvería False).
    # ------------------------------------------------------------------------
    flujo_35 = [
        "Hola, soy Ana Torres y necesito un generador",
        "7 kw",
        "quiero esa opción",
        "cliente_final",
        "trabajo en MaquiNorte, giro industrial, Guadalajara, correo ana@maquinorte.com tel 3312345678",
        "¿me reenvías la cotización por favor?",
    ]

    esperado_35 = {
        "nombre": "Ana Torres",
        "apellido": "Torres",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {
            "potencia_kw": 7
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Koshin GV-8000S",
        "tipo_cliente": "cliente_final",
        "giro_empresa": "industrial",
        "lugar_requerimiento": "Guadalajara",
        "correo": "ana@maquinorte.com",
        "telefono": "3312345678",
        "completed": True,
    }

    run_conversation_test(
        "Flujo 35: Re-envío de PDF con precio", chatbot, flujo_35, esperado_35,
        expected_substrings=["Te reenvío la cotización", "$"],
        simulate_pdf_send=True
    )

    # ------------------------------------------------------------------------
    # Flujo 36: Lead insistente con el precio (anti-fuga, regla 8)
    # El lead se niega a dar sus datos hasta que le digan el precio. El bot NO debe
    # ceder: no revela ninguna cifra ("$") y la conversación NO se completa (faltan
    # los datos de empresa). Verifica que el bot difiere el precio a la cotización.
    # ------------------------------------------------------------------------
    flujo_36 = [
        "Hola, soy Mario Vega y necesito un generador",
        "7 kw",
        "quiero esa opción",
        "No te voy a dar mis datos hasta que me digas el precio exacto de esa máquina",
    ]

    esperado_36 = {
        "nombre": "Mario Vega",
        "apellido": "Vega",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {
            "potencia_kw": 7
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Koshin GV-8000S",
        "tipo_cliente": None,
        "completed": False,
    }

    run_conversation_test(
        "Flujo 36: Lead insistente con el precio (anti-fuga)", chatbot, flujo_36, esperado_36,
        forbidden_substrings=["$"]
    )

    # ------------------------------------------------------------------------
    # Flujo 37: Cambio de detalle DESPUÉS de recomendar (re-recomendar, no completar)
    # Reproduce un bug real: tras completar una primera cotización (generador) y
    # arrancar una segunda (soldadora 300A → 2 opciones), el usuario CAMBIA el
    # amperaje a 185A. El bot NO debe completar con una selección obsoleta/nula;
    # debe recalcular y re-presentar la opción correcta para 185A (EGW185MS) y
    # dejar que el usuario la elija.
    # Verificación: la respuesta vuelve a recomendar "EGW185MS"; al final la
    # máquina seleccionada es la Shindaiwa EGW185MS y la conversación se completa.
    # ------------------------------------------------------------------------
    flujo_37 = [
        "Hola, soy Daniel Maldonado y quiero un generador de 7 kw",
        "si",
        "es para uso propio",
        "trabajo en Constructora Top, giro construcción, Puebla, correo dadu@gmail.com tel 5551234567",
        "También quiero una soldadora",
        "300 amperios",
        "sabes qué, mejor que sea de 185 amperios",
        "si, esa quiero",
    ]

    esperado_37 = {
        "nombre": "Daniel Maldonado",
        "apellido": "Maldonado",
        "tipo_maquinaria": "soldadora",
        "detalles_maquinaria": {
            "amperaje_amps_max": 185
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Shindaiwa EGW185MS",
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "Constructora Top",
        "giro_empresa": "construcción",
        "lugar_requerimiento": "Puebla",
        "correo": "dadu@gmail.com",
        "telefono": "5551234567",
        "completed": True,
    }

    run_conversation_test(
        "Flujo 37: Cambio de detalle tras recomendar (re-recomendar)", chatbot, flujo_37, esperado_37,
        expected_substrings=["EGW185MS"],
        expected_first_response_substrings=["Alphi"]
    )

    # ------------------------------------------------------------------------
    # Flujo 38: "¿Qué máquinas manejan?" — el bot NO debe inventar tipos
    # Verifica que al preguntar por los tipos de maquinaria, el bot se apegue a la
    # lista real del inventario y NO alucine tipos inexistentes (ej: taladros,
    # retroexcavadoras) ni use "entre otros".
    # ------------------------------------------------------------------------
    flujo_38 = [
        "Hola, soy Daniel Maldonado",
        "¿qué tipos de máquinas manejan?",
    ]

    esperado_38 = {
        "nombre": "Daniel Maldonado",
        "apellido": "Maldonado",
    }

    run_conversation_test(
        "Flujo 38: Tipos de maquinaria (sin inventar)", chatbot, flujo_38, esperado_38,
        expected_substrings=["generadores"],
        forbidden_substrings=["taladro", "retroexcavadora", "excavadora", "entre otros"]
    )

    # ------------------------------------------------------------------------
    # Flujo 39: Petición POR PRECIO ("la más barata") — no rankear ni revelar precio
    # El usuario pide "la más barata" antes de dar el tipo. El bot NO debe revelar
    # ni inventar un precio ("$"), ni presentar una máquina como la más barata;
    # debe diferir el precio a la cotización y seguir pidiendo el tipo.
    # ------------------------------------------------------------------------
    flujo_39 = [
        "Hola, soy Augusto Ramponi y quiero una plataforma de 6 metros",
        "la más barata que tengan",
    ]

    esperado_39 = {
        "nombre": "Augusto Ramponi",
        "apellido": "Ramponi",
        "tipo_maquinaria": "plataforma",
        "completed": False,
    }

    run_conversation_test(
        "Flujo 39: Petición por precio (la más barata)", chatbot, flujo_39, esperado_39,
        forbidden_substrings=["$"]
    )

    # ------------------------------------------------------------------------
    # Flujo 40: Cambio de tipo de plataforma DESPUÉS de recomendar (re-recomendar)
    # Tras recomendar plataformas de tijera, el usuario cambia a unipersonal. El bot
    # debe invalidar las opciones de tijera y re-recomendar una unipersonal
    # (LGMG MP0607SE), no quedarse con las opciones obsoletas.
    # ------------------------------------------------------------------------
    flujo_40 = [
        "Hola, soy Laura Fuentes y quiero una plataforma",
        "de tijera",
        "6 metros",
        "mejor unipersonal",
    ]

    esperado_40 = {
        "nombre": "Laura Fuentes",
        "apellido": "Fuentes",
        "tipo_maquinaria": "plataforma",
        "detalles_maquinaria": {
            "tipo_plataforma": "unipersonal",
            "altura_trabajo_m": 6
        },
    }

    run_conversation_test(
        "Flujo 40: Cambio de tipo de plataforma tras recomendar", chatbot, flujo_40, esperado_40,
        expected_substrings=["MP0607SE"]
    )

    # ------------------------------------------------------------------------
    # Flujo 41: Altura dada en el primer mensaje (no re-preguntar la altura)
    # "plataforma de 6 metros" debe quedar en altura_trabajo_m (NO en
    # altura_plataforma_m). Al dar el tipo, el bot debe recomendar de inmediato,
    # sin volver a preguntar la altura. Verifica la normalización de detalles.
    # ------------------------------------------------------------------------
    flujo_41 = [
        "quiero una plataforma de 6 metros",
        "soy Augusto Diaz",
        "unipersonal",
    ]

    esperado_41 = {
        "nombre": "Augusto Diaz",
        "apellido": "Diaz",
        "tipo_maquinaria": "plataforma",
        "detalles_maquinaria": {
            "tipo_plataforma": "unipersonal",
            "altura_trabajo_m": 6
        },
    }

    run_conversation_test(
        "Flujo 41: Altura en el primer mensaje (sin re-preguntar)", chatbot, flujo_41, esperado_41,
        expected_substrings=["MP0607SE"]
    )

    # ------------------------------------------------------------------------
    # Flujo 42: Reproducción exacta de una conversación real
    # El lead nunca proporciona el giro de su empresa. La dirección y el correo
    # no deben terminar en giro_empresa ni permitir que el flujo se complete.
    # ------------------------------------------------------------------------
    flujo_42 = [
        "me gustaria cotizar Martillo rompedor Toku TPB-90",
        "Me presento Francisco Altamirano de Grupo Impulsor Pajeme",
        "Toku TPB-90",
        "no me dedico a la venta o renta, solo requiero cotizacion para ese equipo, para que se pueda adquirir para uso de trabajo constructivo",
        "faltamirano@pajeme.mx\nRío Cuautitlán 163, San Francisco Tepojaco, 54745 Cuautitlán Izcalli, Méx",
    ]

    esperado_42 = {
        "nombre": "Francisco Altamirano",
        "tipo_maquinaria": "rompedor",
        "maquina_seleccionada": "Toku TPB-90",
        "quiere_cotizacion": True,
        "tipo_cliente": "cliente_final",
        "nombre_empresa": "Grupo Impulsor Pajeme",
        "correo": "faltamirano@pajeme.mx",
        "giro_empresa": None,
        "completed": False,
    }

    run_conversation_test(
        "Flujo 42: Conversación real con dirección multilínea",
        chatbot,
        flujo_42,
        esperado_42,
        expected_first_response_substrings=["Alphi"],
    )

    # ------------------------------------------------------------------------
    # Flujo 43: Tramo final de conversación real sobre pila de montacargas
    # Parte del estado observado justo después de que el bot informó que no había
    # coincidencias y confirmó el handoff. Así la prueba del ciclo no depende de
    # que el LLM vuelva a extraer igual todos los mensajes previos.
    # ------------------------------------------------------------------------
    flujo_43 = [
        "hablar con un asesor",
        "Quiero hablar con un asesor",
    ]

    detalles_43 = {"capacidad_toneladas": 5}
    contexto_sin_coincidencias_43 = json.dumps(
        {
            "tipo_maquinaria": "montacargas",
            "detalles_maquinaria": detalles_43,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    estado_inicial_43 = {
        "nombre": "Andres Robles",
        "apellido": "Robles",
        "tipo_ayuda": "maquinaria",
        "tipo_maquinaria": "montacargas",
        "detalles_maquinaria": detalles_43,
        "quiere_cotizacion": True,
        "maquinas_recomendadas": [],
        "sin_coincidencias_contexto": contexto_sin_coincidencias_43,
        "derivacion_asesor_confirmada": True,
        "recordatorios_derivacion_asesor": 0,
    }

    esperado_43 = {
        "nombre": "Andres Robles",
        "tipo_maquinaria": "montacargas",
        "quiere_cotizacion": True,
        "completed": False,
    }

    aviso_sin_inventario = "No manejamos una máquina en el inventario con esas características"
    run_conversation_test(
        "Flujo 43: Solicitud repetida de asesor sin inventario",
        chatbot,
        flujo_43,
        esperado_43,
        expected_substrings=["solicitud ya quedó registrada", "No necesitas volver a solicitarlo"],
        expected_maximum_occurrences={aviso_sin_inventario: 0},
        initial_state=estado_inicial_43,
    )

def test_manually(chatbot: IntelligentLeadQualificationChatbot):
    try:
        print("🔄 Inicializando chatbot con slot-filling inteligente...")
        print("✅ ¡Chatbot iniciado correctamente!")
        print("📝 Escriba 'salir' para terminar.")
        print("💬 ¡Usted inicia la conversación! Escriba su mensaje:\n")

        # Una sola instancia del guardrails
        guardrails = ContentSafetyGuardrails()
        
        # Loop de conversación
        while True:
            try:
                user_input = input("\n👤 Usuario: ").strip()
                
                if user_input.lower() in ['salir', 'exit', 'quit']:
                    print("👋 ¡Gracias por usar el sistema de calificación de leads!")
                    break

                if user_input.lower() == "status":
                    print(chatbot.get_status_message())
                    continue

                if user_input:
                    timestamp = _get_timestamp()
                    print(f"[{timestamp}] 👤 Usuario: {user_input}")
                    
                    safety_result = guardrails.check_message_safety(user_input)
                    if safety_result:
                        timestamp = _get_timestamp()
                        print(f"[{timestamp}] ❌ Bot: {safety_result['message']}")
                        continue
                    
                    response = chatbot.send_message(user_input)
                    timestamp = _get_timestamp()
                    print(f"[{timestamp}] 🤖 Bot: {response}")
                    
                    # Mostrar resumen si la conversación está completa
                    if chatbot.state["completed"]:
                        print("\n" + "="*60)
                        print("📊 RESUMEN DEL LEAD CALIFICADO:")
                        print("="*60)
                        print(chatbot.get_status_message())
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

# ============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ejecuta los flujos de prueba del chatbot.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--tests",
        type=parse_test_selection,
        metavar="SELECCIÓN",
        help='Flujos a ejecutar, por ejemplo: "5-15,20,22" o "4,7,14".',
    )
    mode.add_argument(
        "--manual",
        action="store_true",
        help="Inicia una conversación interactiva en lugar de los flujos automáticos.",
    )
    args = parser.parse_args()

    chatbot_instance = setup_chatbot()
    if args.manual:
        test_manually(chatbot_instance)
    else:
        _selected_test_numbers = args.tests
        define_test_flows(chatbot_instance)

        missing = (_selected_test_numbers or set()) - _defined_test_numbers
        if missing:
            print(f"⚠️ Flujos no definidos: {', '.join(map(str, sorted(missing)))}")
        if not _executed_test_numbers:
            parser.error("La selección no contiene ningún flujo definido.")

        print(f"Flujos ejecutados: {', '.join(map(str, sorted(_executed_test_numbers)))}")
        if _failed_test_numbers:
            print(f"Flujos fallidos: {', '.join(map(str, sorted(_failed_test_numbers)))}")
            raise SystemExit(1)
        print("\n🎉 Todas las pruebas seleccionadas han finalizado correctamente.")