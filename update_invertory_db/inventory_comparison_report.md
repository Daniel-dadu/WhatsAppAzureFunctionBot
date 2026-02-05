# Inventory Comparison Report

**Generated:** 2026-02-04  
**Local inventory:** `inventory_data.py` (57 machines)  
**SQL inventory:** `prices_inventory.txt` (50 products)

---

## Summary

| Status | Count |
|--------|-------|
| ✅ **Matched in both** | 30 machines |
| ⚠️ **Only in local inventory** | 27 machines |
| 🆕 **Only in SQL database** | 20 products |

---

## ✅ Machines Found in BOTH Inventories (30)

### Apisonador
| Local (inventory_data.py) | SQL (prices_inventory.txt) | Stock |
|---------------------------|---------------------------|-------|
| Sakai RS75 | RS75 - APISONADOR RS75 MARCA SAKAI | 17 |

### Compresor (7 matches)
| Local | SQL Code | Stock |
|-------|----------|-------|
| AIRMAN SAS22RD6E | SAS22RD6E | 1 |
| AIRMAN SAS37RD6E | SAS37RD6E | 2 |
| AIRMAN SAS4SD6C | SAS4SD6C | 2 |
| AIRMAN SAS55RD6E | SAS55RD6E | 2 |
| AIRMAN SAS75RD6E | SAS75RD6E | 2 |
| AIRMAN SAS8SD6C | SAS8SD6C | 1 |
| AIRMAN PDS750S-4B1 | PDS750S4B1 | 3 |

### Rompedor / Martillo Neumático (3 matches)
| Local | SQL Code | Stock |
|-------|----------|-------|
| Toku TCB-300 | TCB300 | 1 |
| Toku TPB-60 | TPB60 | 84 |
| Toku TPB-90 | TPB90 | 3 |

### Motobomba (2 matches)
| Local | SQL Code | Stock |
|-------|----------|-------|
| Koshin KTY-100D | KTY100D | 21 |
| Koshin KTH-100 X → **Close match:** KTH100XBAF | KTH100XBAF | 12 |

### Generador (6 matches)
| Local | SQL Code | Stock |
|-------|----------|-------|
| Shindaiwa DGM250MK-D | DGM250MKD | 6 |
| Shindaiwa DGM450MK-D | DGM450MKD | 27 |
| Shindaiwa DGM600MK-D | DGM600MKD | 7 |
| AIRMAN SDG150S → **Close match:** SDG150S3A6 | SDG150S3A6 | 3 |
| Koshin GV-5500s | GV5500S | 56 |
| Koshin GV-8000S | GV8000S | 11 |

### Montacargas (1 match)
| Local | SQL Code | Stock |
|-------|----------|-------|
| LGMG CPD30 | CPD30 | 2 |

### Manipulador (1 match)
| Local | SQL Code | Stock |
|-------|----------|-------|
| LGMG H1840 | H1840 | 1 |

### Plataforma (6 matches)
| Local | SQL Code | Stock |
|-------|----------|-------|
| LGMG A45JE-LI | A45JELI | 4 |
| LGMG AR52J | AR52J | 2 |
| LGMG AR60J-2 | AR60J-2 | 1 |
| LGMG AR60JE-2 | AR60JE-2 | 1 |
| LGMG S2632E II | S2632EII | 1 |
| LGMG S4046E II | S4046EII | 2 |
| LGMG SS1230E | SS1230E | 4 |

### Cortadora de Varillas (1 match)
| Local | SQL Code | Stock |
|-------|----------|-------|
| Simpedil C54 EVO | C54TTF05 | 21 |

### Dobladora de Varillas (1 match)
| Local | SQL Code | Stock |
|-------|----------|-------|
| Simpedil P54 EVO | P54TTF06 | 22 |

### Soldadora (1 match)
| Local | SQL Code | Stock |
|-------|----------|-------|
| Shindaiwa DGW400DMK | DGW400DMKD | 27 |

---

## ⚠️ Machines ONLY in Local Inventory (27)

These machines exist in `inventory_data.py` but are **NOT** in the SQL database.

### Soldadora (3)
- Shindaiwa DGW500DM
- Shindaiwa EGW185MS
- Shindaiwa DGW340DM

### Compresor (9)
- AIRMAN SAS75VD-E
- AIRMAN SAS55VD-E
- AIRMAN SAS37VD-E
- AIRMAN SAS15RD6E
- AIRMAN PDSF830S
- AIRMAN PDSG750VRS-4C5
- AIRMAN PDS400S
- AIRMAN PDSF375S-DP
- AIRMAN PDS185S-6C2

### Generador (2)
- Shindaiwa DGM150BMK
- AIRMAN SDG100S

### Plataforma (8)
- LGMG A30JE
- LGMG SS1932E
- LGMG S3246E II
- LGMG S4650EII
- LGMG AR65J
- LGMG AR65JE-LI

### Torre de Iluminación (3)
- Shindaiwa SL433IDG-B/S1W
- Trime X-SOLAR 4x65W
- Trime X-START

### Montacargas (1)
- LGMG CPD25

### Manipulador (2)
- LGMG H625
- LGMG H735



---

## 🆕 Products ONLY in SQL Database (20)

These products exist in SQL but are **NOT** in `inventory_data.py`.

### Compresor Neumático (1)
| Code | Product | Stock |
|------|---------|-------|
| PDS390SD4B | COMPRESOR MODELO PDS390SD4B MARCA AIRMAN | 1 |

### Compresor Eléctrico (3)
| Code | Product | Stock |
|------|---------|-------|
| SAS15RD6C | COMPRESOR ESTACIONARIO SAS15RD6C | 1 |
| SMS37ERD6E | COMPRESOR ESTACIONARIO SMS37RD6E REGULATOR TYPE | 1 |
| SMS75ERD6E | COMPRESOR ESTACIONARIO SMS75RD6E REGULATOR TYPE | 1 |

### Dobladora de Varilla (1)
| Code | Product | Stock |
|------|---------|-------|
| GW50A-4 | DOBLADORA DE VARILLA GW50A4 MARCA ALPHA C | 1 |

### Generador (1)
| Code | Product | Stock |
|------|---------|-------|
| DG100MI400 | GENERADOR DG100MI-400 MARCA SHINDAIWA | 6 |

### Soldadora Diesel (1)
| Code | Product | Stock |
|------|---------|-------|
| DGW400DMC | SOLDADORA DGW400DMC MARCA SHINDAIWA | 1 |

### Plataforma Articulada (2 new variations)
| Code | Product | Stock |
|------|---------|-------|
| AR52J-2 | PLATAFORMA ARTICULADA AR52J-2 | 3 |
| AR60J | PLATAFORMA ARTICULADA AR60J | 1 |

### Plataforma de Mástil (1 - NEW CATEGORY)
| Code | Product | Stock |
|------|---------|-------|
| M2640JE | PLATAFORMA DE MASTIL M2640JE | 1 |

### Plataforma Personal (2 - NEW CATEGORY)
| Code | Product | Stock |
|------|---------|-------|
| MP0607SE | PLATAFORMA DE MASTIL MP0607SE | 1 |
| MP1208SE | PLATAFORMA DE MASTIL MP1208SE | 4 |

### Plataforma Tijera (7 new variations)
| Code | Product | Stock |
|------|---------|-------|
| S1932E-2 | PLATAFORMA DE TIJERA S1932E-2 | 1 |
| S1932EII | PLATAFORMA DE TIJERA S1932EII | 1 |
| S2632E-2 | PLATAFORMA DE TIJERA S2632E-2 | 1 |
| S2632EIILI | PLATAFORMA DE TIJERA S2632EIILI | 3 |
| S4046E-2 | PLATAFORMA DE TIJERA S4046E-2 | 1 |
| S4650EIILI | PLATAFORMA DE TIJERA S4650EIILI | 7 |

---

## Key Observations

1. **Missing categories in SQL**: Torre de Iluminación is completely absent from the SQL inventory

2. **New categories in SQL**: 
   - Plataforma de Mástil
   - Plataforma Personal

3. **Model naming discrepancies**: SQL uses codes like `DGM250MKD` while local uses `DGM250MK-D`

4. **Cortadora/Dobladora**: SQL has different product codes (C54TTF05, P54TTF06) than local model names (C54 EVO, P54 EVO)

5. **Soldadoras**: None of the 4 local soldadoras match exactly with SQL (SQL has DGW400DMC, DGW400DMKD variations)

6. **Platformas**: Many version variations (-2, II, IILI, LI suffixes) create confusion between old and new versions
