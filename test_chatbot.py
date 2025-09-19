import os
import json
from typing import List, Dict, Any
import re
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

# Importa las clases necesarias de tu archivo de chatbot
from ai_langchain import IntelligentLeadQualificationChatbot, AzureOpenAIConfig, MaquinariaType

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

    # Configura las credenciales de Azure OpenAI desde las variables de entorno
    azure_config = AzureOpenAIConfig(
        endpoint=os.getenv("FOUNDRY_ENDPOINT"),
        api_key=os.getenv("FOUNDRY_API_KEY"),
        deployment_name="gpt-4.1-mini", # O el nombre de tu deployment
        api_version="2024-12-01-preview",
        model_name="gpt-4.1-mini"
    )
    
    chatbot = IntelligentLeadQualificationChatbot(azure_config)
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
        timestamp = _get_timestamp()
        output_lines.append(f"[{timestamp}] 👤 Usuario: {user_message}")

        safety_result = guardrails.check_message_safety(user_message)
        if safety_result:
            timestamp = _get_timestamp()
            output_lines.append(f"[{timestamp}] ❌ Bot: {safety_result['message']}")
            continue
        
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
        if isinstance(expected_value, MaquinariaType):
            if extracted_value != expected_value:
                has_errors = True
                output_lines.append(f"❌ ERROR en '{key}':")
                output_lines.append(f"   -> Esperado: {expected_value}")
                output_lines.append(f"   -> Extraído: {extracted_value}")
        elif isinstance(expected_value, dict):
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
        "La empresa se llama 'Construcciones del Sol' y nos dedicamos a la construcción de carreteras.",
        "La necesitamos en Chiapas.",
        "Es para uso en nuestra empresa.",
        "La página web es constresol.com",
        "mi correo es ana.gomez@constresol.com",
        "mi teléfono es 55 1234 5678"
    ]
    
    esperado_1 = {
        "nombre": "Ana Gómez",
        "apellido": "Gómez",
        "tipo_maquinaria": MaquinariaType.TORRE_ILUMINACION,
        "detalles_maquinaria": {"es_led": True},
        "sitio_web": "constresol.com",
        "uso_empresa_o_venta": "uso empresa",
        "nombre_empresa": "Construcciones del Sol",
        "giro_empresa": "construcción de carreteras",
        "correo": "ana.gomez@constresol.com",
        "telefono": "55 1234 5678"
    }
    
    # run_conversation_test("Flujo 1: Usuario Directo", chatbot, flujo_1, esperado_1)
    
    # ------------------------------------------------------------------------
    # Flujo 2: Usuario que da Múltiples Datos
    # Este usuario proporciona varios datos en una sola respuesta.
    # ------------------------------------------------------------------------
    flujo_2 = [
        "Qué tal, soy Roberto, de la empresa 'Maquinaria Pesada S.A.' y mi correo es roberto@maqpesada.mx. Necesito una plataforma de elevación.",
        "mi apellido es Marquez",
        "la necesito de 10 metros",
        "voy a elevar personal de construccion",
        "es para exterior",
        "nos dedicamos a la renta de maquinaria",
        "En Jalisco.",
        "Es para venderlo a un cliente.",
        "nuestro sitio web es maquinariapesada.mx y mi correo es roberto@maqpesada.mx",
        "mi tel es 81 8765 4321"
    ]
    
    esperado_2 = {
        "nombre": "Roberto Marquez",
        "apellido": "Marquez",
        "tipo_maquinaria": MaquinariaType.PLATAFORMA,
        "detalles_maquinaria": {
            "altura_trabajo": "10 metros",
            "actividad": "elevar personal de construccion",
            "ubicacion": "exterior"
        },
        "lugar_requerimiento": "Jalisco",
        "sitio_web": "maquinariapesada.mx",
        "uso_empresa_o_venta": "venta",
        "nombre_empresa": "Maquinaria Pesada S.A.",
        "giro_empresa": "renta de maquinaria",
        "correo": "roberto@maqpesada.mx",
        "telefono": "81 8765 4321"
    }
    
    # run_conversation_test("Flujo 2: Usuario con Múltiples Datos", chatbot, flujo_2, esperado_2)

    # ------------------------------------------------------------------------
    # Flujo 3: Usuario que Pregunta y se Desvía
    # Este usuario hace preguntas al bot, probando los manejadores de inventario y requerimientos.
    # ------------------------------------------------------------------------
    flujo_3 = [
        "Hola, ¿tienen generadores en existencia?",
        "Ok, necesito uno para mineria. Soy Lucía Martinez.",
        "Necesito unos 50 kva.",
        "Mineria H&H",
        "Nos dedicamos a la mineria.",
        "En qué estados pueden hacer entrega?",
        "Okay, en Aguascalientes.",
        "Para venta.",
        "Entiendo. La web es hh.com",
        "Mi correo es lucia.h@hh.com y mi teléfono es 33 9876 5432"
    ]
    
    esperado_3 = {
        "nombre": "Lucía Martinez",
        "tipo_maquinaria": MaquinariaType.GENERADORES,
        "detalles_maquinaria": {
            "actividad": "mineria",
            "capacidad": "50 kva"
        },
        "nombre_empresa": "Mineria H&H",
        "sitio_web": "hh.com",
        "giro_empresa": "Mineria",
        "uso_empresa_o_venta": "venta",
        "lugar_requerimiento": "Aguascalientes",
        "correo": "lucia.h@hh.com",
        "telefono": "33 9876 5432"
    }
    
    # run_conversation_test("Flujo 3: Usuario que Pregunta", chatbot, flujo_3, esperado_3)

    # ------------------------------------------------------------------------
    # Flujo 4: Usuario que dice que no tiene varios campos
    # ------------------------------------------------------------------------
    flujo_4 = [
        "Hola, soy Daniel Marquez y quiero comprar una torre de iluminación.",
        "Que sea de LED",
        "Trabajo para MachinesCorp",
        "No conozco el giro de la empresa.",
        "No estoy seguro.",
        "Es para venderlo a un cliente.",
        "No tenemos pagina web.",
        "mi correo es daniel.marquez@machinescorp.com y mi teléfono es 33 9876 5432"
    ]

    esperado_4 = {
        "nombre": "Daniel Marquez",
        "apellido": "Marquez",
        "tipo_maquinaria": MaquinariaType.TORRE_ILUMINACION,
        "detalles_maquinaria": {"es_led": True},
        "sitio_web": "No tiene",
        "uso_empresa_o_venta": "venta",
        "nombre_empresa": "MachinesCorp",
        "giro_empresa": "No especificado",
        "lugar_requerimiento": "No especificado",
        "correo": "daniel.marquez@machinescorp.com",
        "telefono": "33 9876 5432"
    }

    run_conversation_test("Flujo 4: Usuario que dice que no tiene pagina web", chatbot, flujo_4, esperado_4)

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
    # test_manually(chatbot_instance)
    print("\n🎉 Todas las pruebas han finalizado.")