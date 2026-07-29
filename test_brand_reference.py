"""
Tests para la detección de marcas y su verificación contra el inventario.

Caso real que originó esto (real_conversations_withLeads/4.json): el lead pidió
"solo marca dewalt y makita" y el bot primero contestó "Entiendo, manejamos
rompedores Dewalt y Makita" y un minuto después "Actualmente no contamos con
rompedores Dewalt o Makita". Nada en el sistema sabía qué marcas manejamos, así
que el LLM improvisaba en cada turno.

No requieren llamadas al LLM: la detección y la evaluación son deterministas.
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
from brand_reference import (
    DISPONIBLE_EN_OTROS_TIPOS,
    DISPONIBLE_EN_TIPO,
    NO_DISPONIBLE,
    build_brand_disclaimer,
    detect_brand_mentions,
    evaluate_brand_names,
    evaluate_brands,
    get_all_own_brands,
    get_brands_for_category,
)
from inventory_service import InventoryService


# ============================================================================
# ÍNDICE DE MARCAS (derivado del inventario)
# ============================================================================

def test_marcas_propias_salen_del_inventario():
    marcas = get_all_own_brands()
    assert "Toku" in marcas
    assert "LGMG" in marcas
    assert "DeWalt" not in marcas


@pytest.mark.parametrize("tipo, esperadas", [
    ("rompedor", ["Toku"]),
    ("montacargas", ["Noblelift"]),
    ("plataforma", ["LGMG"]),
    ("generador", ["Koshin", "Shindaiwa"]),
    ("torre_iluminacion", ["Shindaiwa", "Trime"]),
])
def test_marcas_por_tipo_de_maquinaria(tipo, esperadas):
    assert get_brands_for_category(tipo) == esperadas


# ============================================================================
# DETECCIÓN
# ============================================================================

@pytest.mark.parametrize("mensaje, esperadas", [
    # El caso real de 4.json
    ("Solo marca dewalt y makita por favor", ["DeWalt", "Makita"]),
    ("No tienen marca dewalt?", ["DeWalt"]),
    ("O makita?", ["Makita"]),
    # Marcas externas frecuentes, sin la palabra "marca"
    ("¿manejan Bosch?", ["Bosch"]),
    ("busco una plataforma Genie o JLG", ["Genie", "JLG"]),
    ("compresor Atlas Copco", ["Atlas Copco"]),
    # Marcas nuestras
    ("¿tienen soldadoras Shindaiwa?", ["Shindaiwa"]),
    ("quiero un generador Koshin", ["Koshin"]),
    # Marca que no está en ninguna lista: la salva el patrón "marca X"
    ("quiero marca Zoomlion", ["Zoomlion"]),
])
def test_detecta_marcas(mensaje, esperadas):
    # Se comparan los nombres canónicos: el lead escribe "dewalt" y el bot
    # responde "DeWalt".
    detectadas = [ev.marca for ev in evaluate_brands(mensaje)]
    assert detectadas == esperadas, f"{mensaje!r} → {detect_brand_mentions(mensaje)}"


@pytest.mark.parametrize("mensaje", [
    # Flujo normal: saludos, nombres, datos de contacto
    "Hola buen día",
    "Mateo Velásquez",
    "Disculpe tiene rompedores para concreto de 10 y 15 kg?",
    "No, busco de menor kg",
    "compras2024@empresa.com",
    "Constructora H2O SA de CV",
    "en Jalisco",
    # Códigos de máquina: los resuelve machine_reference, no son marcas
    "PDSG900VR",
    "CAT320D",
    "quiero la S4046E II",
    # El lead dice que la marca le da igual
    "cualquier marca está bien",
    "la marca no importa",
    "¿qué marca de rompedores manejan?",
    # Apellidos que coinciden con marcas: sin contexto de maquinaria, no cuentan
    "Miller",
    "Soy Juan Clark",
    "Mi apellido es Lincoln",
])
def test_no_detecta_falsos_positivos(mensaje):
    assert detect_brand_mentions(mensaje) == [], f"Falso positivo en {mensaje!r}"


def test_apellido_ambiguo_si_cuenta_con_contexto_de_maquinaria():
    """'Miller' solo es marca si el mensaje habla de equipo."""
    assert detect_brand_mentions("tienen soldadoras Miller?") == ["Miller"]


# ============================================================================
# DISPONIBILIDAD CONTRA EL INVENTARIO
# ============================================================================

def test_marca_que_no_manejamos():
    ev = evaluate_brands("Solo marca dewalt y makita por favor", "rompedor")
    assert [e.marca for e in ev] == ["DeWalt", "Makita"]
    assert all(e.estatus == NO_DISPONIBLE for e in ev)
    # Y sabe qué ofrecer en su lugar
    assert ev[0].marcas_del_tipo == ["Toku"]


def test_marca_que_manejamos_en_el_tipo_pedido():
    ev = evaluate_brands("¿tienen soldadoras Shindaiwa?", "soldadora")
    assert ev[0].estatus == DISPONIBLE_EN_TIPO


def test_marca_que_manejamos_pero_no_en_ese_tipo():
    """
    El caso que el bot no podía distinguir: tener la marca no es tenerla en la
    categoría que el lead busca. Shindaiwa sí, pero no en rompedores.
    """
    ev = evaluate_brands("¿manejan rompedores Shindaiwa?", "rompedor")
    assert ev[0].estatus == DISPONIBLE_EN_OTROS_TIPOS
    assert "soldadoras" in ev[0].tipos_de_la_marca
    assert ev[0].marcas_del_tipo == ["Toku"]


def test_sin_tipo_de_maquinaria_solo_se_evalua_la_marca():
    ev = evaluate_brands("¿manejan Shindaiwa?")
    assert ev[0].estatus == DISPONIBLE_EN_TIPO
    assert ev[0].tipo_solicitado is None


def test_la_evaluacion_depende_del_tipo_vigente():
    """
    La misma marca se re-evalúa cuando el lead dice qué máquina quiere: por eso
    las marcas se guardan crudas en el estado y no ya resueltas.
    """
    assert evaluate_brand_names(["Koshin"], "generador")[0].estatus == DISPONIBLE_EN_TIPO
    assert evaluate_brand_names(["Koshin"], "rompedor")[0].estatus == DISPONIBLE_EN_OTROS_TIPOS


# ============================================================================
# TEXTO GENERADO
# ============================================================================

def test_disclaimer_niega_y_ofrece_la_alternativa_real():
    texto = build_brand_disclaimer(evaluate_brands("marca dewalt y makita", "rompedor"))
    assert "no manejamos DeWalt ni Makita" in texto
    assert "Toku" in texto


def test_disclaimer_vacio_si_si_manejamos_la_marca():
    """No hay nada que aclarar: la recomendación ya será de esa marca."""
    assert build_brand_disclaimer(evaluate_brands("soldadora Shindaiwa", "soldadora")) == ""


# ============================================================================
# INSTRUCCIÓN AL LLM
# ============================================================================

def _instruccion(mensaje, tipo):
    return IntelligentResponseGenerator._build_brand_instruction(
        None, evaluate_brands(mensaje, tipo)
    )


def test_instruccion_prohibe_afirmar_la_marca_que_no_tenemos():
    instruccion = _instruccion("Solo marca dewalt y makita por favor", "rompedor")
    assert "DeWalt: NO la manejamos" in instruccion
    assert "Makita: NO la manejamos" in instruccion
    assert "Toku" in instruccion
    assert "PROHIBIDO afirmar o insinuar que manejamos una marca" in instruccion


def test_instruccion_distingue_marca_sin_ese_tipo():
    instruccion = _instruccion("¿tienen rompedores Shindaiwa?", "rompedor")
    assert "SÍ la manejamos, pero únicamente en" in instruccion
    assert "NO tenemos rompedores (martillos neumáticos) de esa marca" in instruccion


def test_sin_marcas_no_hay_instruccion():
    assert _instruccion("Hola buen día", "rompedor") == ""


# ============================================================================
# FILTRO DE INVENTARIO POR MARCA
# ============================================================================

def test_recomendacion_respeta_la_marca_pedida():
    service = InventoryService()
    koshin = service.find_matching_machines("generador", {}, brands=["Koshin"])
    assert koshin, "Debería haber generadores Koshin"
    assert all(m["modelo"].startswith("Koshin") for m in koshin)


def test_filtro_de_marca_se_ignora_si_no_hay_nada_de_esa_marca():
    """
    Vale más ofrecerle la alternativa que dejarlo sin recomendación: que no
    manejamos su marca ya se le dice aparte.
    """
    service = InventoryService()
    assert service.find_matching_machines("rompedor", {}, brands=["DeWalt"])


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


def test_las_marcas_se_guardan_en_el_estado(chatbot):
    chatbot._detect_and_store_brands("Solo marca dewalt y makita por favor")
    assert chatbot.state["marcas_solicitadas"] == ["DeWalt", "Makita"]
    assert chatbot.state["marcas_aclaradas"] is False


def test_la_marca_se_conserva_hasta_saber_el_tipo_de_maquina(chatbot):
    """
    En 4.json el lead pidió la marca ANTES de que el bot supiera qué buscaba.
    La marca no se puede evaluar en ese turno, así que tiene que sobrevivir.
    """
    chatbot._detect_and_store_brands("Solo marca dewalt y makita por favor")
    chatbot.state["tipo_maquinaria"] = "rompedor"

    generator = IntelligentResponseGenerator.__new__(IntelligentResponseGenerator)
    evaluaciones = generator._pending_brand_evaluations(chatbot.state)

    assert [e.marca for e in evaluaciones] == ["DeWalt", "Makita"]
    assert all(e.estatus == NO_DISPONIBLE for e in evaluaciones)


def test_no_se_repite_la_aclaracion_en_cada_turno(chatbot):
    chatbot._detect_and_store_brands("marca dewalt")
    chatbot.state["marcas_aclaradas"] = True

    generator = IntelligentResponseGenerator.__new__(IntelligentResponseGenerator)
    assert generator._pending_brand_evaluations(chatbot.state) == []

    # Pero si el lead vuelve a preguntar, hay que volver a responderle
    chatbot._detect_and_store_brands("No tienen marca dewalt?")
    assert chatbot.state["marcas_aclaradas"] is False
    assert generator._pending_brand_evaluations(chatbot.state)


# ============================================================================
# REGRESIÓN DE 4.json
# ============================================================================

def test_la_recomendacion_aclara_la_marca_antes_de_listar(chatbot):
    """
    El turno donde el bot listó dos Toku sin decir una palabra de las marcas que
    el lead había pedido. Ese silencio es lo que llevó al lead a repreguntar y
    al bot a contradecirse.
    """
    generator = IntelligentResponseGenerator.__new__(IntelligentResponseGenerator)
    generator.inventory_service = InventoryService()

    state = dict(chatbot.state)
    state.update({
        "nombre": "Mateo",
        "tipo_maquinaria": "rompedor",
        "detalles_maquinaria": {"peso_kg": 10},
        "marcas_solicitadas": ["DeWalt", "Makita"],
        "marcas_aclaradas": False,
    })

    respuesta = generator.generate_response(
        "Mateo Velásquez", [], {"nombre": "Mateo"}, state,
        next_question="¿Te gustaría recibir una cotización?",
        question_type="quiere_cotizacion",
    )

    assert "no manejamos DeWalt ni Makita" in respuesta
    assert "Toku" in respuesta
    # Lo que decía antes y era falso
    assert "manejamos rompedores Dewalt" not in respuesta
    assert state["marcas_aclaradas"] is True
