"""
Datos iniciales de configuración de maquinaria
"""

machinery_configurations = [
    {
        "type_id": "soldadora",
        "name": "Soldadora",
        "fields": [
            {
                "name": "amperaje",
                "question": "¿cuál es el amperaje que necesitas?",
                "reason": "Para recomendarte el modelo adecuado según tu trabajo",
                "type": "number",
                "unit": "amps",
                "comparison_operator": "gte"
            },
            {
                "name": "tipo_alimentacion",
                "question": "¿cuál es el tipo de alimentación que necesitas: eléctrica o combustible?",
                "reason": "Para recomendarte el modelo adecuado según tu trabajo",
                "type": "selection",
                "comparison_operator": "eq"
            }
        ]
    },
    {
        "type_id": "compresor",
        "name": "Compresor",
        "fields": [
            {
                "name": "cfm_requerido",
                "question": "¿cuánto volumen de aire en CFM necesitas?",
                "reason": "Para seleccionar la potencia correcta",
                "type": "number", 
                "unit": "CFM",
                "comparison_operator": "gte"
            },
            {
                "name": "psi_requerido",
                "question": "¿cuánto presión en PSI necesitas?",
                "reason": "Para seleccionar la potencia correcta",
                "type": "number", 
                "unit": "PSI",
                "comparison_operator": "gte"
            },
        ]
    },
    {
        "type_id": "rompedor",
        "name": "Rompedor",
        "fields": []
    },
    {
        "type_id": "motobomba",
        "name": "Motobomba",
        "fields": []
    },
    {
        "type_id": "apisonador",
        "name": "Apisonador",
        "fields": []
    },
    {
        "type_id": "generador",
        "name": "Generador",
        "fields": [
            {
                "name": "tipo_generador",
                "question": "¿cuál es el tipo de generador que requiere: estacionario o portátil?",
                "reason": "Para seleccionar el generador correcto",
                "type": "selection",
                "comparison_operator": "eq"
            },
            {
                "name": "potencia",
                "question": "¿cuál es la potencia del generador que requiere en kW?", # Poner los KW que ellos ya manejan
                "reason": "Para seleccionar el generador correcto",
                "type": "number",
                "unit": "kW",
                "comparison_operator": "gte"
            }
        ]
    },
    {
        "type_id": "cortadora_varillas",
        "name": "Cortadora de Varilla",
        "fields": []
    },
    {
        "type_id": "dobladora_varillas",
        "name": "Dobladora de Varilla",
        "fields": []
    },
    {
        "type_id": "torre_iluminacion",
        "name": "Torre de Iluminación",
        "fields": [
            {
                "name": "es_led",
                "question": "¿prefieres iluminación LED?",
                "reason": "Para determinar el tipo de iluminación necesario",
                "type": "boolean",
                "comparison_operator": "eq"
            }
        ]
    },
    {
        "type_id": "montacargas",
        "name": "Montacargas",
        "fields": [
            {
                "name": "capacidad_carga",
                "question": "¿qué peso requiere levantar?",
                "reason": "Para determinar la capacidad necesaria",
                "type": "number",
                "unit": "kg",
                "comparison_operator": "gte"
            }
        ]
    },
    {
        "type_id": "plataforma",
        "name": "Plataforma",
        "fields": [
            {
                "name": "tipo_plataforma",
                "question": "¿cuál es el tipo de plataforma que necesitas: articulada o de tijera?",
                "reason": "Para seleccionar la plataforma correcta",
                "type": "selection",
                "comparison_operator": "contains"
            },
            {
                "name": "altura_trabajo",
                "question": "¿cuál es la altura de trabajo que necesitas?",
                "reason": "Para asegurar que la máquina alcance la altura necesaria",
                "type": "number",
                "unit": "m",
                "comparison_operator": "gte"
            },
            {
                "name": "altura_plataforma",
                "question": "¿cuál es la altura de la plataforma que necesitas?",
                "reason": "Para asegurar que la máquina alcance la altura necesaria",
                "type": "number",
                "unit": "m",
                "comparison_operator": "gte"
            },
            {
                "name": "tipo_alimentacion",
                "question": "¿cuál es el tipo de alimentación que necesitas?",
                "reason": "Para asegurar el tipo de alimentación",
                "type": "selection",
                "comparison_operator": "eq"
            }
        ]
    },
    {
        "type_id": "manipulador",
        "name": "Manipulador Telescópico",
        "fields": [
            {
                "name": "altura",
                "question": "¿qué altura necesita?",
                "reason": "Para determinar la altura necesaria",
                "type": "number",
                "unit": "m",
                "comparison_operator": "gte"
            },
            {
                "name": "capacidad",
                "question": "¿qué peso requiere mover?",
                "reason": "Para determinar la capacidad necesaria",
                "type": "number",
                "unit": "kg",
                "comparison_operator": "gte"
            }
        ]
    }
]
