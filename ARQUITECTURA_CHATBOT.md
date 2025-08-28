# Arquitectura del Sistema de Chatbot WhatsApp con Agente Humano

## Resumen del Sistema Actual

La Azure Function actual implementa:
- Slot-filling inteligente con LangChain para extraer datos de leads
- Conversación automatizada vía WhatsApp API
- Estado en memoria (InMemoryStateStore) - pendiente migrar a Cosmos DB
- Esqueleto de integración con HubSpot (no implementado)

## Nuevas Funcionalidades a Implementar

### 1. Modos de Conversación
- **Modo Bot**: Respuesta automática con pipeline actual
- **Modo Agente**: Humano responde, sin respuesta automática pero con slot-filling activo

### 2. Intervención de Agente Humano
- Endpoint especial para recibir mensajes del agente
- Capacidad de "tomar control" de conversaciones activas del bot
- Timeout automático: regreso a modo bot después de 30 minutos de inactividad del agente

### 3. Persistencia Completa
- Migración de InMemoryStateStore a Cosmos DB
- Mantenimiento de compatibilidad con InMemoryStateStore para pruebas
- Integración real con HubSpot

## Estructura de Datos

### ConversationState Expandido
```typescript
ConversationState = {
    // Campos existentes (mantener compatibilidad)
    "messages": [
        {
            "role": "user" | "assistant",  // Mantener formato actual
            "content": string,
            "timestamp": datetime,  // NUEVO
            "sender": "lead" | "bot" | "agente"  // NUEVO
        }
    ],
    "nombre": string,
    "tipo_maquinaria": MaquinariaType,
    "detalles_maquinaria": object,
    "sitio_web": string,
    "uso_empresa_o_venta": string,
    "nombre_completo": string,
    "nombre_empresa": string,
    "giro_empresa": string,
    "correo": string,
    "telefono": string,
    "completed": boolean,
    
    // Campos nuevos a agregar
    "lugar_requerimiento": string,  // NUEVO: lugar donde se requiere la máquina
    "conversation_mode": "bot" | "agente",  // NUEVO
    "asignado_asesor": string  // NUEVO: ID del asesor asignado
}
```

### Estructura en Cosmos DB
```json
{
  "id": "conv_12345",  
  "lead_id": "5219931340372",
  "canal": "whatsapp",  
  "created_at": "2025-08-24T18:00:00Z",  
  "updated_at": "2025-08-24T18:15:00Z",  
  "state": {
    // Aquí va todo el ConversationState
  },
  "messages": [
    {
      "id": "msg_001",
      "sender": "lead",   // "bot" | "agente" | "lead"
      "text": "Hola, me interesa una excavadora.",
      "timestamp": "2025-08-24T18:01:00Z",
      "delivered": true,
      "read": true
    },
    {
      "id": "msg_002",
      "sender": "bot",
      "text": "Perfecto, ¿qué tipo de maquinaria buscas exactamente?",
      "timestamp": "2025-08-24T18:02:00Z",
      "delivered": true,
      "read": false
    }
  ],
  "conversation_mode": "bot",
  "asignado_asesor": "asesor_ventas_123"
}
```

**Decisión**: No rediseñar ConversationState, mantener compatibilidad y hacer transformación en CosmosDBStateStore.

## Flujo de Slot-filling

### Orden de Campos (Actualizado)
1. nombre
2. tipo_maquinaria
3. detalles_maquinaria (específicos por tipo)
4. **lugar_requerimiento** (NUEVO - después de detalles, antes de uso)
5. uso_empresa_o_venta
6. nombre_empresa
7. sitio_web
8. giro_empresa
9. nombre_completo
10. correo
11. telefono

### Slot-filling Contextual con Agente
- **Ejecutar solo en mensajes del lead**
- **Contexto**: Usar último mensaje del bot/agente como contexto (no solo mensajes con "?")
- **Ejemplo**: 
  - Agente: "Supongo que necesitas un rompedor"
  - Lead: "Así es"
  - Sistema: Extraer `tipo_maquinaria: "rompedores"`

## Endpoints y Autenticación

### Endpoint Existente
- `POST /whatsappbot1` - Maneja webhooks de WhatsApp (leads)

### Nuevo Endpoint
- `POST /agent-message` - Recibe mensajes del agente humano
- **Autenticación**: Token simple (no avanzado)
- **Payload**: 
  ```json
  {
    "wa_id": "5219931340372",
    "message": "texto del agente"
  }
  ```

## Lógica de Modos de Conversación

### Cambio a Modo Agente
- **Trigger**: Agente presiona botón en interfaz web
- **Acción**: Actualizar `conversation_mode` a "agente" (solo si no estaba ya)
- **Persistencia**: Se mantiene entre sesiones hasta timeout o cambio manual

### Timeout (30 minutos)
- **Medición**: Desde timestamp del último mensaje del agente
- **Validación**: Solo cuando llega nuevo mensaje del lead (no polling)
- **Acción**: Cambiar automáticamente a modo "bot"

### Flujo por Modo

#### Modo Bot (Actual)
1. Lead envía mensaje → Azure Function
2. Slot-filling extrae datos
3. Bot genera respuesta automática
4. Envío vía WhatsApp API
5. Actualizar HubSpot (asíncrono)

#### Modo Agente
1. Lead envía mensaje → Azure Function
2. Slot-filling extrae datos (usando contexto de agente)
3. **NO enviar respuesta automática**
4. Actualizar estado en Cosmos DB
5. Actualizar HubSpot (asíncrono)

#### Agente Envía Mensaje
1. Agente envía vía endpoint especial
2. Actualizar `conversation_mode` si necesario
3. Agregar mensaje a lista de messages
4. Enviar mensaje a lead vía WhatsApp API
5. Actualizar estado en Cosmos DB

## Integración HubSpot

### Triggers de Actualización
- **Tiempo real**: Después de cada extracción de datos por slot-filling
- **Modo**: Funciona tanto en modo bot como agente
- **Ejecución**: Asíncrona (no bloquear respuesta)

### Manejo de Errores
- **Fallas de HubSpot**: No afectar flujo principal (Cosmos DB sigue funcionando)
- **Retry Logic**: No implementar inicialmente (mejora futura)

## Orden de Implementación

### Fase 1: Estructura de Datos
1. Expandir ConversationState con campos nuevos
2. Implementar CosmosDBStateStore completo
3. Mantener InMemoryStateStore para pruebas

### Fase 2: Modos de Conversación
1. Agregar endpoint `/agent-message`
2. Implementar lógica de cambio de modos
3. Implementar timeout de 30 minutos

### Fase 3: Slot-filling Mejorado
1. Integrar slot-filling contextual (considerar mensajes de agente)
2. Agregar campo `lugar_requerimiento` al flujo (creo que ya está implementado)
3. Asegurar funcionamiento en ambos modos

### Fase 4: Integraciones
1. Implementar actualización HubSpot completa
2. Hacer updates asíncronos tras slot-filling
3. Testing integral del sistema

### Fase 5: Notificación a Asesores (Futuro)
1. Implementar lógica de asignación de asesor basada en `lugar_requerimiento`
2. Envío automático de mensaje WhatsApp al asesor correspondiente
3. Actualización del campo `asignado_asesor` en base de datos
*Nota: Funcionalidad a definir en detalle posteriormente*

## Consideraciones Técnicas

### Cosmos DB
- **Partition Key**: `wa_id`
- **TTL**: No automático
- **Consistency**: Default (no requerimientos especiales)

### Seguridad
- **Endpoint agente**: Token simple entre Azure Functions
- **WhatsApp**: Mantener verificación de usuarios autorizados actual

### Compatibilidad
- **InMemoryStateStore**: Mantener para pruebas con `test_chatbot.py`
- **Código ai_langchain.py**: Modificar lo mínimo posible
- **APIs existentes**: Mantener retrocompatibilidad

## Casos de Uso Clave

### Caso 1: Agente Toma Control
1. Conversación activa en modo bot
2. Agente presiona "Tomar Control" 
3. Sistema cambia a modo agente
4. Próximo mensaje del lead no genera respuesta automática
5. Slot-filling sigue activo usando contexto del último mensaje del bot

### Caso 2: Timeout de Agente
1. Conversación en modo agente
2. Pasan 30 minutos sin mensaje del agente
3. Lead envía nuevo mensaje
4. Sistema detecta timeout y cambia a modo bot
5. Bot responde automáticamente

### Caso 3: Slot-filling con Contexto de Agente
1. Agente: "¿Trabajas para MachinesCorp?"
2. Lead: "Sí"
3. Slot-filling extrae: `nombre_empresa: "MachinesCorp"`
4. Datos se guardan en Cosmos DB y HubSpot

---

## Estado del Documento
- **Creado**: Enero 2025
- **Última actualización**: Fase 1 completada
- **Próximo paso**: Implementar Fase 2 - Modos de Conversación

## Historial de Implementación

### ✅ Fase 1: Estructura de Datos (Completada)
- [x] Expandir ConversationState con campos nuevos: `lugar_requerimiento`, `conversation_mode`, `asignado_asesor`
- [x] Agregar `timestamp` y `sender` a estructura de mensajes
- [x] Implementar CosmosDBStateStore completo con transformaciones bidireccionales
- [x] Agregar `lugar_requerimiento` al flujo de slot-filling (posición 4, después de detalles_maquinaria)
- [x] Mantener compatibilidad completa con InMemoryStateStore para pruebas

**Cambios realizados:**
- `state_management.py`: ConversationState expandido, CosmosDBStateStore implementado
- `ai_langchain.py`: Slot-filling actualizado con nuevo campo, mensajes con metadata completo

### 🚀 Optimización de Performance: Smart Dispatcher (Completada)
- [x] Implementar smart dispatcher en `save_conversation_state()`
- [x] Operaciones granulares con Cosmos DB Patch Operations
- [x] Detección automática de cambios específicos
- [x] Fallback automático a operación completa en caso de error

**Beneficios de la optimización:**
- **Eficiencia de red**: Solo se envían los datos que cambiaron
- **Costo reducido**: Menor consumo de RUs en Cosmos DB
- **Mejor concurrencia**: Menos conflictos entre operaciones simultáneas
- **Escalabilidad**: Performance constante independiente del tamaño de conversación
- **Compatibilidad**: Interfaz idéntica, optimización transparente

**Operaciones optimizadas:**
- Append de mensajes nuevos (sin reescribir mensajes anteriores)
- Patch de campos específicos del lead (solo campos que cambiaron)
- Actualización de modo de conversación
- Fallback automático a operación completa si falla patch

### 🏗️ Refactorización: Arquitectura Stateless (Completada)
- [x] Eliminar variable global `whatsapp_bot`
- [x] Implementar factory method `create_whatsapp_bot()`
- [x] Instancia fresca por request
- [x] Auto-detección de entorno (dev/prod)

**Beneficios de la refactorización:**
- **Aislamiento total**: Cada request es completamente independiente
- **Sin estado compartido**: Elimina interferencias entre usuarios concurrentes
- **Memory management**: Azure Functions limpia automáticamente después de cada request
- **Mejor testability**: Fácil inyección de mocks y testing
- **Flexibilidad**: Auto-detección entre InMemoryStateStore (dev) y CosmosDBStateStore (prod)
- **Robust error handling**: Fallback automático a InMemory si Cosmos DB falla

**Cambios realizados:**
- `function_app.py`: Factory methods para bot y state store, eliminación de estado global
- Compatibilidad total con el patrón stateless de Azure Functions
