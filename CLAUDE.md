# CLAUDE.md

Las instrucciones para agentes de IA de este repositorio viven en
**[`AGENTS.md`](AGENTS.md)**. Léelo primero.

Puntos clave:
- Este es el bot de WhatsApp de AlphaC para calificación de leads de
  maquinaria (Azure Functions + LangChain + Azure OpenAI).
- El comando `"reset"` es solo para pruebas — ningún lead real debe usarlo.
  Ver [AGENTS.md](AGENTS.md).
- El único CRM es Odoo (`odoo_manager.py`). HubSpot se eliminó por completo
  del proyecto — no reintroduzcas nada de eso.
- La integración con Odoo es best-effort a propósito: si Odoo falla, el bot
  debe seguir la conversación con total normalidad. Nunca conviertas esa
  integración en una dependencia dura del flujo de mensajes.
