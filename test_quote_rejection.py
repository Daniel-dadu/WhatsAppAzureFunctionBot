import os

os.environ.setdefault("FOUNDRY_API_KEY", "test-key")
os.environ.setdefault("FOUNDRY_ENDPOINT", "https://example.invalid")

from ai_langchain import IntelligentLeadQualificationChatbot


class _InventoryResponder:
    @staticmethod
    def is_inventory_question(_message):
        return False


class _ResponseGenerator:
    @staticmethod
    def generate_final_response(_state):
        raise AssertionError("A rejected quotation must not generate a final quotation")

    @staticmethod
    def generate_response(*_args, **_kwargs):
        return "Respuesta posterior al cierre"


def _build_chatbot():
    chatbot = IntelligentLeadQualificationChatbot.__new__(
        IntelligentLeadQualificationChatbot
    )
    chatbot.state = {
        "messages": [],
        "tipo_ayuda": "maquinaria",
        "tipo_maquinaria": "generador",
        "detalles_maquinaria": {"potencia_kw": 20},
        "maquinas_recomendadas": ["Shindaiwa DGM250MK-D"],
        "maquina_seleccionada": None,
        "quiere_cotizacion": False,
        "completed": False,
        "cotizacion_enviada": False,
        "cierre_ofrecido": False,
    }
    chatbot.inventory_responder = _InventoryResponder()
    chatbot.response_generator = _ResponseGenerator()
    chatbot._machine_ref = None
    chatbot._coverage = None
    chatbot._add_message_and_return_response = lambda response, _question_type: response
    return chatbot


def test_rejected_quotation_closes_without_generating_one():
    chatbot = _build_chatbot()

    response = chatbot._process_and_respond(
        "No quiero una cotización.",
        {"quiere_cotizacion": False},
    )

    assert response == "De acuerdo, ¿hay algo más en lo que te pueda ayudar?"
    assert chatbot.state["completed"] is True
    assert chatbot.state["cierre_ofrecido"] is True
    assert chatbot.state["cotizacion_enviada"] is False
    assert chatbot.state["maquina_seleccionada"] is None


def test_rejected_quotation_never_calls_pdf_callback():
    chatbot = _build_chatbot()
    chatbot.current_user_id = "test-user"
    chatbot.send_pdf_callback = lambda *_args: (_ for _ in ()).throw(
        AssertionError("PDF callback must not run")
    )

    assert chatbot._try_send_pdf_quotation() is False
