"""
Tests para la detección de códigos/modelos de maquinaria en el mensaje del lead.

Caso real que originó esto (real_conversations_withLeads/3.json): el lead
respondió "PDSG900VR" a "¿Con quién tengo el gusto?" y el bot repitió la pregunta
en seco, sin dar señal de haber leído el código.

No requieren llamadas al LLM: la detección es determinista.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_langchain import (
    AzureOpenAIConfig,
    IntelligentLeadQualificationChatbot,
    IntelligentResponseGenerator,
)
from machine_reference import detect_machine_reference, looks_like_machine_code


# ============================================================================
# DETECCIÓN
# ============================================================================

@pytest.mark.parametrize("mensaje, categoria, en_inventario", [
    # El caso real: modelo AIRMAN que NO tenemos, pero la familia PDSG lo delata
    ("PDSG900VR", "compresor", False),
    # Modelos que sí están en inventario, escritos de distintas formas
    ("PDSG750VRS-4C5", "compresor", True),
    ("me interesa el AIRMAN PDS185S-6C2", "compresor", True),
    ("quiero la S4046E II", "plataforma", True),
    ("Koshin GV-5500s", "generador", True),
    ("necesito un DGW400DMK", "soldadora", True),
    ("TPB-90", "rompedor", True),
    ("CPCD30", "montacargas", True),
    ("H1840", "manipulador", True),
    # Sin dígitos, solo resoluble contra el inventario
    ("X-START", "torre_iluminacion", True),
    # Código incompleto, resuelto por prefijo único
    ("PDS185", "compresor", True),
])
def test_detecta_codigos_de_maquina(mensaje, categoria, en_inventario):
    ref = detect_machine_reference(mensaje)
    assert ref is not None, f"No se detectó el código en {mensaje!r}"
    assert ref.categoria == categoria
    assert ref.en_inventario is en_inventario


@pytest.mark.parametrize("mensaje", [
    # Saludos y datos personales del flujo normal
    "BUEN DÍA",
    "Daniel mald",
    "Gracias, Daniel",
    "Constructora H2O SA de CV",
    # Respuestas numéricas a las preguntas de detalle: NO son códigos
    "300A",
    "15 metros",
    "3 toneladas",
    "necesito 20 kw",
    "una plataforma de tijera",
    "1",
    # Datos de contacto
    "compras2024@empresa.com",
    "mi tel es 9931340372",
    "www.empresa2024.com",
    # RFC del flujo de Constancia de Situación Fiscal
    "MALD850101ABC",
    "mi rfc es ABC850101XY1",
    # Marca que no manejamos: no inventamos una categoría
    "CAT320D",
    "necesito una JCB540170",
])
def test_no_detecta_falsos_positivos(mensaje):
    assert detect_machine_reference(mensaje) is None, f"Falso positivo en {mensaje!r}"


def test_referencia_incluye_modelo_canonico():
    """Un código de inventario se resuelve al nombre completo con marca."""
    ref = detect_machine_reference("quiero cotizar la S4046E II")
    assert ref.modelo == "LGMG S4046E II"
    assert ref.confianza == "exacta"


def test_familia_no_inventa_modelo():
    """Si no tenemos ese modelo, modelo queda en None (no se adivina)."""
    ref = detect_machine_reference("PDSG900VR")
    assert ref.modelo is None
    assert ref.confianza == "familia"


@pytest.mark.parametrize("texto, esperado", [
    ("PDSG900VR", True),
    ("CAT320D", True),
    ("S4046E", True),
    ("Daniel", False),
    ("Daniel Maldonado", False),
    ("construcción", False),
    ("Grupo 3M", False),
    ("", False),
    (None, False),
])
def test_looks_like_machine_code(texto, esperado):
    assert looks_like_machine_code(texto) is esperado


# ============================================================================
# INSTRUCCIÓN DE RECONOCIMIENTO
# ============================================================================

def _build(ref, next_question, question_type):
    return IntelligentResponseGenerator._build_machine_reference_instruction(
        None, ref, next_question, question_type
    )


def test_instruccion_pide_reconocer_antes_de_repreguntar():
    """El caso de 3.json: hay código y la pregunta pendiente es el nombre."""
    instruccion = _build(detect_machine_reference("PDSG900VR"), "¿Con quién tengo el gusto?", "nombre")
    assert "Entiendo que te interesa esa máquina, pero primero" in instruccion
    assert "PDSG900VR" in instruccion
    assert "compresor" in instruccion
    # No debe afirmar que tenemos ese modelo exacto
    assert "no está en nuestro inventario" in instruccion


def test_instruccion_menciona_modelo_cuando_si_lo_manejamos():
    instruccion = _build(
        detect_machine_reference("me interesa la S4046E II"),
        "Necesito los siguientes datos de su empresa.",
        "datos_empresa",
    )
    assert "LGMG S4046E II" in instruccion
    assert "sí manejamos" in instruccion


@pytest.mark.parametrize("question_type", [
    "tipo_maquinaria",
    "detalles_maquinaria",
    "quiere_cotizacion",
    "seleccion_maquina",
])
def test_no_reconoce_cuando_el_codigo_es_la_respuesta(question_type):
    """
    Si la pregunta pendiente ya es sobre la máquina, el código ES la respuesta:
    decir "pero primero" ahí no tendría sentido.
    """
    ref = detect_machine_reference("PDSG900VR")
    assert _build(ref, "¿Qué tipo de maquinaria requiere?", question_type) == ""


def test_no_reconoce_sin_referencia_ni_sin_pregunta_pendiente():
    ref = detect_machine_reference("PDSG900VR")
    assert _build(None, "¿Con quién tengo el gusto?", "nombre") == ""
    assert _build(ref, None, "conversation_complete") == ""


# ============================================================================
# EFECTO EN EL ESTADO
# ============================================================================

@pytest.fixture
def chatbot():
    """Chatbot con credenciales dummy: estas pruebas no invocan al LLM."""
    config = AzureOpenAIConfig(
        endpoint="https://dummy.openai.azure.com/",
        api_key="dummy-key",
        deployment_name="dummy",
    )
    return IntelligentLeadQualificationChatbot(config)


def test_codigo_se_guarda_y_resuelve_tipo_maquinaria(chatbot):
    """El código no se pierde y evita preguntar algo que ya sabemos."""
    extracted = {}
    ref = chatbot._detect_and_merge_machine_reference("PDSG900VR", extracted)

    assert ref is not None
    assert chatbot.state["maquina_mencionada"] == "PDSG900VR"
    # Se infiere el tipo para no preguntar "¿qué tipo de maquinaria requiere?"
    assert extracted["tipo_maquinaria"] == "compresor"

    chatbot._update_state_with_extracted_info(extracted)
    assert chatbot.state["tipo_maquinaria"] == "compresor"
    # tipo_ayuda se deduce de tener tipo_maquinaria
    assert chatbot.state["tipo_ayuda"] == "maquinaria"


def test_no_sobrescribe_tipo_maquinaria_ya_conocido(chatbot):
    chatbot.state["tipo_maquinaria"] = "plataforma"
    extracted = {}
    chatbot._detect_and_merge_machine_reference("PDSG900VR", extracted)
    assert "tipo_maquinaria" not in extracted


def test_codigo_nunca_se_guarda_como_nombre(chatbot):
    """
    Guardia contra el peor caso: que el LLM tome el código como nombre del lead
    y quede contaminado el estado y el contacto de HubSpot.
    """
    chatbot._update_state_with_extracted_info({"nombre": "PDSG900VR"})
    assert chatbot.state["nombre"] is None

    chatbot._update_state_with_extracted_info({"nombre": "Daniel", "apellido": "Maldonado"})
    assert chatbot.state["nombre"] == "Daniel Maldonado"


def test_codigo_nunca_se_guarda_como_giro(chatbot):
    chatbot._update_state_with_extracted_info({"giro_empresa": "CPCD30"})
    assert chatbot.state["giro_empresa"] is None

    chatbot._update_state_with_extracted_info({"giro_empresa": "construcción"})
    assert chatbot.state["giro_empresa"] == "construcción"


def test_giro_inferido_por_contexto_ignora_codigos(chatbot):
    """
    El fallback que toma el mensaje completo como giro (cuando el bot preguntó por
    el giro y el LLM no extrajo nada) no debe tragarse un código de máquina.
    """
    chatbot.state["messages"] = [
        {"role": "assistant", "sender": "bot", "question_type": "datos_empresa",
         "content": "¿Cuál es el giro de tu empresa?"},
        {"role": "user", "sender": "lead", "question_type": "", "content": "PDSG900VR"},
    ]
    chatbot._update_state_with_extracted_info({})
    assert chatbot.state["giro_empresa"] is None
