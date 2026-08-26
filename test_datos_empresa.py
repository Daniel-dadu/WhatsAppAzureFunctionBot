"""
Regresión de real_conversations_withLeads/6.json.

El bot le mandó a la lead "Necesito los siguientes datos de su empresa para
continuar con la cotización." sin decir cuáles: ella reenvió tres veces los
mismos datos que ya había dado. La petición de datos de empresa SIEMPRE tiene
que nombrar lo que falta.
"""

from ai_langchain import (
    build_datos_empresa_question,
    get_pending_empresa_fields,
    response_omite_campos_pendientes,
)

MENSAJE_VAGO = "Necesito los siguientes datos de su empresa para continuar con la cotización."


# ============================================================================
# LA PETICIÓN SIEMPRE NOMBRA LOS CAMPOS
# ============================================================================

def test_peticion_nunca_es_vaga():
    """Cualquier combinación de pendientes produce un texto que los nombra."""
    estados = [
        {},
        {"tipo_cliente": "distribuidor"},
        {"tipo_cliente": "distribuidor", "correo": "a@b.com", "lugar_requerimiento": "Cancún"},
        {"tipo_cliente": "cliente_final", "correo": "a@b.com"},
        {"tipo_cliente": "cliente_final", "correo": "a@b.com", "lugar_requerimiento": "Cancún",
         "nombre_empresa": "ACME"},
        {"tipo_cliente": "distribuidor", "correo": "a@b.com", "lugar_requerimiento": "Cancún",
         "constancia_fiscal_entregada": "No tiene"},
    ]
    for estado in estados:
        pending = get_pending_empresa_fields(estado)
        pregunta = build_datos_empresa_question(pending)
        assert pregunta, f"Sin petición para {estado}"
        assert not response_omite_campos_pendientes(pregunta, pending), (
            f"La petición no nombra los pendientes {pending}: {pregunta!r}"
        )
        assert pregunta != MENSAJE_VAGO


def test_varios_pendientes_van_enumerados():
    """El primer bloque (uso, correo, estado) se pide como lista numerada."""
    pending = get_pending_empresa_fields({})
    pregunta = build_datos_empresa_question(pending)

    assert "1. ¿Te dedicas a la venta o renta de maquinaria?" in pregunta
    assert "2. Correo electrónico" in pregunta
    assert "3. Estado de la República Mexicana" in pregunta
    # Nunca viñetas: WhatsApp las renderiza mal y el prompt las prohíbe.
    assert "•" not in pregunta


def test_turno_roto_de_6json_pide_la_constancia_por_su_nombre():
    """
    Estado exacto del turno que falló: la lead ya dio venta, correo y Cancún,
    así que lo único pendiente era la Constancia de Situación Fiscal.
    """
    estado = {
        "tipo_cliente": "distribuidor",
        "correo": "compras@proveeduriayservicios.com",
        "lugar_requerimiento": "Cancun",
        "constancia_fiscal_entregada": None,
    }
    pending = get_pending_empresa_fields(estado)
    assert pending == ["Constancia de Situación Fiscal"]

    pregunta = build_datos_empresa_question(pending)
    assert "Constancia de Situación Fiscal" in pregunta
    # Un solo dato pendiente no se pide como lista numerada.
    assert "1." not in pregunta


def test_no_se_repiten_datos_ya_entregados():
    """Lo que la lead ya contestó no vuelve a aparecer en la petición."""
    estado = {
        "tipo_cliente": "cliente_final",
        "correo": "compras@proveeduriayservicios.com",
        "lugar_requerimiento": "Cancún",
        "nombre_empresa": "Operadora Porserv del Sureste",
    }
    pregunta = build_datos_empresa_question(get_pending_empresa_fields(estado))

    assert "giro" in pregunta.lower()
    assert "correo" not in pregunta.lower()
    assert "nombre de tu empresa" not in pregunta.lower()


def test_sin_pendientes_no_hay_peticion():
    assert build_datos_empresa_question([]) == ""


# ============================================================================
# RED DE SEGURIDAD SOBRE LA RESPUESTA DEL LLM
# ============================================================================

def test_detecta_el_mensaje_vago_que_se_envio_en_produccion():
    pending = get_pending_empresa_fields({})
    assert response_omite_campos_pendientes(MENSAJE_VAGO, pending)
    assert response_omite_campos_pendientes(MENSAJE_VAGO, ["Constancia de Situación Fiscal"])


def test_acepta_una_respuesta_que_si_nombra_los_campos():
    respuesta = (
        "El precio va en la cotización formal. Para generarla necesito:\n"
        "1. Correo electrónico\n2. Estado de la República Mexicana"
    )
    pending = ["correo electrónico", "ubicación (estado de la República Mexicana)"]
    assert not response_omite_campos_pendientes(respuesta, pending)


def test_sin_campos_pendientes_no_se_marca_omision():
    """Sin nada que pedir, la red de seguridad no debe dispararse."""
    assert not response_omite_campos_pendientes("Gracias, Sandra.", [])
