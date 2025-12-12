inventario = [
   # SOLDADORA
    {"modelo": "Shindaiwa DGW500DM", "categoria": "soldadora", "amperaje": "30-500 AMP", "tipo_alimentacion": "combustible", "tipo_soldadora": "moto soldadora", "diametro_varilla": "3/8", "tipo_trabajo": "electrodo"},
    {"modelo": "Shindaiwa EGW185MS", "categoria": "soldadora", "amperaje": "45-185 AMP", "tipo_alimentacion": "combustible", "tipo_soldadora": "moto soldadora", "diametro_varilla": "5/32", "tipo_trabajo": "electrodo"},
    {"modelo": "Shindaiwa DGW400DMK", "categoria": "soldadora", "amperaje": "50-390 AMP", "tipo_alimentacion": "combustible", "tipo_soldadora": "moto soldadora", "diametro_varilla": "5/16", "tipo_trabajo": "electrodo, micro alambre, TIG, arcayeo"},
    {"modelo": "Shindaiwa DGW340DM", "categoria": "soldadora", "amperaje": "55-340 AMP", "tipo_alimentacion": "combustible", "tipo_soldadora": "moto soldadora", "diametro_varilla": "5/16", "tipo_trabajo": "electrodo, arcayeo"},

    # COMPRESORES
    {"modelo": "AIRMAN SAS75VD-E", "categoria": "compresor", "tipo_compresor": "eléctrico", "cfm": "501.47", "psi": "100"},
    {"modelo": "AIRMAN SAS55VD-E", "categoria": "compresor", "tipo_compresor": "eléctrico", "cfm": "367.27", "psi": "100"},
    {"modelo": "AIRMAN SAS37VD-E", "categoria": "compresor", "tipo_compresor": "eléctrico", "cfm": "247.2", "psi": "100"},
    {"modelo": "AIRMAN SAS75RD6E", "categoria": "compresor", "tipo_compresor": "eléctrico", "cfm": "490.87", "psi": "100"},
    {"modelo": "AIRMAN SAS55RD6E", "categoria": "compresor", "tipo_compresor": "eléctrico", "cfm": "360.21", "psi": "100"},
    {"modelo": "AIRMAN SAS37RD6E", "categoria": "compresor", "tipo_compresor": "eléctrico", "cfm": "243.67", "psi": "100"},
    {"modelo": "AIRMAN SAS22RD6E", "categoria": "compresor", "tipo_compresor": "eléctrico", "cfm": "144.79", "psi": "100"},
    {"modelo": "AIRMAN SAS15RD6E", "categoria": "compresor", "tipo_compresor": "eléctrico", "cfm": "93.58", "psi": "100"},
    {"modelo": "AIRMAN SAS8SD6C", "categoria": "compresor", "tipo_compresor": "eléctrico", "cfm": "35.31", "psi": "135"},
    {"modelo": "AIRMAN SAS4SD6C", "categoria": "compresor", "tipo_compresor": "eléctrico", "cfm": "15.53", "psi": "120"},
    {"modelo": "AIRMAN PDSF830S", "categoria": "compresor", "tipo_compresor": "portatil", "cfm": "830", "psi": "150"},
    {"modelo": "AIRMAN PDSG750VRS-4C5", "categoria": "compresor", "tipo_compresor": "portatil", "cfm": "750-900", "psi": "200"},
    {"modelo": "AIRMAN PDS750S-4B1", "categoria": "compresor", "tipo_compresor": "portatil", "cfm": "750", "psi": "100"},
    {"modelo": "AIRMAN PDS400S", "categoria": "compresor", "tipo_compresor": "portatil", "cfm": "400", "psi": "100"},
    {"modelo": "AIRMAN PDSF375S-DP", "categoria": "compresor", "tipo_compresor": "portatil", "cfm": "375", "psi": "100/150"},
    {"modelo": "AIRMAN PDS185S-6C2", "categoria": "compresor", "tipo_compresor": "portatil", "cfm": "185", "psi": "100"},

    # ROMPEDOR
    {"modelo": "Toku TCB-300", "categoria": "rompedor", "tipo_alimentacion": "neumatico", "peso": "30 kg"},
    {"modelo": "Toku TPB-60", "categoria": "rompedor", "tipo_alimentacion": "neumatico", "peso": "30 kg"},
    {"modelo": "Toku TPB-90", "categoria": "rompedor", "tipo_alimentacion": "neumatico", "peso": "42 kg"},

    # MOTOBOMBAS
    {"modelo": "Koshin KTY-100D", "categoria": "motobomba", "diametro_salida": "4 pulgadas", "tipo_combustible": "diésel"},
    {"modelo": "Koshin KTH-100 X", "categoria": "motobomba", "diametro_salida": "4 pulgadas", "tipo_combustible": "gasolina"},

    # APISONADOR
    {"modelo": "Sakai RS75", "categoria": "apisonador", "motor": "Honda GXR120", "ancho_zapata": "395 mm"},

    # GENERADOR
    {"modelo": "Shindaiwa DGM150BMK", "categoria": "generador", "tipo_generador": "estacionario", "potencia": "15 kVA", "tipo_alimentacion": "diésel"},
    {"modelo": "Shindaiwa DGM250MK-D", "categoria": "generador", "tipo_generador": "estacionario", "potencia": "25 kVA", "tipo_alimentacion": "diésel"},
    {"modelo": "Shindaiwa DGM450MK-D", "categoria": "generador", "tipo_generador": "estacionario", "potencia": "45 kVA", "tipo_alimentacion": "diésel"},
    {"modelo": "Shindaiwa DGM600MK-D", "categoria": "generador", "tipo_generador": "estacionario", "potencia": "60 kVA", "tipo_alimentacion": "diésel"},
    {"modelo": "AIRMAN SDG150S", "categoria": "generador", "tipo_generador": "estacionario", "potencia": "150 kVA", "tipo_alimentacion": "diésel"},
    {"modelo": "AIRMAN SDG100S", "categoria": "generador", "tipo_generador": "estacionario", "potencia": "100 kVA", "tipo_alimentacion": "diésel"},
    {"modelo": "Koshin GV-8000S", "categoria": "generador", "tipo_generador": "portatil", "potencia": "7.2 kW", "tipo_alimentacion": "gasolina"},
    {"modelo": "Koshin GV-5500s", "categoria": "generador", "tipo_generador": "portatil", "potencia": "5.5 kVA", "tipo_alimentacion": "gasolina"},

    # CORTADOR DE VARILLAS
    {"modelo": "Simpedil C54 EVO", "categoria": "cortador_varillas", "tipo_alimentacion": "Eléctrica", "diametro_maximo_varilla": "1.75 pulgadas", "cortes_por_minuto": 37},

    # DOBLADOR DE VARILLAS
    {"modelo": "Simpedil P54 EVO", "categoria": "doblador_varillas", "tipo_alimentacion": "Eléctrica", "diametro_maximo_varilla": "1.75 pulgadas", "cortes_por_minuto": 6},

    # TORRE DE ILUMINACIÓN
    {
      "modelo": "Shindaiwa SL433IDG-B/S1W",
      "categoria": "torre_iluminacion",
      "tipo_reflector": "LED",
      "consumo_combustible": "15.5 l",
      "remolcable": "Sí"
    },
    {
      "modelo": "Trime X-SOLAR 4x65W",
      "categoria": "torre_iluminacion",
      "tipo_reflector": "LED",
      "consumo_combustible": "0",
      "remolcable": "Sí"
    },
    {
      "modelo": "Trime X-START",
      "categoria": "torre_iluminacion",
      "tipo_reflector": "LED",
      "consumo_combustible": "0.55 L/h",
      "remolcable": "Sí"
    },

    # MONTACARCAS
    {
    "modelo": "LGMG CPD30",
    "categoria": "montacarcas",
    "capacidad_carga": "3000 kg",
    "altura_maxima": "4.5 m",
    "tipo_alimentacion": "Eléctrica"
   },
   {
      "modelo": "LGMG CPD25",
      "categoria": "montacarcas",
      "capacidad_carga": "2500 kg",
      "altura_maxima": "4.5 m",
      "tipo_alimentacion": "Eléctrica"
   },

    # PLATAFORMAS
    {"modelo": "LGMG AR60JE-2", "categoria": "plataforma", "tipo_plataforma": "articulada", "altura_trabajo": "20.12 m", "altura_plataforma": "18.12 m", "tipo_alimentacion": "electrica"},
    {"modelo": "LGMG AR60J-2", "categoria": "plataforma", "tipo_plataforma": "articulada", "altura_trabajo": "20.12 m", "altura_plataforma": "18.12 m", "tipo_alimentacion": "combustible"},
    {"modelo": "LGMG AR65J", "categoria": "plataforma", "tipo_plataforma": "articulada", "altura_trabajo": "21.58 m", "altura_plataforma": "19.58 m", "tipo_alimentacion": "combustible"},
    {"modelo": "LGMG AR65JE-LI", "categoria": "plataforma", "tipo_plataforma": "articulada", "altura_trabajo": "21.58 m", "altura_plataforma": "19.58 m", "tipo_alimentacion": "electrica"},
    {"modelo": "LGMG AR52J", "categoria": "plataforma", "tipo_plataforma": "articulada", "altura_trabajo": "17.70 m", "altura_plataforma": "15.7 m", "tipo_alimentacion": "combustible"},
    {"modelo": "LGMG A45JE-LI", "categoria": "plataforma", "tipo_plataforma": "articulada", "altura_trabajo": "16.09 m", "altura_plataforma": "14.09 m", "tipo_alimentacion": "electrica"},
    {"modelo": "LGMG A30JE", "categoria": "plataforma", "tipo_plataforma": "articulada", "altura_trabajo": "11 m", "altura_plataforma": "9 m", "tipo_alimentacion": "electrica"},
    {"modelo": "LGMG SS1230E", "categoria": "plataforma", "tipo_plataforma": "tijera", "altura_trabajo": "5.6 m", "altura_plataforma": "3.6 m", "tipo_alimentacion": "electrica"},
    {"modelo": "LGMG SS1932E", "categoria": "plataforma", "tipo_plataforma": "tijera", "altura_trabajo": "7.5 m", "altura_plataforma": "5.5 m", "tipo_alimentacion": "electrica"},
    {"modelo": "LGMG S2632E II", "categoria": "plataforma", "tipo_plataforma": "tijera", "altura_trabajo": "10 m", "altura_plataforma": "8 m", "tipo_alimentacion": "electrica"},
    {"modelo": "LGMG S3246E II", "categoria": "plataforma", "tipo_plataforma": "tijera", "altura_trabajo": "12 m", "altura_plataforma": "10 m", "tipo_alimentacion": "electrica"},
    {"modelo": "LGMG S4046E II", "categoria": "plataforma", "tipo_plataforma": "tijera", "altura_trabajo": "14 m", "altura_plataforma": "12 m", "tipo_alimentacion": "electrica"},
    {"modelo": "LGMG S4650EII", "categoria": "plataforma", "tipo_plataforma": "tijera", "altura_trabajo": "15.8 m", "altura_plataforma": "13.8 m", "tipo_alimentacion": "electrica"},

    # MANIPULADORES
    {"modelo": "LGMG H625", "categoria": "manipulador", "altura_maxima": "5.94 m", "capacidad_carga": "2500 kg"},
    {"modelo": "LGMG H735", "categoria": "manipulador", "altura_maxima": "7 m", "capacidad_carga": "3500 kg"},
    {"modelo": "LGMG H1840", "categoria": "manipulador", "altura_maxima": "17.5 m", "capacidad_carga": "4000 kg"},
]