import os
import json
from typing import List, Dict, Any
import re
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

# Importa las clases necesarias de tu archivo de chatbot
from ai_langchain import IntelligentLeadQualificationChatbot, AzureOpenAIConfig, MaquinariaType

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
    
    # Simula la conversación
    for i, user_message in enumerate(conversation_flow):
        output_lines.append(f"👤 Usuario: {user_message}")
        
        bot_response = chatbot.send_message(user_message)
        output_lines.append(f"🤖 Bot: {bot_response}\n")

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
        "Busco una torre de iluminación.",
        "Sí, la prefiero de LED por favor.",
        "Es para uso en nuestra empresa.",
        "La empresa se llama 'Construcciones del Sol'.",
        "La página web es constresol.com",
        "Nos dedicamos a la construcción de carreteras.",
        "Claro, mi nombre completo es Ana María Gómez Pérez.",
        "mi correo es ana.gomez@constresol.com",
        "55 1234 5678"
    ]
    
    esperado_1 = {
        "nombre": "Ana María Gómez Pérez",
        "tipo_maquinaria": MaquinariaType.TORRE_ILUMINACION,
        "detalles_maquinaria": {"es_led": True},
        "sitio_web": "constresol.com",
        "uso_empresa_o_venta": "uso empresa",
        "nombre_completo": "Ana María Gómez Pérez",
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
        "Qué tal, soy Roberto, de la empresa 'Maquinaria Pesada S.A.' y mi correo es roberto@maqpesada.mx. Necesito un compresor.",
        "Lo necesito de 185 pcm.",
        "Es para conectar dos pistolas de clavos y un taladro neumático.",
        "En Chiapas.",
        "Es para venderlo a un cliente.",
        "nuestro sitio web es maquinariapesada.mx",
        "venta de maquinaria",
        "Roberto Carlos Paredes y mi tel es 81 8765 4321"
    ]
    
    esperado_2 = {
        "nombre": "Roberto",
        "tipo_maquinaria": MaquinariaType.COMPRESOR,
        "detalles_maquinaria": {
            "capacidad_volumen": "185 pcm",
            "herramientas_conectar": "dos pistolas de clavos y un taladro neumático"
        },
        "lugar_requerimiento": "Chiapas",
        "sitio_web": "maquinariapesada.mx",
        "uso_empresa_o_venta": "venta",
        "nombre_completo": "Roberto Carlos Paredes",
        "nombre_empresa": "Maquinaria Pesada S.A.",
        "giro_empresa": "venta de maquinaria",
        "correo": "roberto@maqpesada.mx",
        "telefono": "81 8765 4321"
    }
    
    run_conversation_test("Flujo 2: Usuario con Múltiples Datos", chatbot, flujo_2, esperado_2)

    # ------------------------------------------------------------------------
    # Flujo 3: Usuario que Pregunta y se Desvía
    # Este usuario hace preguntas al bot, probando los manejadores de inventario y requerimientos.
    # ------------------------------------------------------------------------
    flujo_3 = [
        "Hola, ¿tienen generadores en existencia?",
        "Ok, necesito uno para una construcción. Soy Lucía.",
        "Es para alimentar varias herramientas eléctricas.",
        "Necesito unos 50 kva.",
        "Para venta.",
        "Constructora H&H",
        "Entiendo. No, no tenemos.",
        "Construcción general",
        "Lucía Hernández Parra",
        "lucia.h@hh.com",
        "33 9876 5432"
    ]
    
    esperado_3 = {
        "nombre": "Lucía",
        "tipo_maquinaria": MaquinariaType.GENERADORES,
        "detalles_maquinaria": {
            "actividad": "alimentar varias herramientas eléctricas",
            "capacidad": "50 kva"
        },
        "sitio_web": "No tiene",
        "uso_empresa_o_venta": "venta",
        "nombre_completo": "Lucía Hernández Parra",
        "nombre_empresa": "Constructora H&H",
        "giro_empresa": "Construcción general",
        "correo": "lucia.h@hh.com",
        "telefono": "33 9876 5432"
    }
    
    # run_conversation_test("Flujo 3: Usuario que Pregunta", chatbot, flujo_3, esperado_3)

def test_manually(chatbot: IntelligentLeadQualificationChatbot):
    try:
        print("🔄 Inicializando chatbot con slot-filling inteligente...")
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

                if user_input.lower() == "status":
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

# ============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# ============================================================================

if __name__ == "__main__":
    chatbot_instance = setup_chatbot()
    # define_test_flows(chatbot_instance)
    test_manually(chatbot_instance)
    print("\n🎉 Todas las pruebas han finalizado.")