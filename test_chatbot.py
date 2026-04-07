import os
import json
from typing import List, Dict, Any
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
    expected_data: Dict[str, Any]
):
    """
    Ejecuta un flujo de conversación de prueba y compara los resultados.
    Guarda todo el output de la prueba en un archivo .txt y solo imprime
    en consola cuando inicia y cuando termina la prueba.
    """
    import os
    if os.environ.get("RUN_ONLY") and os.environ.get("RUN_ONLY") not in test_name:
        return
        
    # Solo informar inicio en consola
    print(f"INICIANDO PRUEBA: {test_name}")

    output_lines: List[str] = []
    output_lines.append("==================================================")
    output_lines.append(f"✨ Resultado de la prueba: {test_name}")
    output_lines.append("==================================================\n")
    output_lines.append(f"--- INICIANDO PRUEBA: {test_name} ---\n")
    
    # Reinicia el estado del chatbot para una prueba limpia
    chatbot.reset_conversation()

    # Una sola instancia del guardrails
    guardrails = ContentSafetyGuardrails()
    
    # Simula la conversación
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

    if not has_errors:
        output_lines.append("✅ ¡ÉXITO! Toda la información fue extraída correctamente.")
    else:
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
        "Sí, la prefiero de LED por favor.",
        "Sí, quiero la maquina 1",
        "Es para nuestra empresa",
        "Claro. La empresa se llama 'Construcciones del Sol' y nos dedicamos a la construcción de carreteras. Estamos ubicados en Puebla. Mi correo es ana.gomez@constresol.com y mi teléfono es 55 1234 5678."
    ]
    
    esperado_1 = {
        "nombre": "Ana Gómez",
        "apellido": "Gómez",
        "tipo_maquinaria": "torre_iluminacion",
        "detalles_maquinaria": {"tipo_reflector": "LED"},
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Shindaiwa SL433IDG-B/S1W",
        "uso_empresa_o_venta": "uso empresa",
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
        "La maquinaria es para venta.",
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
        "uso_empresa_o_venta": "venta",
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
        "El tipo de generador debe ser portátil",
        "La potencia debe ser de 7.2 kW",
        "En qué estados pueden hacer entrega?, quiero cotizarla",
        "Es para uso de la empresa.",
        "Construcciones del Norte, Nuevo León, dadu@gmail.com, 8112345678"
    ]
    
    esperado_3 = {
        "nombre": "Lucía Martinez",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {
            "actividad": "mineria",
            "tipo_generador": "portátil",
            "potencia_kw": 7.2
        },
        "quiere_cotizacion": True,
        "uso_empresa_o_venta": "uso empresa",
        "nombre_empresa": "Construcciones del Norte",
        "lugar_requerimiento": "Nuevo León",
        "correo": "dadu@gmail.com",
        "telefono": "8112345678"
    }
    
    run_conversation_test("Flujo 3: Usuario que Pregunta", chatbot, flujo_3, esperado_3)

    # ------------------------------------------------------------------------
    # Flujo 4: Usuario que dice que no tiene varios campos
    # ------------------------------------------------------------------------
    flujo_4 = [
        "Hola, soy Daniel Marquez y quiero comprar una torre de iluminación.",
        "Que sea de LED",
        "Quiero la maquina 1",
        "quiero comercializarla, es para venta",
        "te adjunto la constancia"
    ]

    esperado_4 = {
        "nombre": "Daniel Marquez",
        "apellido": "Marquez",
        "tipo_maquinaria": "torre_iluminacion",
        "detalles_maquinaria": {"tipo_reflector": "LED"},
        "quiere_cotizacion": True,
        "uso_empresa_o_venta": "venta",
        "constancia_fiscal_entregada": True
    }

    run_conversation_test("Flujo 4: Usuario que dice que no tiene varios campos", chatbot, flujo_4, esperado_4)

    # ------------------------------------------------------------------------
    # Flujo 5: Usuario que selecciona máquina específica
    # ------------------------------------------------------------------------
    flujo_5 = [
        "Hola, quiero una torre de luz",
        "Soy Juan Perez",
        "Si, LED",
        "quiero la 1",
        "es para uso propio",
        "trabajo en Constructora Norte, nos dedicamos a la construccion, en Monterrey. correo carlos@connorte.com y tel 81 1234 5678"
    ]

    esperado_5 = {
        "nombre": "Juan Perez",
        "apellido": "Perez",
        "tipo_maquinaria": "torre_iluminacion",
        "detalles_maquinaria": {"tipo_reflector": "LED"},
        "quiere_cotizacion": True,
        "uso_empresa_o_venta": "uso empresa",
        "nombre_empresa": "Constructora Norte",
        "giro_empresa": "construcción",
        "lugar_requerimiento": "Monterrey",
        "correo": "carlos@connorte.com",
        "telefono": "81 1234 5678"
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
        "estacionario",
        "20 kw",
        "si, cotizame el primero que es Shindaiwa DGM250MK-D",
        "es para uso de la empresa",
        "trabajo en Alfa Construcciones, nos dedicamos a la construccion, en Puebla. correo mi@mail.com y tel 529931340372"
    ]

    esperado_6 = {
        "nombre": "Daniel Maldonado",
        "apellido": "Maldonado",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {
            "tipo_generador": "estacionario",
            "potencia_kw": 20
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Shindaiwa DGM250MK-D",
        "uso_empresa_o_venta": "uso empresa",
        "nombre_empresa": "Alfa Construcciones",
        "giro_empresa": "construcción",
        "lugar_requerimiento": "Puebla",
        "correo": "mi@mail.com",
        "telefono": "529931340372"
    }

    run_conversation_test("Flujo 6: Selección de máquina con nombre específico", chatbot, flujo_6, esperado_6)

    # ------------------------------------------------------------------------
    # Flujo 7: Plataforma S1932EII – verificar que se muestre el precio
    # Este flujo prueba el ciclo completo: preguntas de plataforma, selección
    # de máquina, datos de empresa y verificación de que el precio aparezca
    # en la respuesta final.
    # ------------------------------------------------------------------------
    flujo_7 = [
        "Hola, soy Carlos Ramírez",
        "Necesito una plataforma de elevación",
        "de tijera",
        "la altura de trabajo es de 7 metros",
        "eléctrica",
        "Si, quiero cotizacion de la LGMG S1932EII",
        "uso empresa",
        "Trabajo en Constructora Norte, nos dedicamos a la construcción, estamos en Monterrey. Mi correo es carlos@connorte.com y mi teléfono es 81 1234 5678"
    ]

    esperado_7 = {
        "nombre": "Carlos Ramírez",
        "apellido": "Ramírez",
        "tipo_maquinaria": "plataforma",
        "quiere_cotizacion": True,
        "maquina_seleccionada": "LGMG S1932EII",
        "uso_empresa_o_venta": "uso empresa",
        "nombre_empresa": "Constructora Norte",
        "giro_empresa": "construcción",
        "lugar_requerimiento": "Monterrey",
        "correo": "carlos@connorte.com",
        "telefono": "81 1234 5678"
    }

    run_conversation_test("Flujo 7: Plataforma S1932EII con precio", chatbot, flujo_7, esperado_7)

    # ------------------------------------------------------------------------
    # Flujo 8: Selección de máquina con código parcial (sin marca)
    # Este flujo prueba que el bot muestre el precio incluso cuando el usuario
    # selecciona una máquina usando solo el código del modelo (ej: "DGM250MK-D")
    # sin el nombre completo de la marca (ej: "Shindaiwa DGM250MK-D").
    # Valida el fuzzy matching del pricing service.
    # ------------------------------------------------------------------------
    flujo_8 = [
        "Hola, soy María López",
        "Necesito un generador",
        "estacionario",
        "25 kw",
        "Me interesa la DGM250MK-D, quiero cotización por favor",
        "Es para uso de la empresa",
        "Trabajo en IndustrialMex, nos dedicamos a la manufactura y estamos en Querétaro, mi correo es maria@industrialmex.com y tel 442 111 2233"
    ]

    esperado_8 = {
        "nombre": "María López",
        "apellido": "López",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {
            "tipo_generador": "estacionario",
            "potencia_kw": 25
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "DGM250MK-D",
        "uso_empresa_o_venta": "uso empresa",
        "nombre_empresa": "IndustrialMex",
        "giro_empresa": "manufactura",
        "lugar_requerimiento": "Querétaro",
        "correo": "maria@industrialmex.com",
        "telefono": "442 111 2233"
    }

    run_conversation_test("Flujo 8: Selección de máquina con código parcial", chatbot, flujo_8, esperado_8)

    # ------------------------------------------------------------------------
    # Flujo 9: Torre de iluminación con nombre parcial (X-START → Trime X-START)
    # Replica el escenario de producción donde el usuario dice "Quiero la X-START"
    # y el bot debe resolver el nombre parcial al modelo completo "Trime X-START"
    # para poder obtener su precio ($14,949 USD).
    # ------------------------------------------------------------------------
    flujo_9 = [
        "hola",
        "Soy Daniel Maldonado",
        "quiero una torre de iluminacion",
        "Quiero que sea led",
        "Quiero la X-START",
        "Es para distribución/venta",
        "la constancia ya fue enviada en formato pdf"
    ]

    esperado_9 = {
        "nombre": "Daniel Maldonado",
        "apellido": "Maldonado",
        "tipo_maquinaria": "torre_iluminacion",
        "detalles_maquinaria": {"tipo_reflector": "LED"},
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Trime X-START",
        "uso_empresa_o_venta": "venta",
        "constancia_fiscal_entregada": True
    }

    run_conversation_test("Flujo 9: Torre iluminación con nombre parcial", chatbot, flujo_9, esperado_9)

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
        "eléctrica",
        "Me interesa la LGMG MP0607SE",
        "Es para nuestra empresa",
        "Trabajo en Mantenimiento X, nos dedicamos a mantenimiento industrial, estamos en CDMX, mi correo es laura@mx.com"
    ]

    esperado_10 = {
        "nombre": "Laura Mendoza",
        "apellido": "Mendoza",
        "tipo_maquinaria": "plataforma",
        "detalles_maquinaria": {
            "tipo_plataforma": "unipersonal",
            "altura_trabajo_m": 8,
            "tipo_alimentacion": "electrica"
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "LGMG MP0607SE",
        "uso_empresa_o_venta": "uso empresa",
        "nombre_empresa": "Mantenimiento X",
        "giro_empresa": "mantenimiento industrial",
        "lugar_requerimiento": "CDMX",
        "correo": "laura@mx.com"
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
        "eléctrica",
        "Me interesa la LGMG M2640JE",
        "uso empresa",
        "Empresa Silva Construcciones, construccion, Estado de Mexico, rs@silvacons.com"
    ]

    esperado_11 = {
        "nombre": "Ricardo Silva",
        "apellido": "Silva",
        "tipo_maquinaria": "plataforma",
        "detalles_maquinaria": {
            "tipo_plataforma": "mástil",
            "altura_trabajo_m": 10,
            "tipo_alimentacion": "electrica"
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "LGMG M2640JE",
        "uso_empresa_o_venta": "uso empresa",
        "nombre_empresa": "Empresa Silva Construcciones",
        "giro_empresa": "construccion",
        "lugar_requerimiento": "Estado de Mexico",
        "correo": "rs@silvacons.com"
    }

    run_conversation_test("Flujo 11: Plataforma Mástil", chatbot, flujo_11, esperado_11)

    # ------------------------------------------------------------------------
    # Flujo 12: Compresor
    # Este flujo prueba que el sistema solicite tipo_compresor y caudal_cfm_max
    # ------------------------------------------------------------------------
    flujo_12 = [
        "Hola, me llamo Luis Torres",
        "Busco un compresor",
        "portátil",
        "necesito 400 cfm",
        "Me interesa esa opción",
        "para uso de la empresa",
        "trabajo en MachinesCorp, nos dedicamos a la construccion, y Ciudad de Mexico"
        "correo carlos@connorte.com y tel 81 1234 5678"
    ]

    esperado_12 = {
        "nombre": "Luis Torres",
        "apellido": "Torres",
        "tipo_maquinaria": "compresor",
        "detalles_maquinaria": {
            "tipo_compresor": "portátil",
            "caudal_cfm_max": 400
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "AIRMAN PDS750S-4B1",
        "uso_empresa_o_venta": "uso empresa",
        "nombre_empresa": "MachinesCorp",   
        "giro_empresa": "construccion",
        "lugar_requerimiento": "Ciudad de Mexico",
        "correo": "carlos@connorte.com",
        "telefono": "81 1234 5678"
    }

    run_conversation_test("Flujo 12: Compresor", chatbot, flujo_12, esperado_12)

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
        "trabajo en Alfa Construcciones, nos dedicamos a la construccion, en Puebla. correo mi@mail.com y tel 529931340372"
    ]

    esperado_13 = {
        "nombre": "Daniel Maldonado",
        "apellido": "Maldonado",
        "tipo_maquinaria": "rompedor",
        "detalles_maquinaria": {},
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Toku TPB-60",
        "uso_empresa_o_venta": "uso empresa",
        "nombre_empresa": "Alfa Construcciones",
        "giro_empresa": "construccion",
        "lugar_requerimiento": "Puebla",
        "correo": "mi@mail.com",
        "telefono": "529931340372"
    }

    run_conversation_test("Flujo 13: Selección de máquina implícita", chatbot, flujo_13, esperado_13)

    # ------------------------------------------------------------------------
    # Flujo 14: Atributos desde el inicio (Ejemplo de soldadora)
    # ------------------------------------------------------------------------
    flujo_14 = [
        "me cotizas una soldadora shindaiwa de 185 amperes",
        "mi correo es j.perez@gmail.com y me llamo Juan Perez",
        "la necesito de diesel",
        "quiero Shindaiwa DGW340DM",
        "uso propio",
        "trabajo en MachinesCorp, nos dedicamos a la construccion, y Ciudad de Mexico"
    ]

    esperado_14 = {
        "nombre": "Juan Perez",
        "apellido": "Perez",
        "tipo_maquinaria": "soldadora",
        "detalles_maquinaria": {
            "amperaje_amps_max": 185,
            "tipo_alimentacion": "diésel"
        },
        "quiere_cotizacion": True,
        "maquina_seleccionada": "Shindaiwa DGW340DM",
        "uso_empresa_o_venta": "uso empresa",
        "nombre_empresa": "MachinesCorp",
        "giro_empresa": "construcción",
        "lugar_requerimiento": "Ciudad de Mexico",
        "correo": "j.perez@gmail.com",
    }

    run_conversation_test("Flujo 14:  Atributos desde el inicio", chatbot, flujo_14, esperado_14)

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
                    estado = chatbot.get_lead_data_json()
                    print(f"🤖 Estado actual de la conversación:\n{estado}")
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

# ============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# ============================================================================

if __name__ == "__main__":
    chatbot_instance = setup_chatbot()
    define_test_flows(chatbot_instance)
    # test_manually(chatbot_instance)  # modo interactivo; descomentar solo para pruebas manuales
    print("\n🎉 Todas las pruebas han finalizado.")