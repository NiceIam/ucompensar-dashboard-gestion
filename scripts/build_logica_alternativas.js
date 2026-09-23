/**
 * Genera el bloque "¿Qué alternativa novedosa de solución tengo?" para
 * la Actividad 1 de Lógica Matemática y Programación.
 *
 * Audiencia: estudiante de primer semestre de ciencia de datos.
 * Escenario: empresa inmobiliaria con chatbot lineal sin filtrado.
 *
 * Salida: outputs_logica_alternativas.docx
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
  ImageRun,
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
} = require("docx");

const FONT = "Times New Roman";
const SIZE_BODY = 24; // 12pt
const SIZE_H1 = 28;
const SIZE_H2 = 26;
const SIZE_H3 = 24;
const MONO = "Consolas";

const IMG_DIR = "/sessions/nice-vigilant-tesla/mnt/outputs/img_logica";

const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const cellBorders = { top: border, bottom: border, left: border, right: border };

function plain(text, opts = {}) { return new TextRun({ text, font: FONT, size: SIZE_BODY, ...opts }); }
function bold(text, opts = {}) { return new TextRun({ text, font: FONT, size: SIZE_BODY, bold: true, ...opts }); }
function italic(text, opts = {}) { return new TextRun({ text, font: FONT, size: SIZE_BODY, italics: true, ...opts }); }
function code(text, opts = {}) { return new TextRun({ text, font: MONO, size: 20, ...opts }); }

function apaPara(text, opts = {}) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    spacing: { line: 360, after: 120 },
    indent: opts.indent === false ? undefined : { firstLine: 720 },
    children: typeof text === "string"
      ? [new TextRun({ text, font: FONT, size: SIZE_BODY })]
      : text,
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    alignment: AlignmentType.LEFT,
    spacing: { before: 360, after: 180, line: 360 },
    children: [new TextRun({ text, font: FONT, size: SIZE_H1, bold: true })],
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    alignment: AlignmentType.LEFT,
    spacing: { before: 300, after: 120, line: 360 },
    children: [new TextRun({ text, font: FONT, size: SIZE_H2, bold: true })],
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    alignment: AlignmentType.LEFT,
    spacing: { before: 200, after: 80, line: 360 },
    children: [new TextRun({ text, font: FONT, size: SIZE_H3, bold: true, italics: true })],
  });
}

function bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { line: 320, after: 60 },
    alignment: AlignmentType.JUSTIFIED,
    children: typeof text === "string"
      ? [new TextRun({ text, font: FONT, size: SIZE_BODY })]
      : text,
  });
}

function pageBreak() { return new Paragraph({ children: [new PageBreak()] }); }

// Bloque de pseudocódigo / código con fondo gris claro
function codeBlock(lines) {
  return lines.map((line) =>
    new Paragraph({
      spacing: { line: 260, after: 0 },
      shading: { fill: "F2F2F2", type: ShadingType.CLEAR, color: "auto" },
      indent: { left: 360 },
      children: [code(line || " ")],
    })
  );
}

// Imagen centrada con caption
function image(filename, w, h, caption) {
  const filePath = path.join(IMG_DIR, filename);
  const para = new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 240, after: 60 },
    children: [
      new ImageRun({
        type: "png",
        data: fs.readFileSync(filePath),
        transformation: { width: w, height: h },
        altText: { title: caption, description: caption, name: filename },
      }),
    ],
  });
  return [
    para,
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 },
      children: [italic(caption)],
    }),
  ];
}

// Tabla con encabezado azul
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
            children: [new TextRun({ text: txt, font: FONT, size: 22, bold: true, color: "FFFFFF" })],
          }),
        ],
      })
  );
  const headerRow = new TableRow({ tableHeader: true, children: headerCells });
  const bodyRows = rows.map((cols) =>
    new TableRow({
      children: cols.map((txt, i) =>
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

// ===========================================================================
// CONTENIDO
// ===========================================================================

const contenido = [
  // Encabezado del bloque
  h1("c. ¿Qué alternativa novedosa de solución tengo?"),
  apaPara(
    "El equipo plantea tres alternativas de solución para el chatbot inmobiliario, organizadas en orden de complejidad creciente. La primera utiliza únicamente lógica proposicional clásica con reglas booleanas; la segunda incorpora un sistema de puntaje ponderado que mantiene la base lógica pero agrega flexibilidad numérica; la tercera combina las reglas con un modelo conversacional asistido por inteligencia artificial. Cada alternativa se sustenta en estructuras de control, tablas de verdad, reglas condicionales, diagramas de flujo y pseudocódigo, conforme al criterio b del enunciado."
  ),

  // ---------- a. Datos del escenario ----------
  h2("a. Datos del escenario expresados en lógica matemática"),
  apaPara(
    "Antes de proponer las alternativas, es necesario formalizar los datos del escenario. La empresa inmobiliaria recibe consultas a través de un chatbot y, por experiencia comercial, se sabe que un cliente vale la pena ser atendido por un asesor humano cuando se cumplen cuatro condiciones simultáneas. Estas condiciones se traducen en cuatro proposiciones simples, cada una con valor de verdad V (verdadero) o F (falso):"
  ),
  bullet([bold("p: "), plain("el cliente tiene presupuesto suficiente para alguna propiedad del catálogo.")]),
  bullet([bold("q: "), plain("el cliente busca una propiedad en la zona objetivo de la inmobiliaria.")]),
  bullet([bold("r: "), plain("el cliente puede pagar la cuota inicial requerida.")]),
  bullet([bold("s: "), plain("el cliente está disponible para visitar la propiedad esta semana.")]),
  apaPara(
    "Con estas variables se construye una tabla de verdad de 16 filas (2⁴ combinaciones posibles), que clasifica al cliente en tres categorías: caliente (alta prioridad), tibio (seguimiento) y frío (descartar o nutrir con marketing automático). La regla principal es una conjunción: el cliente caliente cumple p ∧ q ∧ r ∧ s. La Figura 1 sintetiza visualmente esta clasificación."
  ),
  ...image("01_tabla_verdad.png", 380, 540, "Figura 1. Tabla de verdad con la clasificación lógica del cliente inmobiliario sobre las cuatro variables proposicionales p, q, r, s."),

  // ---------- ALTERNATIVA 1 ----------
  h2("Alternativa 1 — Chatbot con reglas booleanas estrictas"),

  h3("Descripción"),
  apaPara(
    "Esta primera alternativa es la más sencilla de implementar y la que mejor refleja directamente lo que estudiamos en clase de lógica matemática. El chatbot pregunta al cliente cuatro preguntas cerradas (sí o no), recibe sus respuestas, las trata como variables proposicionales y aplica una regla booleana exacta para clasificarlo. Si las cuatro respuestas son sí, el cliente es caliente; si solo falla la disponibilidad de visita, es tibio; en cualquier otro caso, es frío. La ventaja es que es totalmente predecible y se puede explicar con una tabla de verdad. La desventaja es que es muy estricta: un cliente que tiene presupuesto, está en la zona y quiere visitar pero no tiene la cuota inicial, queda descartado, aunque podría calificar para un crédito."
  ),

  h3("Reglas condicionales (cálculo proposicional)"),
  apaPara("La clasificación se modela con tres reglas formales:"),
  ...codeBlock([
    "Regla 1 (CALIENTE):  caliente ⇔ (p ∧ q ∧ r ∧ s)",
    "Regla 2 (TIBIO):     tibio    ⇔ (p ∧ q ∧ r ∧ ¬s)",
    "Regla 3 (FRÍO):      frio     ⇔ ¬caliente ∧ ¬tibio",
  ]),
  apaPara(
    "Cada regla utiliza únicamente conectores lógicos básicos: la conjunción (∧), la negación (¬) y la equivalencia (⇔). La regla 3 garantiza que toda combinación tiene una clasificación, porque las tres categorías son mutuamente excluyentes y cubren todo el espacio de posibilidades (16 filas de la tabla de verdad)."
  ),

  h3("Pseudocódigo"),
  ...codeBlock([
    "ALGORITMO  ClasificarCliente_Booleano",
    "ENTRADA:   p, q, r, s   (booleanos: True / False)",
    "SALIDA:    categoria    (CALIENTE | TIBIO | FRÍO)",
    "INICIO",
    "  SI (p Y q Y r Y s) ENTONCES",
    "      categoria ← \"CALIENTE\"",
    "  SINO SI (p Y q Y r Y NO s) ENTONCES",
    "      categoria ← \"TIBIO\"",
    "  SINO",
    "      categoria ← \"FRÍO\"",
    "  FIN_SI",
    "  RETORNAR categoria",
    "FIN",
  ]),

  h3("Diagrama de flujo"),
  ...image("02_flujo_alt1.png", 460, 580, "Figura 2. Diagrama de flujo de la Alternativa 1. Cada rombo representa una decisión booleana basada en la conjunción de las variables p, q, r, s."),

  h3("Estructuras de control utilizadas"),
  bullet("Estructura condicional anidada (SI ... SINO SI ... SINO): permite evaluar las tres categorías en orden de prioridad."),
  bullet("Operadores lógicos Y (AND) y NO (NOT): implementan directamente la conjunción y la negación del cálculo proposicional."),
  bullet("Variable de salida (categoria): almacena el resultado para retornarlo al final."),

  // ---------- ALTERNATIVA 2 ----------
  h2("Alternativa 2 — Chatbot con scoring lógico ponderado"),

  h3("Descripción"),
  apaPara(
    "La segunda alternativa parte de la misma base lógica pero relaja la rigidez de la primera. En lugar de exigir que las cuatro condiciones se cumplan al pie de la letra, asigna un peso numérico a cada variable según su importancia comercial. El presupuesto y la zona pesan 3 puntos cada uno, la cuota inicial pesa 2 puntos y la disponibilidad pesa 1 punto. El chatbot suma los puntos y compara contra dos umbrales: si el puntaje es mayor o igual a 7, el cliente es caliente; si está entre 4 y 6, es tibio; por debajo de 4 es frío. Esta alternativa es más flexible y se acerca a cómo realmente trabajan los modelos de scoring crediticio."
  ),

  h3("Reglas condicionales con pesos"),
  ...codeBlock([
    "Función de scoring:",
    "  score = 3·valor(p) + 3·valor(q) + 2·valor(r) + 1·valor(s)",
    "  donde valor(x) = 1 si x es verdadero, 0 si es falso",
    "",
    "Reglas de clasificación:",
    "  Regla 1: caliente ⇔ (score ≥ 7)",
    "  Regla 2: tibio    ⇔ (4 ≤ score < 7)",
    "  Regla 3: frio     ⇔ (score < 4)",
  ]),
  apaPara(
    "El score máximo posible es 9 (todas las variables verdaderas). Las reglas siguen siendo proposicionales —usan conectores ⇔ y la conjunción implícita en los rangos— pero ahora la decisión depende de un valor numérico calculado por una sumatoria, lo que en programación se traduce en una estructura de iteración o en una expresión aritmética directa."
  ),

  h3("Pseudocódigo"),
  ...codeBlock([
    "ALGORITMO  ClasificarCliente_Scoring",
    "ENTRADA:   p, q, r, s     (booleanos)",
    "SALIDA:    categoria, score",
    "INICIO",
    "  pesos ← [3, 3, 2, 1]",
    "  variables ← [p, q, r, s]",
    "  score ← 0",
    "  PARA i DESDE 0 HASTA 3 HACER",
    "      SI variables[i] = True ENTONCES",
    "          score ← score + pesos[i]",
    "      FIN_SI",
    "  FIN_PARA",
    "  SI score ≥ 7 ENTONCES",
    "      categoria ← \"CALIENTE\"",
    "  SINO SI score ≥ 4 ENTONCES",
    "      categoria ← \"TIBIO\"",
    "  SINO",
    "      categoria ← \"FRÍO\"",
    "  FIN_SI",
    "  RETORNAR categoria, score",
    "FIN",
  ]),

  h3("Diagrama de flujo"),
  ...image("03_flujo_alt2.png", 460, 600, "Figura 3. Diagrama de flujo de la Alternativa 2 con scoring ponderado. La novedad respecto a la Alternativa 1 es la caja de cálculo del puntaje y el uso de comparaciones numéricas."),

  h3("Estructuras de control utilizadas"),
  bullet("Estructura iterativa (PARA ... HACER): recorre las variables proposicionales para calcular el score sin escribir cuatro condicionales separadas."),
  bullet("Estructura condicional anidada (SI ... SINO SI ... SINO): clasifica con base en los rangos numéricos del puntaje."),
  bullet("Arreglos (pesos, variables): permiten parametrizar el sistema sin tocar el código si la empresa decide cambiar la importancia de cada criterio."),

  // ---------- ALTERNATIVA 3 ----------
  h2("Alternativa 3 — Chatbot híbrido con reglas lógicas y agente de IA"),

  h3("Descripción"),
  apaPara(
    "La tercera alternativa combina lo mejor de las dos anteriores con un modelo de inteligencia artificial conversacional, similar a Gemini o ChatGPT. La idea es que las reglas lógicas resuelvan los casos claros (clientes obviamente calientes o claramente fríos) y que solo cuando el resultado es ambiguo —típicamente un cliente tibio— se active un agente de IA que conversa con el cliente, le hace preguntas abiertas y reinterpreta la respuesta. Por ejemplo, si un cliente respondió que no tiene la cuota inicial, el agente le puede preguntar si está abierto a un crédito, descubrir que sí, y reclasificarlo como caliente. Esta alternativa es la más sofisticada y la que ofrece mejor experiencia al usuario, pero también es la más costosa de implementar."
  ),

  h3("Reglas condicionales del orquestador"),
  ...codeBlock([
    "Regla principal (lógica + IA):",
    "  caliente ⇔ (p ∧ q ∧ r ∧ s) ∨",
    "             (resultado_LLM = \"calificado\")",
    "  tibio    ⇔ (p ∧ q ∧ r ∧ ¬s) ∧",
    "             (resultado_LLM ≠ \"frio\")",
    "  frio     ⇔ ¬caliente ∧ ¬tibio",
  ]),
  apaPara(
    "La novedad es la disyunción (∨): basta con que las reglas booleanas o el agente de IA confirmen al cliente como calificado para que sea clasificado como caliente. Esto permite recuperar clientes que las reglas estrictas habrían descartado."
  ),

  h3("Pseudocódigo"),
  ...codeBlock([
    "ALGORITMO  ClasificarCliente_Hibrido",
    "ENTRADA:   p, q, r, s     (booleanos)",
    "SALIDA:    categoria",
    "INICIO",
    "  SI (p Y q Y r Y s) ENTONCES",
    "      categoria ← \"CALIENTE\"   // caso obvio",
    "  SINO SI (NO p) Y (NO q) ENTONCES",
    "      categoria ← \"FRÍO\"       // caso descartado",
    "  SINO",
    "      // caso ambiguo: activar agente de IA",
    "      respuesta ← AgenteLLM(\"hazle más preguntas al cliente\")",
    "      SI respuesta = \"calificado\" ENTONCES",
    "          categoria ← \"CALIENTE\"",
    "      SINO SI respuesta = \"posible\" ENTONCES",
    "          categoria ← \"TIBIO\"",
    "      SINO",
    "          categoria ← \"FRÍO\"",
    "      FIN_SI",
    "  FIN_SI",
    "  Registrar(\"log_conversacion\", categoria)",
    "  RETORNAR categoria",
    "FIN",
  ]),

  h3("Diagrama de flujo"),
  ...image("04_flujo_alt3.png", 480, 660, "Figura 4. Diagrama de flujo de la Alternativa 3 híbrida. El agente de IA solo se invoca cuando las reglas booleanas no dan una respuesta clara, optimizando el costo de cómputo."),

  h3("Estructuras de control utilizadas"),
  bullet("Condicional anidada con tres ramas: separa los casos obvios (caliente, frío) del caso ambiguo que requiere IA."),
  bullet("Llamada a una función externa (AgenteLLM): introduce la noción de modularidad, donde una parte del trabajo se delega a otro programa."),
  bullet("Operador lógico O (OR) en la regla principal: amplía las posibilidades de calificar a un cliente combinando dos fuentes de decisión."),
  bullet("Registro de eventos (Registrar): guarda cada conversación para auditoría posterior y para reentrenar el modelo."),

  // ---------- COMPARACIÓN ----------
  h2("Comparación de las tres alternativas"),
  apaPara(
    "La Tabla 1 sintetiza las diferencias entre las tres alternativas desde la perspectiva de un estudiante de primer semestre que apenas está conociendo la lógica matemática y los primeros conceptos de programación."
  ),
  new Paragraph({
    spacing: { before: 240, after: 120, line: 360 },
    children: [bold("Tabla 1"), italic("  Comparación entre las tres alternativas propuestas")],
  }),
  buildTable(
    ["Criterio", "Alternativa 1\nReglas booleanas", "Alternativa 2\nScoring ponderado", "Alternativa 3\nHíbrido + IA"],
    [
      ["Complejidad lógica", "Baja: tres reglas con conjunción y negación", "Media: suma ponderada y comparación numérica", "Alta: combina reglas, función externa y disyunción"],
      ["Estructuras de control", "SI / SINO / SINO SI", "PARA + SI anidado", "SI anidado + llamada a función"],
      ["Tabla de verdad", "16 filas exactas (2⁴ casos)", "10 niveles posibles (score 0-9)", "16 filas + ramas adicionales del LLM"],
      ["Predictibilidad", "Total — siempre la misma respuesta", "Alta — depende del puntaje exacto", "Media — el LLM puede dar respuestas distintas"],
      ["Costo de implementación", "Muy bajo (un día de desarrollo)", "Bajo (dos a tres días)", "Alto (semanas + costo por API)"],
      ["Innovación", "Mínima — es lógica clásica", "Media — concepto de scoring", "Alta — IA generativa integrada"],
      ["Mejor para...", "Empresas que recién empiezan", "Empresas con mucho volumen", "Empresas que quieren UX premium"],
    ],
    [1700, 2400, 2400, 2860]
  ),

  // ---------- CONCLUSIÓN ----------
  h2("Selección recomendada y justificación"),
  apaPara(
    "Para la empresa inmobiliaria del escenario, el equipo recomienda comenzar con la Alternativa 2 (scoring ponderado). La razón es práctica: la Alternativa 1 es demasiado rígida y dejaría escapar oportunidades comerciales reales (clientes que no cumplen las cuatro condiciones pero que sí son rentables); la Alternativa 3 es la más completa pero requiere un presupuesto y un equipo técnico que la inmobiliaria probablemente no tiene en su primera fase. La Alternativa 2 ofrece el mejor balance entre rigor lógico, flexibilidad y costo, y se puede implementar en menos de una semana usando lenguajes accesibles como Python o JavaScript. Cuando la empresa madure y crezca, podrá evolucionar hacia la Alternativa 3 sin reescribir el sistema desde cero, simplemente agregando el agente de IA en la rama del cliente tibio."
  ),
  apaPara(
    "Esta progresión también tiene un valor pedagógico: las tres alternativas usan los mismos conceptos de lógica matemática (proposiciones, conectores, tablas de verdad, reglas condicionales), pero los aplican con creciente sofisticación. El estudiante que entiende la Alternativa 1 puede comprender la Alternativa 2 sumando el concepto de variables ponderadas; quien entiende la Alternativa 2 puede llegar a la Alternativa 3 incorporando la idea de delegar decisiones complejas a un módulo externo. Así, el ejercicio demuestra cómo la lógica proposicional sigue siendo la base incluso de los sistemas de inteligencia artificial más avanzados."
  ),
];

// ===========================================================================
// MAIN
// ===========================================================================
const doc = new Document({
  creator: "Sharon León — Raquel Merlano — Angie Pérez — Cristhian Prieto",
  title: "Alternativa innovadora — Lógica Matemática",
  description: "Bloque c de la Actividad 1 de Lógica Matemática y Programación",
  styles: {
    default: { document: { run: { font: FONT, size: SIZE_BODY } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: SIZE_H1, bold: true, font: FONT },
        paragraph: { spacing: { before: 360, after: 180, line: 360 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: SIZE_H2, bold: true, font: FONT },
        paragraph: { spacing: { before: 300, after: 120, line: 360 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: SIZE_H3, bold: true, italics: true, font: FONT },
        paragraph: { spacing: { before: 200, after: 80, line: 360 }, outlineLevel: 2 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
        ],
      },
    ],
  },
  sections: [{
    properties: {
      page: { size: { width: 12240, height: 15840 },
              margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({
            text: "Lógica Matemática y Programación — Actividad 1 — bloque c",
            font: FONT, size: 20, italics: true, color: "595959",
          })],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "Página ", font: FONT, size: 20 }),
            new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 20 }),
            new TextRun({ text: " — Compensar 2026", font: FONT, size: 20 }),
          ],
        })],
      }),
    },
    children: contenido,
  }],
});

const out = path.resolve(__dirname, "..", "Bloque_C_Alternativas_Innovadoras_Logica.docx");
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(out, buffer);
  console.log("OK ->", out, "size:", buffer.length, "bytes");
});
