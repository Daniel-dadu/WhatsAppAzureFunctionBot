# AGENTS.md — Bot de WhatsApp para AlphaC

Este archivo es para cualquier IA que trabaje en este repositorio (Claude Code,
Cursor, Antigravity, etc.). Cubre lo que el código **no** deja claro por sí solo:
decisiones de diseño y reglas de negocio que no son obvias leyendo los archivos.

Para la descripción funcional del proyecto (qué hace el bot, tipos de
maquinaria soportados, variables de entorno, arquitectura general) ver
[README.md](README.md). Este archivo es un complemento, no un reemplazo.

## Qué es esto

Azure Function en Python que atiende leads de maquinaria ligera para AlphaC
por WhatsApp. Usa Azure OpenAI + LangChain para la conversación, Cosmos DB
para persistir el estado de cada conversación, y sincroniza los leads con
Odoo CRM (`odoo_manager.py`, modelo `crm.lead` vía su API externa JSON-RPC).

## Reglas de comportamiento que no son obvias leyendo el código

### El comando "reset" es SOLO para pruebas

`whatsapp_bot.py::_handle_reset_command` se dispara cuando el texto del
mensaje es literalmente `"reset"`. Existe únicamente para pruebas
manuales/QA. **Ningún lead real debería poder ni necesitar usarlo.**

No:
- lo documentes como algo que el usuario final puede invocar,
- construyas lógica de producción que dependa de que un lead lo use,
- lo menciones en mensajes del bot o en materiales de cara al cliente.

Si en algún momento se necesita una forma real de que un lead reinicie su
conversación, debe ser una función nueva y deliberada — no asumas que este
comando de depuración cumple ese rol.

### El CRM es Odoo — HubSpot ya no existe en este proyecto

- En algún momento se planteó integrar con HubSpot, pero **nunca se llegó a
  una integración completa en producción**, y todo ese código
  (`hubspot_manager.py`, el campo `hubspot_contact_id` del estado, las
  variables `HUBSPOT_*`) se eliminó por completo del repositorio.
- La única integración de CRM es **Odoo** (`odoo_manager.py`), sobre el
  modelo `crm.lead` vía su API externa JSON-RPC.
- Si encuentras referencias a HubSpot en algún lado (comentarios viejos,
  commits antiguos, este mismo archivo si alguien lo desactualiza), es
  historia — no un sistema activo. No lo reintroduzcas ni construyas nada
  asumiendo que existe.

### La integración con Odoo es "best-effort" por diseño — nunca debe bloquear la conversación

`create_odoo_manager_from_env()` y todos los métodos públicos de
`OdooManager` atrapan sus propias excepciones y regresan `None`/no hacen
nada en vez de lanzar error. Los call sites en `function_app.py`,
`whatsapp_bot.py` y `ai_langchain.py` también envuelven las llamadas a Odoo
en try/except adicionales.

Esto es intencional: **si Odoo está caído, mal configurado, o tarda
demasiado, el bot debe seguir atendiendo al lead por WhatsApp con total
normalidad.** Cualquier cambio futuro a esta integración debe preservar esa
garantía — nunca dejes que una falla de Odoo interrumpa o retrase la
respuesta al lead. El timeout de red hacia Odoo está fijado a propósito
(`REQUEST_TIMEOUT_SECONDS` en `odoo_manager.py`) para acotar el peor caso;
no lo subas sin pensar en el impacto en la latencia de cada mensaje.

### El mapeo de campos bot → Odoo no es 1:1

- `tipo_cliente` del bot (`"distribuidor"` | `"cliente_final"`) se traduce a
  `tipo_prospecto` en Odoo (`"distribuidor"` | `"cliente"`) — los valores
  **no** son los mismos strings. Ver `TIPO_PROSPECTO_MAP` en
  `odoo_manager.py`.
- `tipo_maquinaria` y `marcas_solicitadas` **no tienen campo dedicado en
  Odoo todavía** — se meten como texto dentro de `description`,
  recalculando el texto completo en cada actualización (ver
  `_build_extra_notes` en `odoo_manager.py`). Esto sobrescribe cualquier
  nota manual que alguien escriba directo en el lead desde Odoo. Es un
  parche temporal; hay que quitarlo en cuanto el integrador de Odoo agregue
  esos dos campos.
- La API de Odoo (colección de Postman entregada por el integrador) **no
  incluye eliminación de leads** (`unlink`). Por eso `OdooManager` no tiene
  `delete_lead` — está ausente a propósito, no es un descuido.

## Testing

`test_chatbot.py` **no es una suite de pytest** a pesar del nombre. Solo
tiene un test real (`test_manually`), que además requiere un fixture que no
existe y falla si se corre con pytest. El resto del archivo son escenarios
que se ejecutan manualmente vía `python test_chatbot.py`, requieren
credenciales reales de Azure OpenAI, y hacen llamadas reales al LLM. No
asumas que `pytest test_chatbot.py` da cobertura automática del chatbot.

Los demás `test_*.py` (`test_pricing_service.py`, `test_company_profile.py`,
etc.) sí son pytest estándar y se pueden correr normal.

## Estado de la integración con Odoo

(Actualizar esta sección conforme avance el trabajo, para que la siguiente
sesión de IA no tenga que re-derivar todo esto desde cero.)

- ✅ `odoo_manager.py` construido y probado contra la API real de Odoo
  (autenticación, create, read, write, search_read).
- ✅ Conectado al flujo real de mensajes: se crea/actualiza el lead en Odoo
  en cada mensaje, de forma best-effort.
- ✅ Probado de punta a punta corriendo la función localmente (`func start`)
  con un payload de WhatsApp simulado: creó y actualizó un lead real en el
  sandbox de Odoo, y confirmó que si otra integración falla (por ejemplo,
  credenciales inválidas), la conversación sigue sin interrumpirse.
- ✅ 8 de 10 campos personalizados confirmados y mapeados: `tipo_prospecto`,
  `giro_empresa`, `tipo_ayuda`, `caracteristicas_especificas`,
  `modelo_especifico`, `constancia_situacion_fiscal_entregada`,
  `identificador_conversacion_whatsapp`, y resolución de `state_id`/
  `country_id` vía `res.country.state`.
- ⏳ Pendiente con el integrador de Odoo: campo dedicado para
  `tipo_maquinaria` y `marcas_solicitadas` (hoy van dentro de
  `description` como parche).
- ⏳ Pendiente: el endpoint `new-lead-form` (`function_app.py`) sigue
  siendo un stub — falta conectar el webhook real de Odoo, el envío de la
  plantilla de WhatsApp de primer contacto (`notificacion_de_leads` en
  `whatsapp_bot.py`, que ya existe y funciona), y el prellenado del estado
  del lead antes de que responda.
- ⏳ Pendiente: asignación automática por zona/asesor — bloqueado porque no
  tenemos el modelo de datos de zona→asesor de Odoo.
- ⏳ Pendiente: qué hacer con el lead de Odoo cuando se usa el comando
  "reset" (hoy no se toca; recordar que ese comando es solo de pruebas, ver
  arriba).
