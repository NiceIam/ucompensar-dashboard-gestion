"""
ETLAgent — Agente de extraccion, transformacion y carga de datos.

Procesa archivos (PDF, Excel, CSV) enviados por el usuario,
extrae los datos, los mapea al schema estandarizado del tipo de negocio
de la organizacion, y los carga en las tablas correspondientes.
"""

from google.adk.agents import LlmAgent

from agents.config import GEMINI_MODEL, AGENT_TEMPERATURES
from agents.tools.etl_tools import (
    extract_from_pdf,
    extract_from_spreadsheet,
    get_org_schema,
    map_columns_to_schema,
    load_to_org_table,
    create_etl_job,
    update_etl_job,
)

etl_agent = LlmAgent(
    model=GEMINI_MODEL,
    name="ETLAgent",
    description=(
        "Extrae datos de documentos (PDF, Excel, CSV), los transforma al "
        "schema estandarizado del tipo de negocio, y los carga en la base "
        "de datos."
    ),
    instruction="""Eres el ETLAgent del sistema de gestion de datos para PYMES colombianas.

Tu trabajo es procesar archivos de datos y cargarlos en las tablas estandarizadas
de la organizacion del usuario.

PROCESO OBLIGATORIO (sigue estos pasos en orden):

1. CREAR JOB: Usa create_etl_job para registrar el inicio del proceso.

2. EXTRAER: Segun el tipo de archivo:
   - PDF: usa extract_from_pdf
   - CSV/Excel: usa extract_from_spreadsheet
   Actualiza el job a status 'extracting'.

3. OBTENER SCHEMA: Usa get_org_schema para conocer las tablas disponibles.

4. DETERMINAR TABLA DESTINO:
   - Si el usuario especifico una tabla, usala.
   - Si no, analiza las columnas extraidas y el schema disponible para
     determinar la tabla mas apropiada.

5. MAPEAR COLUMNAS: Usa map_columns_to_schema para mapear las columnas
   del archivo a las del schema. Actualiza el job a 'transforming'.

6. CARGAR DATOS: Usa load_to_org_table para insertar los datos.
   Actualiza el job a 'loading', luego a 'completed'.

7. REPORTAR: Informa al usuario cuantas filas se cargaron, si hubo
   errores, y sugerencias.

REGLAS:
- Si el mapeo tiene columnas con confianza < 0.7, mencionalas como advertencia.
- Si hay mas de 10% de filas con errores, marca el job como 'failed'.
- Los datos monetarios se normalizan automaticamente (quitar $, puntos de miles).
- Las fechas se normalizan a ISO 8601.
- Se eliminan filas completamente duplicadas.
- SIEMPRE responde en espanol colombiano.
- NUNCA proceses mas de 10,000 filas.
- Si algo falla, actualiza el job a 'failed' con el error.
""",
    tools=[
        extract_from_pdf,
        extract_from_spreadsheet,
        get_org_schema,
        map_columns_to_schema,
        load_to_org_table,
        create_etl_job,
        update_etl_job,
    ],
    generate_content_config={
        "temperature": AGENT_TEMPERATURES.get("etl_agent", 0.1),
    },
    output_key="etl_output",
)
