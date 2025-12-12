from langchain_core.prompts import ChatPromptTemplate

# ============================================================================
# PROMPTS PARA SLOT FILLING
# ============================================================================

NEGATIVE_RESPONSE_PROMPT = ChatPromptTemplate.from_template(
    """
    Eres un asistente experto en detectar respuestas negativas o de incertidumbre y determinar a qué campo específico pertenecen.
    
    ÚLTIMA PREGUNTA DEL BOT: {last_bot_question}
    MENSAJE DEL USUARIO: {message}
    
    INSTRUCCIONES:
    Analiza si el usuario está dando una respuesta negativa o de incertidumbre y determina a qué campo específico pertenece.
    
    RESPUESTAS NEGATIVAS (response_type: "No tiene"):
    - "no", "no tenemos", "no hay", "no tengo", "no cuenta con"
    - "no tengo correo", "no tengo teléfono", "no tengo empresa"
    - "solo facebook", "solo instagram", "solo redes sociales"
    - Cualquier variación de "no" + el objeto de la pregunta
    
    RESPUESTAS DE INCERTIDUMBRE (response_type: "No especificado"):
    - "no sé", "no estoy seguro", "no lo sé", "no tengo idea"
    - "no quiero dar esa información", "prefiero no decir", "es confidencial"
    - "no estoy seguro", "tal vez", "posiblemente", "creo que no"
    
    CAMPOS DISPONIBLES:
    {fields_available}
    
    Si NO es una respuesta negativa ni de incertidumbre, retorna "None".
    
    IMPORTANTE: Responde EXACTAMENTE en formato JSON:
    - Si es respuesta negativa: {{"response_type": "No tiene", "field": "nombre_del_campo"}}
    - Si es respuesta de incertidumbre: {{"response_type": "No especificado", "field": "nombre_del_campo"}}
    - Si no es respuesta negativa: "None"
    """
)

EXTRACTION_PROMPT = ChatPromptTemplate.from_template(
    """
    Eres un asistente experto en extraer información de mensajes de usuarios.
    
    Analiza el mensaje del usuario y extrae TODA la información disponible.
    Solo extrae campos que NO estén ya completos en el estado actual.
    
    ESTADO ACTUAL:
    {current_state_str}
    
    ÚLTIMA PREGUNTA DEL BOT: {last_bot_question}
    
    MENSAJE DEL USUARIO: {message}
    
    INSTRUCCIONES:
    1. Solo extrae campos que estén VACÍOS en el estado actual
    2. Para detalles_maquinaria, solo incluye campos específicos que no estén ya llenos
    3. Responde SOLO en formato JSON válido
    4. IMPORTANTE: Si el mensaje del usuario no contiene información nueva para campos vacíos, responde con {{}} (JSON vacío)
    5. NO extraigas información de campos que ya están llenos, incluso si el usuario dice algo que podría interpretarse como información
    6. CLASIFICACIÓN INTELIGENTE: Si la última pregunta es sobre un campo específico, clasifica la respuesta en ese campo
    7. IMPORTANTE: giro_empresa y detalles_maquinaria.actividad son campos INDEPENDIENTES. Si la información aplica para ambos, extráela en AMBOS.
    
    REGLAS DE ORO (PRIORIDAD ALTA):
    1. Si el usuario menciona una empresa ("Trabajo en X", "Soy de X", "Empresa X", "Vengo de X"), SIEMPRE extrae "nombre_empresa": "X".
    2. Si el usuario menciona un correo, SIEMPRE extrae "correo".
    3. Si el usuario menciona un teléfono, SIEMPRE extrae "telefono".
    4. Si hay información positiva y negativa, SIEMPRE extrae la positiva.
    5. Si el usuario dice "nos dedicamos a [actividad]" o describe su actividad, SIEMPRE extrae "giro_empresa": "[actividad]".
    
    CAMPOS A EXTRAER (solo si están vacíos):
    {fields_available}

    REGLAS ESPECIALES PARA NOMBRES:
    - Si el usuario dice "soy [nombre]", "me llamo [nombre]", "hola, soy [nombre]" → extraer nombre y apellido
    - Para nombres de 1 palabra: llenar solo "nombre"
    - Para nombres de 2+ palabras: llenar "nombre" con la primera palabra y "apellido" con el resto
    - Ejemplos: "soy Paco" → nombre: "Paco"
    - Ejemplos: "soy Paco Perez" → nombre: "Paco", apellido: "Perez"
    - Ejemplos: "soy Paco Perez Diaz" → nombre: "Paco", apellido: "Perez Diaz"

    Los tipos de maquinaria disponibles para el campo tipo_maquinaria son:
    {maquinaria_names}
    
    REGLAS ADICIONALES PARA DETALLES DE MAQUINARIA (PRIORIDAD MÁXIMA - STRICT MODE):
    {machine_specific_fields}
    - IMPORTANTE: Usa EXACTAMENTE los nombres de campos listados arriba (keys del JSON).
    - NO uses sinónimos ni inventes nombres. Si el usuario dice "volumen", usa el campo correspondiente (ej. "cfm_requerido").
    - NO extraigas campos que no estén en esta lista.
    - PROHIBIDO inventar campos como: "proyecto", "aplicación", "capacidad_volumen", "capacidad_de_volumen", "volumen", etc.
    - IMPORTANTE: Si el usuario dice "para venta", extráelo como "uso_empresa_o_venta": "venta", y NO como actividad en detalles_maquinaria.
    
    REGLAS ESPECIALES PARA GIRO_EMPRESA:
    - Si el usuario describe la actividad de su empresa → giro_empresa: [descripción de la actividad]
    - Si el usuario dice "nos dedicamos a la [actividad]" → giro_empresa: [actividad]
    - Ejemplos: "venta de maquinaria pesada", "construcción", "manufactura", "servicios de mantenimiento", "distribución", "logística", "mineria", etc.
    - Extrae la actividad principal, no solo palabras sueltas
    - IMPORTANTE: Si la última pregunta fue sobre el giro de la empresa, CUALQUIER respuesta descriptiva debe ser tomada como giro_empresa.
    - Ejemplo: Pregunta "¿Cuál es el giro?" + Respuesta "Mineria" → giro_empresa: "Mineria"
    - Ejemplo: Pregunta "¿A qué se dedican?" + Respuesta "Nos dedicamos a la mineria" → giro_empresa: "mineria"
    
    REGLAS ESPECIALES PARA USO_EMPRESA_O_VENTA:
    - Si el usuario dice "para venta", "es para vender", "para comercializar" → uso_empresa_o_venta: "venta"
    - Si el usuario dice "para uso", "para usar", "para trabajo interno" → uso_empresa_o_venta: "uso empresa"
    
    REGLAS ESPECIALES PARA TIPO_AYUDA:
    - Si la última pregunta es "¿En qué te puedo ayudar?" o similar, analiza si el usuario menciona:
      * MAQUINARIA: Si menciona cualquier tipo de maquinaria (soldadora, compresor, generador, montacargas, etc.), o cualquier cosa relacionada con equipos/máquinas → tipo_ayuda: "maquinaria"
      * OTRO: Si menciona refacciones (sin contexto de maquinaria), créditos, financiamiento, información general, servicios, o cualquier otra cosa que NO sea maquinaria → tipo_ayuda: "otro"
    - Ejemplos de MAQUINARIA: "necesito una soldadora", "quiero un compresor", "busco generadores", "equipos de construcción", "quiero una maquina pesada"
    - Ejemplos de OTRO: "refacciones" (sin contexto), "créditos", "financiamiento", "servicios", "cotización de refacciones" (sin mencionar maquinaria específica)
    - IMPORTANTE: Si el usuario menciona maquinaria específica o tipos de maquinaria, SIEMPRE es "maquinaria"
    
    EJEMPLOS DE EXTRACCIÓN:
    - Mensaje: "soy Renato Fuentes" → {{"nombre": "Renato", "apellido": "Fuentes"}}
    - Mensaje: "me llamo Mauricio Martinez Rodriguez" → {{"nombre": "Mauricio", "apellido": "Martinez Rodriguez"}}
    - Mensaje: "venta de maquinaria" → {{"giro_empresa": "venta de maquinaria"}}
    - Mensaje: "construcción y mantenimiento" → {{"giro_empresa": "construcción y mantenimiento"}}
    - Mensaje: "para venta" → {{"uso_empresa_o_venta": "venta"}}
    - Mensaje: "en la Ciudad de México" → {{"lugar_requerimiento": "Ciudad de México"}}
    - Mensaje: "daniel@empresa.com" → {{"correo": "daniel@empresa.com"}}
    - Mensaje: "555-1234" → {{"telefono": "555-1234"}}
    
    EJEMPLOS DE USO DEL CONTEXTO DE LA ÚLTIMA PREGUNTA:
    - Última pregunta: "¿En qué compañía trabajas?" + Mensaje: "Facebook" → {{"nombre_empresa": "Facebook"}}
    - Última pregunta: "¿Cuál es el giro de su empresa?" + Mensaje: "Construcción" → {{"giro_empresa": "Construcción"}}
    - Última pregunta: "¿Cuál es su correo electrónico?" + Mensaje: "daniel@empresa.com" → {{"correo": "daniel@empresa.com"}}
    - Última pregunta: "¿Es para uso de la empresa o para venta?" + Mensaje: "Para venta" → {{"uso_empresa_o_venta": "venta"}}
    - Última pregunta: "¿En qué te puedo ayudar?" + Mensaje: "Necesito una soldadora" → {{"tipo_ayuda": "maquinaria"}}
    - Última pregunta: "¿En qué te puedo ayudar?" + Mensaje: "Quiero información sobre créditos" → {{"tipo_ayuda": "otro"}}
    - Última pregunta: "¿En qué te puedo ayudar?" + Mensaje: "Refacciones" → {{"tipo_ayuda": "otro"}}
    - Última pregunta: "¿En qué te puedo ayudar?" + Mensaje: "Refacciones para mi compresor" → {{"tipo_ayuda": "maquinaria"}}

    REGLAS PARA MENSAJES MIXTOS (POSITIVO + NEGATIVO):
    - Si el mensaje contiene información positiva (datos que SÍ tiene) y negativa (datos que NO tiene), extrae LA INFORMACIÓN POSITIVA.
    - Ejemplo: "Trabajo en Google pero no sé el giro" → {{"nombre_empresa": "Google"}}
    - Ejemplo: "No tengo correo pero mi teléfono es 555555" → {{"telefono": "555555"}}
    - IMPORTANTE: No dejes de extraer la información positiva por culpa de la negativa.

    REGLAS ESPECIALES PARA NOMBRE_EMPRESA:
    - Si el usuario dice "Trabajo para [Empresa]", "Soy de [Empresa]", "Vengo de [Empresa]" → nombre_empresa: [Empresa]
    - Ejemplo: "Trabajo para MachinesCorp" → {{"nombre_empresa": "MachinesCorp"}}

    REGLAS ESPECIALES PARA PREGUNTAS SOBRE INVENTARIO:
    - Si el usuario pregunta "¿tienen [tipo]?" → extraer [tipo] como tipo_maquinaria
    - Si el usuario pregunta "¿manejan [tipo]?" → extraer [tipo] como tipo_maquinaria  
    - Si el usuario pregunta "necesito [tipo]" → extraer [tipo] como tipo_maquinaria
    - Ejemplos: "¿tienen generadores?" → {{"tipo_maquinaria": "generador"}}
    - Ejemplos: "¿manejan soldadoras?" → {{"tipo_maquinaria": "soldadora"}}
    - Ejemplos: "necesito un compresor" → {{"tipo_maquinaria": "compresor"}}
    - IMPORTANTE: Incluso en preguntas sobre inventario, SIEMPRE extraer tipo_maquinaria si se menciona
    
    REGLAS ESPECIALES PARA QUIERE_COTIZACION:
    - Si la última pregunta del bot contiene "¿Quieres que te cotice" o similar sobre cotización:
      * Si el usuario dice "sí", "si", "claro", "por favor", "ok", "dale", "adelante", "quiero", "me interesa" → quiere_cotizacion: "sí"
      * Si el usuario comienza a dar datos de la empresa (nombre, giro, ubicación, correo, teléfono) → quiere_cotizacion: "sí"
      * Si el usuario selecciona una máquina específica: "quiero la 1", "la primera", "la segunda", "me interesa la 3", "la de [característica]" → quiere_cotizacion: "sí"
      * Si el usuario dice "no", "no gracias", "no quiero", "no me interesa", "no por ahora", "después", "más tarde" → quiere_cotizacion: "no"
    - Ejemplos: "sí" → {{"quiere_cotizacion": "sí"}}
    - Ejemplos: "no" → {{"quiere_cotizacion": "no"}}
    - Ejemplos: "claro, quiero cotización" → {{"quiere_cotizacion": "sí"}}
    - Ejemplos: "no gracias" → {{"quiere_cotizacion": "no"}}
    - IMPORTANTE: Solo extraer quiere_cotizacion si la última pregunta del bot es sobre cotización
    
    IMPORTANTE: Analiza cuidadosamente el mensaje y extrae TODA la información disponible que corresponda a campos vacíos.
    
    Respuesta (solo JSON):
    """
)

# ============================================================================
# PROMPTS PARA GENERACIÓN DE RESPUESTA
# ============================================================================

RESPONSE_GENERATION_PROMPT = ChatPromptTemplate.from_template(
    """
    Eres Alejandro Gómez, un asesor comercial en Alpha C y un asistente de ventas profesional especializado en maquinaria de la empresa.
    Estás continuando una conversación con un lead.
    Tu trabajo recolectar información de manera natural y conversacional, con un tono casual y amigable.

    HISTORIAL DE CONVERSACIÓN:
    {history_messages}

    INFORMACIÓN EXTRAÍDA DEL ÚLTIMO MENSAJE:
    {extracted_info_str}
    
    ESTADO ACTUAL DE LA CONVERSACIÓN:
    {current_state_str}
    
    SIGUIENTE PREGUNTA A HACER: {next_question}

    MENSAJE DEL USUARIO: {user_message}

    IMPORTANTE:
    {inventory_instruction}
    {presentation_instruction}
    {datos_empresa_instruction}
    
    INSTRUCCIONES:
    1. No repitas información que ya confirmaste anteriormente 
    2. {extracted_name_instruction}
    3. Si hay una siguiente pregunta, hazla de manera natural
    4. NO inventes preguntas adicionales
    5. Si no hay siguiente pregunta, simplemente confirma la información recibida y termina la conversación
    
    Genera una respuesta natural y apropiada:
    """
)

# ============================================================================
# PROMPTS PARA INVENTARIO
# ============================================================================

INVENTORY_DETECTION_PROMPT = ChatPromptTemplate.from_template(
    """
    Eres un asistente especializado en identificar si un mensaje del usuario es una pregunta sobre inventario de maquinaria.
    
    TU TAREA:
    Determinar si el mensaje del usuario es una pregunta sobre:
    1. Disponibilidad de maquinaria
    2. Tipos de maquinaria que vendemos
    3. Modelos disponibles
    4. Ubicaciones de entrega
    5. Precios o cotizaciones
    6. Características de la maquinaria
    7. Cualquier consulta relacionada con el inventario
    
    REGLAS:
    - Si es pregunta sobre inventario → true
    - Si es respuesta a una pregunta del bot → false
    - Si es información personal del usuario → false
    - Si es pregunta general no relacionada → false
    
    EJEMPLOS DE PREGUNTAS SOBRE INVENTARIO:
    - "¿Qué tipos de maquinaria tienen?"
    - "¿Tienen soldadoras?"
    - "¿Cuánto cuesta un compresor?"
    - "¿En qué ubicaciones entregan?"
    - "¿Qué modelos de generadores manejan?"
    - "¿Tienen inventario disponible?"
    - "¿Pueden cotizar una torre de iluminación?"
    
    EJEMPLOS DE NO INVENTARIO:
    - "me llamo Juan"
    - "quiero un compresor"
    - "es para venta"
    - "mi empresa se llama ABC"
    
    Mensaje del usuario: {message}
    
    Responde SOLO con "true" si es pregunta sobre inventario, o "false" si no lo es.
    """
)
