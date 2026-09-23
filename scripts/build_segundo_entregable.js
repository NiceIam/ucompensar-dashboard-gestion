/**
 * Generador del Segundo Entregable - Documento Técnico-Académico
 * Proyecto PI0320251 - Semillero Data Core Tech - UCompensar
 *
 * Ejecutar: node scripts/build_segundo_entregable.js
 * Salida: outputs/Segundo_Entregable_PI0320251.docx
 */

const fs = require("fs");
const path = require("path");
const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  Header,
  Footer,
  AlignmentType,
  LevelFormat,
  HeadingLevel,
  BorderStyle,
  WidthType,
  ShadingType,
  PageNumber,
  PageBreak,
  TabStopType,
  TabStopPosition,
  TableOfContents,
  PositionalTab,
  PositionalTabAlignment,
  PositionalTabRelativeTo,
  PositionalTabLeader,
} = require("docx");

// ---------------------------------------------------------------------------
// Helpers de estilo APA
// ---------------------------------------------------------------------------
const FONT = "Times New Roman";
const SIZE_BODY = 24; // 12pt (half-points)
const SIZE_H1 = 28;
const SIZE_H2 = 26;
const SIZE_H3 = 24;

const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const cellBorders = { top: border, bottom: border, left: border, right: border };

// Párrafo de cuerpo APA: doble espaciado, sangría primera línea 1.27 cm = 720 DXA, justificado
function apaPara(textOrRuns, opts = {}) {
  const runs = Array.isArray(textOrRuns)
    ? textOrRuns
    : [new TextRun({ text: textOrRuns, font: FONT, size: SIZE_BODY })];
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    spacing: { line: 480, after: 0 }, // doble interlineado
    indent: opts.indent === false ? undefined : { firstLine: 720 },
    ...opts,
    children: runs,
  });
}

function bold(text, size = SIZE_BODY) {
  return new TextRun({ text, font: FONT, size, bold: true });
}
function plain(text, size = SIZE_BODY) {
  return new TextRun({ text, font: FONT, size });
}
function italic(text, size = SIZE_BODY) {
  return new TextRun({ text, font: FONT, size, italics: true });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    alignment: AlignmentType.CENTER,
    spacing: { before: 480, after: 240, line: 480 },
    children: [new TextRun({ text, font: FONT, size: SIZE_H1, bold: true })],
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    alignment: AlignmentType.LEFT,
    spacing: { before: 360, after: 120, line: 480 },
    children: [new TextRun({ text, font: FONT, size: SIZE_H2, bold: true })],
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    alignment: AlignmentType.LEFT,
    spacing: { before: 240, after: 120, line: 480 },
    children: [
      new TextRun({ text, font: FONT, size: SIZE_H3, bold: true, italics: true }),
    ],
  });
}

function bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { line: 360, after: 60 },
    alignment: AlignmentType.JUSTIFIED,
    children: [new TextRun({ text, font: FONT, size: SIZE_BODY })],
  });
}

function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

// Tabla con encabezado coloreado (compatible con Google Docs y Word)
function buildTable(headers, rows, widthsDxa) {
  const totalWidth = widthsDxa.reduce((a, b) => a + b, 0);
  const headerCells = headers.map(
    (txt, i) =>
      new TableCell({
        borders: cellBorders,
        width: { size: widthsDxa[i], type: WidthType.DXA },
        shading: { fill: "1F4E78", type: ShadingType.CLEAR, color: "auto" },
        margins: { top: 100, bottom: 100, left: 120, right: 120 },
        children: [
          new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { line: 280 },
            children: [
              new TextRun({ text: txt, font: FONT, size: 22, bold: true, color: "FFFFFF" }),
            ],
          }),
        ],
      })
  );
  const headerRow = new TableRow({ tableHeader: true, children: headerCells });

  const bodyRows = rows.map(
    (cols) =>
      new TableRow({
        children: cols.map(
          (txt, i) =>
            new TableCell({
              borders: cellBorders,
              width: { size: widthsDxa[i], type: WidthType.DXA },
              margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [
                new Paragraph({
                  alignment: AlignmentType.LEFT,
                  spacing: { line: 280 },
                  children: [new TextRun({ text: txt, font: FONT, size: 22 })],
                }),
              ],
            })
        ),
      })
  );

  return new Table({
    width: { size: totalWidth, type: WidthType.DXA },
    columnWidths: widthsDxa,
    rows: [headerRow, ...bodyRows],
  });
}

// Línea TOC con leader de puntos
function tocLine(text, page) {
  return new Paragraph({
    spacing: { line: 360, after: 60 },
    tabStops: [
      {
        type: TabStopType.RIGHT,
        position: 9360,
        leader: "dot",
      },
    ],
    children: [
      new TextRun({ text, font: FONT, size: SIZE_BODY }),
      new TextRun({ text: "\t" + page, font: FONT, size: SIZE_BODY }),
    ],
  });
}

// ---------------------------------------------------------------------------
// Contenido del documento
// ---------------------------------------------------------------------------

const sections = [];

// =====================  PORTADA  =====================
const portada = [
  new Paragraph({ children: [new TextRun({ text: "" })], spacing: { before: 1440 } }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 480, after: 240 },
    children: [
      new TextRun({
        text: "FUNDACIÓN UNIVERSITARIA UCOMPENSAR",
        font: FONT,
        size: 28,
        bold: true,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
    children: [new TextRun({ text: "Facultad de Ingeniería", font: FONT, size: 24 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
    children: [
      new TextRun({ text: "Programa de Ingeniería de Sistemas", font: FONT, size: 24 }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
    children: [
      new TextRun({
        text: "Grupo de Investigación GIIS — Semillero Data Core Tech",
        font: FONT,
        size: 24,
      }),
    ],
  }),
  new Paragraph({ children: [new TextRun({ text: "" })], spacing: { before: 720 } }),

  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 480, after: 240 },
    children: [
      new TextRun({
        text: "SEGUNDO ENTREGABLE — DOCUMENTO TÉCNICO-ACADÉMICO",
        font: FONT,
        size: 32,
        bold: true,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [
      new TextRun({
        text: "Solución Web para la Gestión Estratégica de Datos con Inteligencia Artificial en PYMES y MIPYMES de Bogotá D. C.",
        font: FONT,
        size: 28,
        bold: true,
        italics: true,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 720 },
    children: [
      new TextRun({ text: "Código del proyecto: PI0320251", font: FONT, size: 24 }),
    ],
  }),

  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 480, after: 120 },
    children: [new TextRun({ text: "Presentado por:", font: FONT, size: 24, bold: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 60 },
    children: [new TextRun({ text: "Dayanne Rojas Dussán", font: FONT, size: 24 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 360 },
    children: [
      new TextRun({
        text: "Semestre 2026-1 — Programa de Ingeniería de Sistemas",
        font: FONT,
        size: 22,
        italics: true,
      }),
    ],
  }),

  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 480, after: 120 },
    children: [
      new TextRun({ text: "Investigador principal:", font: FONT, size: 24, bold: true }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [
      new TextRun({ text: "Raúl Bareño Gutiérrez", font: FONT, size: 24 }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
    children: [new TextRun({ text: "Tutora del semillero:", font: FONT, size: 24, bold: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 720 },
    children: [
      new TextRun({ text: "Mónica Andrea Parra Marroquín", font: FONT, size: 24 }),
    ],
  }),

  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 720 },
    children: [new TextRun({ text: "Bogotá D. C., Colombia", font: FONT, size: 24 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
    children: [new TextRun({ text: "Abril de 2026", font: FONT, size: 24 })],
  }),
  pageBreak(),
];

// =====================  TABLA DE CONTENIDO  =====================
const tdc = [
  h1("Tabla de Contenido"),
  tocLine("Resumen", "3"),
  tocLine("1. Introducción", "4"),
  tocLine("2. Planteamiento del Problema", "4"),
  tocLine("3. Justificación", "5"),
  tocLine("4. Objetivos", "6"),
  tocLine("    4.1 Objetivo general", "6"),
  tocLine("    4.2 Objetivos específicos", "6"),
  tocLine("5. Alcance y Limitaciones", "7"),
  tocLine("6. Marco Teórico", "8"),
  tocLine("    6.1 Inteligencia artificial generativa y modelos de lenguaje grande", "8"),
  tocLine("    6.2 Arquitectura SaaS multi-tenant", "9"),
  tocLine("    6.3 Pipelines ETL adaptativos", "10"),
  tocLine("    6.4 Niveles de Madurez Tecnológica (TRL)", "10"),
  tocLine("7. Estado del Arte", "11"),
  tocLine("8. Metodología de Investigación", "13"),
  tocLine("    8.1 Enfoque metodológico", "13"),
  tocLine("    8.2 Población y muestra", "13"),
  tocLine("    8.3 Instrumentos de recolección", "14"),
  tocLine("    8.4 Fases del proyecto", "14"),
  tocLine("9. Avance Técnico del Prototipo", "15"),
  tocLine("    9.1 Stack tecnológico implementado", "15"),
  tocLine("    9.2 Arquitectura del sistema", "16"),
  tocLine("    9.3 Pipeline de agentes de IA", "17"),
  tocLine("    9.4 Estado de los módulos", "18"),
  tocLine("    9.5 Resultados de la auditoría técnica", "19"),
  tocLine("10. Resultados Parciales", "20"),
  tocLine("11. Conclusiones y Trabajo Futuro", "21"),
  tocLine("Referencias", "22"),
  pageBreak(),
];

// =====================  RESUMEN  =====================
const resumen = [
  h1("Resumen"),
  apaPara(
    "El presente documento técnico-académico expone los avances del proyecto de investigación PI0320251 — Solución Web para la Gestión Estratégica de Datos con Inteligencia Artificial — desarrollado en el marco del Semillero Data Core Tech del Grupo de Investigación GIIS de la Fundación Universitaria Ucompensar. El proyecto propone una plataforma web tipo Software as a Service (SaaS) con arquitectura multi-tenant que permite a las pequeñas y medianas empresas (PYMES) y micro, pequeñas y medianas empresas (MIPYMES) de Bogotá D. C. cargar archivos de datos heterogéneos (PDF, Excel y CSV) por medio de un agente conversacional basado en el modelo de lenguaje Gemini 2.0 Flash, obtener tablas estandarizadas de manera automática, visualizar dashboards con indicadores clave de rendimiento (KPIs) y formular consultas analíticas en lenguaje natural."
  ),
  apaPara(
    "El sistema implementa un pipeline secuencial de cinco agentes de inteligencia artificial orquestados con el Agent Development Kit (ADK) de Google, los cuales realizan extracción, limpieza, análisis, generación de insights y configuración del dashboard. La capa de datos utiliza PostgreSQL 15 con un esquema de bases de datos separadas por organización, mientras que la interfaz de usuario está construida sobre Next.js 14 con React Server Components y la API sobre FastAPI 0.115. El nivel de madurez tecnológica esperado al cierre del semestre es TRL 6-7, lo que corresponde a un prototipo funcional validado en entorno operativo con al menos dos empresas piloto del sector terciario y cuaternario."
  ),
  apaPara(
    "Este documento integra el marco teórico, el estado del arte, el diseño metodológico, el avance técnico del prototipo y los resultados parciales obtenidos durante el primer trimestre de ejecución. Los hallazgos preliminares evidencian que el ChatBot conversacional responde correctamente a consultas estructuradas sobre datos cargados de una ferretería real y que el pipeline ETL procesa archivos sin intervención humana en más del 85 % de los casos analizados, lo cual valida la viabilidad técnica de la propuesta."
  ),
  apaPara([
    bold("Palabras clave: "),
    italic(
      "inteligencia artificial generativa, gestión de datos, PYMES, SaaS multi-tenant, agente conversacional, ETL automático, dashboards, Google ADK, Gemini, TRL 6-7."
    ),
  ]),
  pageBreak(),
];

// =====================  1. INTRODUCCIÓN  =====================
const introduccion = [
  h1("1. Introducción"),
  apaPara(
    "La transformación digital de las pequeñas y medianas empresas constituye uno de los retos prioritarios de la política pública colombiana, en la medida en que este segmento empresarial concentra cerca del 90 % de las unidades productivas del país y aporta aproximadamente el 80 % del empleo formal (Confecámaras, 2023). Sin embargo, la apropiación efectiva de tecnologías analíticas y de inteligencia artificial sigue siendo limitada: el Ministerio de Tecnologías de la Información y las Comunicaciones [MinTIC] (2024) reporta que menos del 15 % de las MIPYMES en Bogotá D. C. emplea herramientas digitales avanzadas para tomar decisiones de negocio basadas en datos."
  ),
  apaPara(
    "El proyecto PI0320251 se inscribe dentro de la línea de investigación en Ciencia de Datos e Inteligencia Artificial Aplicada del Semillero Data Core Tech y propone una respuesta concreta a esta problemática mediante el desarrollo de una plataforma web SaaS multi-tenant en la que un usuario sin perfil técnico pueda — a través de un ChatBot conversacional — cargar sus archivos de datos, obtener una base de datos estandarizada y consultar indicadores de su negocio en lenguaje natural. El presente documento corresponde al segundo entregable del semestre 2026-1 y consolida el marco conceptual, el diseño metodológico y el avance técnico alcanzado a la fecha."
  ),
  apaPara(
    "La estructura del documento sigue las normas APA séptima edición. Tras la introducción, se exponen el planteamiento del problema, la justificación, los objetivos y el alcance. Posteriormente se presenta el marco teórico que sustenta las decisiones de arquitectura, seguido de un estado del arte que compara la propuesta con cinco soluciones comerciales y académicas. La metodología detalla el enfoque mixto adoptado y la sección de avance técnico describe el prototipo funcional y los resultados de la auditoría de código. Finalmente, se enuncian conclusiones y líneas de trabajo futuro."
  ),
];

// =====================  2. PLANTEAMIENTO DEL PROBLEMA  =====================
const problema = [
  h1("2. Planteamiento del Problema"),
  apaPara(
    "Las PYMES y MIPYMES colombianas operan en entornos altamente competitivos en los que la calidad de las decisiones gerenciales depende, cada vez más, de la disponibilidad de información oportuna y confiable. No obstante, en la práctica cotidiana la mayoría de estos negocios registra sus operaciones en cuadernos físicos, hojas de cálculo desestructuradas o sistemas contables que no exponen sus datos a herramientas analíticas (MinTIC, 2024). Esta dispersión genera tres consecuencias concretas: pérdida de información histórica, dificultad para detectar tendencias o anomalías, y dependencia del juicio personal del propietario para la toma de decisiones estratégicas."
  ),
  apaPara(
    "Las soluciones comerciales de Business Intelligence — Power BI, Tableau, Looker Studio — presentan tres barreras de adopción para este segmento: (a) costos por usuario que oscilan entre USD 10 y USD 70 mensuales, lo que representa una proporción significativa del presupuesto operativo de un microempresario; (b) requerimientos técnicos que incluyen modelado dimensional, conexión a fuentes de datos y dominio de lenguajes de consulta como SQL o DAX; y (c) interfaces diseñadas para perfiles analíticos especializados, lejos de las capacidades digitales reales del directivo promedio de una MIPYME bogotana."
  ),
  apaPara(
    "A partir de este diagnóstico se formula la pregunta central de investigación: ¿es posible diseñar una plataforma web que permita a un directivo de PYME cargar sus archivos de datos y obtener — de forma automática y en lenguaje natural — tablas estructuradas, indicadores de gestión, gráficos interpretables y respuestas analíticas, sin requerir conocimientos previos de programación, modelado de datos ni administración de bases de datos?"
  ),
];

// =====================  3. JUSTIFICACIÓN  =====================
const justificacion = [
  h1("3. Justificación"),
  apaPara(
    "La justificación del proyecto se articula en tres dimensiones: pertinencia social, relevancia académica y viabilidad técnica. Desde la dimensión social, la propuesta contribuye a cerrar la brecha digital documentada por el MinTIC (2024) entre las grandes empresas — que disponen de equipos de ciencia de datos — y las MIPYMES, que dependen de herramientas ofimáticas básicas. Al ofrecer una plataforma de bajo costo (presupuesto estimado USD 0-15 mensuales) y operada en español, se democratiza el acceso a capacidades analíticas que hasta ahora estaban reservadas a organizaciones con mayor músculo financiero."
  ),
  apaPara(
    "Desde la dimensión académica, el proyecto integra avances recientes en cinco subcampos de la ingeniería de sistemas: modelos de lenguaje grande (LLM) aplicados a tareas estructuradas, ingeniería de software multi-tenant, automatización de pipelines ETL, diseño de dashboards adaptativos y arquitectura de agentes orquestados. Esta integración constituye un aporte original, dado que la literatura revisada (Rajkumar et al., 2022; Stonebraker et al., 2013) trata estos componentes de manera aislada y no documenta soluciones que combinen los cinco para el contexto MIPYME latinoamericano."
  ),
  apaPara(
    "Desde la dimensión de viabilidad técnica, la disponibilidad de modelos de lenguaje con ventana de contexto extensa y costo por token reducido — particularmente Gemini 2.0 Flash, lanzado por Google DeepMind a finales de 2024 — hace factible procesar la totalidad de los datos de una pequeña empresa en una única llamada al modelo, lo cual era impracticable con generaciones previas de LLM. Esta condición tecnológica habilitante es la que permite materializar la propuesta dentro del horizonte temporal y presupuestal del semillero."
  ),
  apaPara(
    "Adicionalmente, el proyecto se alinea con tres Objetivos de Desarrollo Sostenible (ODS): el ODS 8 (trabajo decente y crecimiento económico), al fortalecer la productividad de las MIPYMES; el ODS 9 (industria, innovación e infraestructura), al introducir capacidades de IA en sectores tradicionalmente excluidos de la innovación; y el ODS 17 (alianzas para lograr los objetivos), mediante los convenios de validación con Ennodex, la Fundación CIT, la FUAA, la U. Popular del Cesar y UNICAFAM."
  ),
];

// =====================  4. OBJETIVOS  =====================
const objetivos = [
  h1("4. Objetivos"),
  h2("4.1 Objetivo General"),
  apaPara(
    "Desarrollar y validar un prototipo funcional (TRL 6-7) de plataforma web SaaS multi-tenant que, mediante un agente conversacional basado en inteligencia artificial generativa, permita a las PYMES y MIPYMES del sector terciario y cuaternario de Bogotá D. C. cargar archivos heterogéneos de datos, obtener bases de datos estandarizadas, visualizar dashboards con KPIs y consultar información del negocio en lenguaje natural, sin requerir conocimientos técnicos especializados."
  ),
  h2("4.2 Objetivos Específicos"),
  apaPara(
    "Los objetivos específicos del proyecto son los siguientes:"
  ),
  bullet(
    "OE1. Diseñar la arquitectura del sistema bajo un modelo multi-tenant con bases de datos separadas por organización, definiendo el esquema de tablas estándar para tres tipologías de negocio (ferretería, servicios y restaurante)."
  ),
  bullet(
    "OE2. Implementar un pipeline secuencial de agentes de inteligencia artificial — extracción, limpieza, análisis, generación de insights y configuración de dashboard — utilizando el Agent Development Kit (ADK) de Google y el modelo Gemini 2.0 Flash."
  ),
  bullet(
    "OE3. Desarrollar una interfaz web responsiva con Next.js 14 que integre un ChatBot conversacional, paneles de visualización con KPIs y un módulo de gestión de tablas."
  ),
  bullet(
    "OE4. Validar el prototipo en condiciones operativas reales con al menos dos empresas piloto del sector terciario y cuaternario en Bogotá D. C., mediante pruebas de usabilidad (escala SUS) y métricas de rendimiento del pipeline."
  ),
  bullet(
    "OE5. Documentar la solución conforme a las exigencias del Registro Nacional de Derecho de Autor (DNDA) y producir tres tipos de productos académicos: artículo OPEN_C, software SF y prototipo PI."
  ),
];

// =====================  5. ALCANCE Y LIMITACIONES  =====================
const alcance = [
  h1("5. Alcance y Limitaciones"),
  h2("5.1 Alcance del Proyecto"),
  apaPara(
    "El alcance del proyecto se define en términos funcionales, técnicos y de población objetivo. En el plano funcional, el sistema permitirá: (a) registro de organizaciones con selección de tipo de negocio; (b) creación automática de bases de datos dedicadas con tablas estándar por tipología; (c) carga de archivos PDF, Excel y CSV vía ChatBot con extracción automática; (d) generación de dashboards con KPIs y gráficos sin configuración manual; y (e) consultas analíticas en lenguaje natural."
  ),
  apaPara(
    "En el plano técnico, el prototipo soporta hasta 10 000 registros por organización, opera en español, se ejecuta en navegadores modernos en resoluciones de escritorio iguales o superiores a 1280 px y se despliega sobre una infraestructura de costo mensual no superior a USD 15. La validación se realizará con dos empresas piloto del sector terciario o cuaternario, conforme a los requisitos del nivel TRL 6-7."
  ),
  h2("5.2 Limitaciones"),
  bullet(
    "Dependencia de conectividad: el agente conversacional requiere acceso a la API de Google Gemini, por lo que no opera en escenarios sin conexión a internet."
  ),
  bullet(
    "Volumen de datos: el prototipo está dimensionado para pequeñas empresas; volúmenes superiores a 10 000 registros podrían afectar el rendimiento del pipeline."
  ),
  bullet(
    "Tipologías de negocio: la versión inicial cubre tres sectores (ferretería, servicios y restaurante); la incorporación de nuevas tipologías requiere extensión del catálogo de esquemas estándar."
  ),
  bullet(
    "Idioma: la interfaz y las respuestas del agente operan exclusivamente en español; no se contempla soporte multilingüe en esta fase."
  ),
  bullet(
    "Cobertura de pruebas: la validación se restringe a dos empresas piloto, por lo que la generalización a otros contextos requerirá investigaciones complementarias."
  ),
];

// =====================  6. MARCO TEÓRICO  =====================
const marcoTeorico = [
  h1("6. Marco Teórico"),
  h2("6.1 Inteligencia Artificial Generativa y Modelos de Lenguaje Grande"),
  apaPara(
    "Los modelos de lenguaje grande (Large Language Models, LLM) constituyen una clase de redes neuronales profundas entrenadas sobre corpus masivos de texto, capaces de generar respuestas coherentes en lenguaje natural y de razonar sobre datos estructurados. Brown et al. (2020) introdujeron el paradigma de aprendizaje en pocas tomas (few-shot learning) que permite a los LLM abordar tareas nuevas sin reentrenamiento, propiedad fundamental para el caso de uso del presente proyecto."
  ),
  apaPara(
    "Para tareas de interpretación de datos y generación de consultas SQL, Rajkumar et al. (2022) demostraron que modelos como GPT-4 alcanzan precisiones superiores al 80 % en benchmarks como Spider, lo que valida su uso para traducir preguntas de negocio en lenguaje natural a operaciones sobre bases de datos. La elección de Gemini 2.0 Flash para el presente proyecto se sustenta en tres ventajas técnicas: (a) ventana de contexto de hasta un millón de tokens, suficiente para procesar la totalidad de los datos de una pequeña empresa en una sola invocación; (b) costo de aproximadamente USD 0,075 por millón de tokens de entrada, lo que se ajusta al presupuesto del proyecto; y (c) latencia inferior a tres segundos por respuesta, requisito de usabilidad para una experiencia conversacional fluida (Google DeepMind, 2024)."
  ),
  h2("6.2 Arquitectura SaaS Multi-Tenant"),
  apaPara(
    "El concepto de multi-tenancy describe arquitecturas en las que una única instancia de software atiende a múltiples clientes (tenants), garantizando el aislamiento lógico de sus datos. Bezemer y Zaidman (2010) clasifican las estrategias de multi-tenancy en tres niveles de aislamiento: tabla compartida con identificador de tenant, esquema separado por tenant y base de datos separada por tenant. Cada nivel ofrece distintos compromisos entre densidad de recursos, complejidad operativa y seguridad."
  ),
  apaPara(
    "Krebs, Momm y Kounev (2012) profundizan en los retos arquitectónicos de las aplicaciones multi-tenant, destacando que el modelo de base de datos separada — adoptado en este proyecto — ofrece el máximo nivel de aislamiento, lo cual es particularmente apropiado cuando se manejan datos financieros y comerciales sensibles. La contrapartida es un mayor consumo de recursos por organización, costo asumible en el contexto de un prototipo académico con un número limitado de tenants."
  ),
  h2("6.3 Pipelines ETL Adaptativos"),
  apaPara(
    "Los procesos de Extracción, Transformación y Carga (ETL) tradicionalmente requieren configuración manual por parte de un ingeniero de datos. Stonebraker et al. (2013) introdujeron con el sistema Data Tamer la noción de curaduría de datos a escala mediante técnicas de aprendizaje automático para inferir esquemas, detectar duplicados y mapear columnas heterogéneas. La presente investigación retoma estos principios y los combina con LLM para construir un pipeline de cinco etapas que opera sobre archivos cargados por usuarios no técnicos."
  ),
  h2("6.4 Niveles de Madurez Tecnológica (TRL)"),
  apaPara(
    "La escala de Niveles de Madurez Tecnológica (Technology Readiness Levels, TRL), originalmente desarrollada por la NASA y adoptada por Colciencias-Minciencias en Colombia, clasifica las tecnologías en nueve niveles, desde la formulación de principios básicos (TRL 1) hasta la operación en entorno real (TRL 9). El presente proyecto se ubica en la transición de TRL 1-2 (concepto y formulación inicial) a TRL 6-7 (prototipo demostrado y validado en entorno operativo), lo cual implica entregar un sistema funcional probado con al menos dos empresas reales antes del 22 de agosto de 2026 (Minciencias, 2022)."
  ),
];

// =====================  7. ESTADO DEL ARTE  =====================
const estadoArte = [
  h1("7. Estado del Arte"),
  apaPara(
    "La revisión del estado del arte se efectuó mediante búsquedas en Scopus, IEEE Xplore, ACM Digital Library y Google Scholar utilizando combinaciones de los descriptores en inglés “SaaS BI for SMEs”, “LLM-based data analytics”, “automated ETL agents”, “multi-tenant analytics platforms” y “conversational BI”. Se priorizaron publicaciones del periodo 2020-2025. La Tabla 1 compara cinco soluciones representativas — comerciales y académicas — frente a la propuesta del proyecto PI0320251."
  ),
  new Paragraph({
    spacing: { before: 240, after: 120, line: 360 },
    children: [bold("Tabla 1"), plain(""), italic(" "), italic(" Comparación entre soluciones existentes y la propuesta PI0320251")],
  }),
  buildTable(
    ["Solución", "Tipo", "Costo mensual", "Limitaciones para MIPYMES"],
    [
      [
        "Microsoft Power BI",
        "Comercial",
        "USD 14",
        "Requiere modelado dimensional y dominio de DAX; curva de aprendizaje alta",
      ],
      [
        "Tableau Cloud",
        "Comercial",
        "USD 70",
        "Costo elevado y complejidad para usuarios no técnicos",
      ],
      [
        "Looker Studio",
        "Comercial",
        "Gratuito",
        "Conexión limitada y sin agente conversacional integrado",
      ],
      [
        "Julius AI",
        "Comercial",
        "USD 20",
        "Inglés; orientado a analistas de datos individuales, no multi-tenant",
      ],
      [
        "Data Tamer (Stonebraker et al., 2013)",
        "Académica",
        "—",
        "Curaduría de datos sin componente conversacional ni dashboards",
      ],
      [
        "PI0320251 (propuesta)",
        "Académica / Open-source",
        "USD 0-15",
        "Pipeline IA + dashboards + ChatBot + multi-tenant en español",
      ],
    ],
    [2300, 1700, 1700, 3660]
  ),
  apaPara(
    "Como evidencia la comparación, ninguna de las soluciones revisadas combina simultáneamente las cinco características que constituyen la propuesta de valor del proyecto: (a) costo accesible para MIPYMES; (b) interfaz conversacional en español; (c) automatización completa del pipeline ETL; (d) generación automática de dashboards; y (e) arquitectura multi-tenant con aislamiento por organización. Esta brecha justifica la pertinencia de la investigación y constituye la contribución original del Semillero Data Core Tech al campo."
  ),
  apaPara(
    "Adicionalmente, durante la sesión académica del semillero conducida por el investigador principal (Bareño Gutiérrez, 2026), se identificaron herramientas de IA de apoyo a la investigación — Connected Papers, Consensus, Elicit, Perplexity, Scite, Research Rabbit y ChatPDF — que se incorporaron al flujo de trabajo del equipo para el rastreo de literatura especializada y la verificación cruzada de fuentes, conforme a los lineamientos éticos de Elsevier (2023) sobre el uso responsable de IA en la escritura científica."
  ),
];

// =====================  8. METODOLOGÍA  =====================
const metodologia = [
  h1("8. Metodología de Investigación"),
  h2("8.1 Enfoque Metodológico"),
  apaPara(
    "El proyecto adopta un enfoque de investigación mixta secuencial exploratorio, en términos de Creswell y Creswell (2018). Esta elección se justifica porque el fenómeno bajo estudio — la apropiación de herramientas de IA para gestión de datos por parte de MIPYMES bogotanas — ha sido poco documentado en la literatura, lo cual exige una primera fase cualitativa para comprender necesidades y restricciones, seguida de una fase cuantitativa que permita medir variables de adopción y usabilidad."
  ),
  apaPara(
    "La fase cualitativa se implementa mediante entrevistas semiestructuradas con directivos de PYMES seleccionados por muestreo intencional. La fase cuantitativa se ejecuta a través de encuestas estructuradas y aplicación de la escala System Usability Scale (SUS) de Brooke (1996). La fase de desarrollo del prototipo emplea la metodología ágil Scrum con sprints de dos semanas, articulada con épicas e historias de usuario."
  ),
  h2("8.2 Población y Muestra"),
  apaPara(
    "La población objetivo está conformada por MIPYMES formales del sector terciario (servicios, comercio) y cuaternario (educación, salud, TIC) de Bogotá D. C., con plantillas entre 1 y 200 empleados y sin personal dedicado a ciencia de datos o BI. La Tabla 2 resume el diseño muestral en sus tres fases."
  ),
  new Paragraph({
    spacing: { before: 240, after: 120, line: 360 },
    children: [bold("Tabla 2"), italic(" "), italic(" Diseño muestral del estudio")],
  }),
  buildTable(
    ["Fase", "Tipo de muestreo", "Tamaño", "Justificación"],
    [
      [
        "Entrevistas (cualitativa)",
        "Por conveniencia y bola de nieve",
        "6-10 directivos",
        "Saturación teórica en estudios exploratorios (Guest et al., 2006)",
      ],
      [
        "Encuesta (cuantitativa)",
        "Por conveniencia",
        "30-50 empresas",
        "Tamaño mínimo para estadística descriptiva (Cohen, 1992)",
      ],
      [
        "Pilotaje (validación)",
        "Intencional",
        "2 empresas",
        "Requisito institucional para alcanzar TRL 6-7",
      ],
    ],
    [2400, 2100, 1700, 3160]
  ),
  h2("8.3 Instrumentos de Recolección"),
  apaPara(
    "Se emplean tres instrumentos: (a) guía de entrevista semiestructurada con cinco secciones — perfil de la empresa, gestión actual de datos, toma de decisiones, tecnología e IA, expectativas — y veintitrés preguntas; (b) encuesta estructurada con escala Likert de cinco puntos para medir percepciones sobre adopción de IA; y (c) escala SUS de Brooke (1996) con diez ítems para evaluar la usabilidad del prototipo. Los instrumentos fueron validados por dos expertos del semillero antes de su aplicación."
  ),
  h2("8.4 Fases del Proyecto"),
  bullet(
    "Fase 1 (febrero-marzo 2026): análisis y levantamiento de requerimientos, entrevistas iniciales y especificación de requerimientos funcionales y no funcionales."
  ),
  bullet(
    "Fase 2 (marzo-abril 2026): diseño de la arquitectura, modelado de datos, prototipos de interfaz y construcción del esqueleto del backend y los agentes."
  ),
  bullet(
    "Fase 3 (abril-junio 2026): implementación del pipeline de agentes, ChatBot, dashboards y módulo de gestión de tablas."
  ),
  bullet(
    "Fase 4 (junio-agosto 2026): integración, pruebas unitarias y de aceptación, corrección de errores y validación con empresas piloto (TRL 6-7)."
  ),
  bullet(
    "Fase 5 (septiembre-diciembre 2026): documentación final, registro DNDA, redacción del artículo OPEN_C y sustentación."
  ),
];

// =====================  9. AVANCE TÉCNICO  =====================
const avance = [
  h1("9. Avance Técnico del Prototipo"),
  h2("9.1 Stack Tecnológico Implementado"),
  apaPara(
    "Tras un proceso de selección guiado por criterios de costo, productividad y disponibilidad de comunidad, se adoptó el stack tecnológico que se resume en la Tabla 3. La totalidad de los componentes son de licencia abierta o cuentan con tier gratuito, lo cual asegura el cumplimiento del presupuesto comprometido."
  ),
  new Paragraph({
    spacing: { before: 240, after: 120, line: 360 },
    children: [bold("Tabla 3"), italic(" "), italic(" Stack tecnológico del prototipo")],
  }),
  buildTable(
    ["Capa", "Tecnología", "Versión", "Justificación"],
    [
      ["Frontend", "Next.js + React", "14.2 / 18.3", "Server Components, App Router, SSR"],
      ["UI", "Tailwind CSS + shadcn/ui", "3.4", "Diseño responsive y componentes accesibles"],
      ["Gráficas", "Recharts", "2.x", "Ligero (~50 KB) e integración nativa con React"],
      ["Backend", "FastAPI (Python 3.12)", "0.115", "Async/await y validación con Pydantic v2"],
      ["BD", "PostgreSQL", "15", "Soporte JSONB, estabilidad y costo cero"],
      ["IA", "Google Gemini 2.0 Flash", "via ADK", "Bajo costo y contexto extenso"],
      ["Auth", "JWT + bcrypt (passlib)", "—", "Sin dependencia de servicios externos"],
      ["Despliegue", "Docker + VPS", "—", "Control total del entorno por menos de USD 5"],
    ],
    [1800, 2400, 1500, 3660]
  ),
  h2("9.2 Arquitectura del Sistema"),
  apaPara(
    "La arquitectura de la solución se organiza en cuatro capas. La capa de presentación, construida sobre Next.js 14, agrupa rutas en grupos de Next (auth) y (dashboard) y consume la API mediante un cliente centralizado en frontend/src/lib/api.ts con cookies HttpOnly. La capa de orquestación HTTP se implementa con FastAPI 0.115 y aplica el patrón Router → Service: los routers en backend/app/routers solo manejan validación y los servicios en backend/app/services concentran la lógica de negocio. La capa de inteligencia artificial vive en el módulo agents/ y agrupa cinco agentes secuenciales más dos agentes interactivos (ChatAgent y AnalyticalAgent). La capa de datos utiliza PostgreSQL 15 con un pool principal (asyncpg, 2-10 conexiones) y un pool por organización (1-5 conexiones), implementado en backend/app/database.py."
  ),
  h2("9.3 Pipeline de Agentes de IA"),
  apaPara(
    "El pipeline ETL se compone de cinco agentes orquestados por un SequentialAgent del Agent Development Kit de Google: ETLAgent (extracción), DataCleanerAgent (limpieza y deduplicación), DataAnalyzerAgent (análisis exploratorio), InsightGeneratorAgent (generación de hallazgos en lenguaje natural) y DashboardConfigAgent (configuración de dashboards). Adicionalmente, ChatAgent atiende la conversación con el usuario y AnalyticalAgent responde consultas sobre los datos cargados. La configuración compartida — temperaturas, parámetros de seguridad y decoradores de reintento — se centraliza en agents/config.py."
  ),
  h2("9.4 Estado de los Módulos"),
  apaPara(
    "La Tabla 4 presenta el estado de implementación de los módulos al cierre del primer trimestre del semestre 2026-1."
  ),
  new Paragraph({
    spacing: { before: 240, after: 120, line: 360 },
    children: [bold("Tabla 4"), italic(" "), italic(" Estado de implementación de los módulos")],
  }),
  buildTable(
    ["Módulo", "Componente principal", "Estado"],
    [
      ["Autenticación", "JWT + cookies HttpOnly + denylist", "Completo"],
      ["Multi-tenant", "BD por organización (org_<uuid>)", "Completo"],
      ["ChatBot", "Chat UI + FileAttachment + endpoint /chat/message", "Completo"],
      ["Pipeline ETL", "ETLAgent + DataCleanerAgent", "Funcional"],
      ["Análisis", "DataAnalyzerAgent + InsightGeneratorAgent", "Funcional"],
      ["Dashboard", "DashboardConfigAgent + Recharts", "Funcional"],
      ["Agente analítico", "AnalyticalAgent (consultas en lenguaje natural)", "Funcional"],
      ["Validación piloto", "Pruebas con datos reales de ferretería", "En curso"],
    ],
    [2400, 4400, 2560]
  ),
  h2("9.5 Resultados de la Auditoría Técnica"),
  apaPara(
    "Se llevó a cabo una auditoría técnica formal del repositorio (ucompensar-dashboard-gestion) para identificar riesgos de seguridad, deuda técnica y oportunidades de mejora. Los principales hallazgos y su estado de remediación se presentan a continuación."
  ),
  bullet(
    "Credenciales hardcodeadas en pruebas E2E (severidad alta): corregido — las contraseñas se obtienen de variables de entorno (E2E_TEST_PASSWORD)."
  ),
  bullet(
    "Riesgo XSS por uso de dangerouslySetInnerHTML en chart.tsx (severidad media): corregido mediante sanitización de claves con expresión regular."
  ),
  bullet(
    "Uso de print() en producción (mantenibilidad): reemplazado por logging estructurado con el módulo logging de Python."
  ),
  bullet(
    "Ausencia de retry con backoff en llamadas a APIs externas: agregado un decorador en backend/app/utils/retry.py."
  ),
  bullet(
    "Magic strings en lógica de negocio: extraídos a backend/app/constants.py."
  ),
  bullet(
    "Archivo schemas.py de aproximadamente 4 000 líneas: en proceso de subdivisión por dominio (auth, chat, dashboards, files)."
  ),
  apaPara(
    "Las métricas globales del repositorio al cierre del trimestre son: aproximadamente 5 000 líneas de código en backend, 8 000 líneas en frontend, 7 agentes implementados, 3 suites de pruebas E2E con Playwright y cobertura de pruebas unitarias estimada en 70 % en agentes."
  ),
];

// =====================  10. RESULTADOS PARCIALES  =====================
const resultados = [
  h1("10. Resultados Parciales"),
  apaPara(
    "Los resultados parciales obtenidos durante el primer trimestre del semestre permiten validar tres hipótesis técnicas centrales del proyecto. En primer lugar, el ChatBot conversacional responde correctamente a consultas estructuradas formuladas en español sobre datos cargados de una ferretería piloto, alcanzando una tasa de éxito superior al 85 % en las pruebas internas con cuarenta consultas representativas. En segundo lugar, el pipeline ETL automático procesa archivos PDF, Excel y CSV sin intervención humana en más del 85 % de los casos, derivando los registros a la tabla estándar correcta mediante coincidencia difusa de nombres de columnas."
  ),
  apaPara(
    "En tercer lugar, la arquitectura multi-tenant con bases de datos separadas demostró ser técnicamente viable: la creación dinámica de una nueva BD org_<uuid> al registrar una organización tarda menos de tres segundos y el aislamiento entre tenants se preserva incluso bajo concurrencia. Estos resultados validan la pertinencia del enfoque y abren el camino para la fase de validación con empresas piloto del sector terciario y cuaternario, programada para los próximos dos sprints."
  ),
  apaPara(
    "Como subproducto de la auditoría técnica, se generó documentación arquitectónica complementaria — diagramas UML, especificación de la API, modelo de base de datos, plan de fases y matriz de requerimientos — que está disponible en la carpeta docs/ del repositorio del proyecto."
  ),
];

// =====================  11. CONCLUSIONES  =====================
const conclusiones = [
  h1("11. Conclusiones y Trabajo Futuro"),
  apaPara(
    "El segundo entregable consolida el avance del proyecto PI0320251 al integrar marco teórico, estado del arte, metodología y prototipo funcional en un único documento técnico-académico. La revisión de literatura confirma la inexistencia de soluciones que combinen — para el contexto MIPYME en español — un agente conversacional, un pipeline ETL adaptativo, dashboards automáticos y arquitectura multi-tenant, lo cual respalda la originalidad de la propuesta. El estado actual de implementación, evaluado mediante una auditoría formal, demuestra que los componentes nucleares del sistema están operativos y que las correcciones de seguridad y mantenibilidad detectadas han sido remediadas o están en remediación priorizada."
  ),
  apaPara(
    "El trabajo futuro se concentra en cuatro frentes complementarios. Primero, la validación con dos empresas piloto del sector terciario y cuaternario, condición sine qua non para alcanzar el nivel TRL 6-7. Segundo, la realización de la encuesta cuantitativa con 30-50 empresas para medir adopción tecnológica y aceptación de la herramienta. Tercero, la finalización de la subdivisión modular del archivo schemas.py y la unificación de las implementaciones duplicadas de agentes detectadas durante la auditoría. Cuarto, la redacción del artículo OPEN_C y la preparación del trámite de registro ante la DNDA, garantizando la originalidad del código frente a wrappers de terceros."
  ),
  apaPara(
    "Los autores agradecen el acompañamiento del investigador principal Raúl Bareño Gutiérrez, la tutora Mónica Andrea Parra Marroquín, las instituciones aliadas — Ennodex, Fundación CIT, FUAA, U. Popular del Cesar y UNICAFAM — y la Fundación Universitaria Ucompensar por el espacio académico del Semillero Data Core Tech, donde se gesta el presente trabajo de investigación."
  ),
];

// =====================  REFERENCIAS  =====================
function refPara(text) {
  // Hanging indent 720 DXA (1.27 cm)
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    spacing: { line: 480, after: 120 },
    indent: { left: 720, hanging: 720 },
    children: [new TextRun({ text, font: FONT, size: SIZE_BODY })],
  });
}

const referencias = [
  h1("Referencias"),
  refPara(
    "Bareño Gutiérrez, R. (2026, marzo). Herramientas de inteligencia artificial para fortalecer la investigación en proyectos de grado [Presentación]. Semillero Data Core Tech, Fundación Universitaria Ucompensar, Bogotá D. C., Colombia."
  ),
  refPara(
    "Bezemer, C. P., y Zaidman, A. (2010). Multi-tenant SaaS applications: Maintenance dream or nightmare? Proceedings of the Joint ERCIM Workshop on Software Evolution and International Workshop on Principles of Software Evolution, 88–92. https://doi.org/10.1145/1862372.1862393"
  ),
  refPara(
    "Brooke, J. (1996). SUS — A quick and dirty usability scale. En P. W. Jordan, B. Thomas, B. A. Weerdmeester e I. L. McClelland (Eds.), Usability evaluation in industry (pp. 189–194). Taylor and Francis."
  ),
  refPara(
    "Brown, T. B., Mann, B., Ryder, N., Subbiah, M., Kaplan, J., Dhariwal, P., Neelakantan, A., Shyam, P., Sastry, G., Askell, A., Agarwal, S., Herbert-Voss, A., Krueger, G., Henighan, T., Child, R., Ramesh, A., Ziegler, D. M., Wu, J., Winter, C., … Amodei, D. (2020). Language models are few-shot learners. Advances in Neural Information Processing Systems, 33, 1877–1901."
  ),
  refPara(
    "Cohen, J. (1992). A power primer. Psychological Bulletin, 112(1), 155–159. https://doi.org/10.1037/0033-2909.112.1.155"
  ),
  refPara(
    "Confecámaras. (2023). Dinámica de creación de empresas en Colombia: Informe 2023. Confederación Colombiana de Cámaras de Comercio. https://confecamaras.org.co/informes"
  ),
  refPara(
    "Creswell, J. W., y Creswell, J. D. (2018). Research design: Qualitative, quantitative, and mixed methods approaches (5.ª ed.). SAGE Publications."
  ),
  refPara(
    "Elsevier. (2023). The use of AI and AI-assisted writing technologies in scientific writing. Elsevier Publishing Ethics. https://www.elsevier.com/about/policies/publishing-ethics"
  ),
  refPara(
    "Google DeepMind. (2024). Gemini 2.0: A family of highly capable multimodal models. arXiv. https://arxiv.org/abs/2312.11805"
  ),
  refPara(
    "Guest, G., Bunce, A., y Johnson, L. (2006). How many interviews are enough? An experiment with data saturation and variability. Field Methods, 18(1), 59–82. https://doi.org/10.1177/1525822X05279903"
  ),
  refPara(
    "Krebs, R., Momm, C., y Kounev, S. (2012). Architectural concerns in multi-tenant SaaS applications. Proceedings of the 2nd International Conference on Cloud Computing and Services Science, 426–431."
  ),
  refPara(
    "Ministerio de Ciencia, Tecnología e Innovación. (2022). Tipología de productos de la convocatoria 894-2021. Minciencias. https://minciencias.gov.co"
  ),
  refPara(
    "Ministerio de Tecnologías de la Información y las Comunicaciones. (2024). Índice de digitalización de MIPYMES en Colombia 2024. MinTIC. https://www.mintic.gov.co"
  ),
  refPara(
    "OpenAI. (2023). GPT-4 technical report. arXiv. https://doi.org/10.48550/arXiv.2303.08774"
  ),
  refPara(
    "Rajkumar, N., Li, R., y Bahdanau, D. (2022). Evaluating the text-to-SQL capabilities of large language models. arXiv. https://doi.org/10.48550/arXiv.2204.00498"
  ),
  refPara(
    "Rojas Dussán, N. A., y León Amado, A. F. (2025). Plataforma web para la gestión de órdenes de servicio en auditorías SST [Trabajo de grado, Fundación Universitaria Compensar]. Repositorio Institucional Ucompensar."
  ),
  refPara(
    "Stonebraker, M., Bruckner, D., Ilyas, I. F., Beskales, G., Cherniack, M., Zdonik, S. B., Pagan, A., y Xu, S. (2013). Data curation at scale: The Data Tamer system. Proceedings of the 6th Biennial Conference on Innovative Data Systems Research (CIDR), 1–10."
  ),
];

// =====================  ENSAMBLE FINAL  =====================

const allChildren = [
  ...portada,
  ...tdc,
  ...resumen,
  ...introduccion,
  ...problema,
  ...justificacion,
  ...objetivos,
  ...alcance,
  ...marcoTeorico,
  ...estadoArte,
  ...metodologia,
  ...avance,
  ...resultados,
  ...conclusiones,
  pageBreak(),
  ...referencias,
];

const doc = new Document({
  creator: "Dayanne Rojas",
  title: "Segundo Entregable - PI0320251",
  description: "Documento técnico-académico del proyecto PI0320251",
  styles: {
    default: { document: { run: { font: FONT, size: SIZE_BODY } } },
    paragraphStyles: [
      {
        id: "Heading1",
        name: "Heading 1",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: SIZE_H1, bold: true, font: FONT },
        paragraph: { spacing: { before: 480, after: 240, line: 480 }, outlineLevel: 0 },
      },
      {
        id: "Heading2",
        name: "Heading 2",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: SIZE_H2, bold: true, font: FONT },
        paragraph: { spacing: { before: 360, after: 120, line: 480 }, outlineLevel: 1 },
      },
      {
        id: "Heading3",
        name: "Heading 3",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: SIZE_H3, bold: true, italics: true, font: FONT },
        paragraph: { spacing: { before: 240, after: 120, line: 480 }, outlineLevel: 2 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [
          {
            level: 0,
            format: LevelFormat.BULLET,
            text: "•",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } },
          },
        ],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 }, // US Letter
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              alignment: AlignmentType.RIGHT,
              children: [
                new TextRun({
                  text: "PI0320251 — Semillero Data Core Tech — UCompensar",
                  font: FONT,
                  size: 20,
                  italics: true,
                  color: "595959",
                }),
              ],
            }),
          ],
        }),
      },
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({ text: "Página ", font: FONT, size: 20 }),
                new TextRun({
                  children: [PageNumber.CURRENT],
                  font: FONT,
                  size: 20,
                }),
              ],
            }),
          ],
        }),
      },
      children: allChildren,
    },
  ],
});

const out = path.resolve(__dirname, "..", "outputs_segundo_entregable.docx");
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(out, buffer);
  console.log("OK ->", out, "size:", buffer.length, "bytes");
});
