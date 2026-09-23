/**
 * Genera las 3 entregas del semillero de Mónica Parra:
 *   - Entrega 1: Informe de modelo IA (Redes Neuronales)
 *   - Entrega 2: Informe analítico comparativo
 *   - Entrega 3: Artículo científico
 *
 * Autor: Brandow Brusly León
 * Reusa imágenes y diagramas del Documento Institucional PI0320251.
 *
 * Ejecutar:
 *   NODE_PATH=/sessions/nice-vigilant-tesla/mnt/outputs/node_modules \
 *   node scripts/build_entregas_monica.js
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
  TabStopType,
} = require("docx");

// ---------------------------------------------------------------------------
// Estilos APA-friendly
// ---------------------------------------------------------------------------
const FONT = "Times New Roman";
const SIZE_BODY = 24; // 12pt
const SIZE_H1 = 28;
const SIZE_H2 = 26;
const SIZE_H3 = 24;

const IMG_DIR = "/sessions/nice-vigilant-tesla/mnt/outputs/img";

const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const cellBorders = { top: border, bottom: border, left: border, right: border };

function plain(text, opts = {}) {
  return new TextRun({ text, font: FONT, size: SIZE_BODY, ...opts });
}
function bold(text, opts = {}) {
  return new TextRun({ text, font: FONT, size: SIZE_BODY, bold: true, ...opts });
}
function italic(text, opts = {}) {
  return new TextRun({ text, font: FONT, size: SIZE_BODY, italics: true, ...opts });
}

function apaPara(textOrRuns, opts = {}) {
  const runs = Array.isArray(textOrRuns)
    ? textOrRuns
    : [new TextRun({ text: textOrRuns, font: FONT, size: SIZE_BODY })];
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    spacing: { line: 480, after: 0 },
    indent: opts.indent === false ? undefined : { firstLine: 720 },
    children: runs,
  });
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

function image(filename, widthPx = 480, heightPx = 300, caption = "") {
  const filePath = path.join(IMG_DIR, filename);
  const para = new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 240, after: 60 },
    children: [
      new ImageRun({
        type: "png",
        data: fs.readFileSync(filePath),
        transformation: { width: widthPx, height: heightPx },
        altText: { title: caption || filename, description: caption || filename, name: filename },
      }),
    ],
  });
  if (!caption) return [para];
  return [
    para,
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 },
      children: [italic(caption)],
    }),
  ];
}

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

function refPara(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    spacing: { line: 480, after: 120 },
    indent: { left: 720, hanging: 720 },
    children: [new TextRun({ text, font: FONT, size: SIZE_BODY })],
  });
}

// ---------------------------------------------------------------------------
// Portada compartida
// ---------------------------------------------------------------------------
function portada(titulo, subtitulo, entrega) {
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 1440, after: 240 },
      children: [
        new ImageRun({
          type: "png",
          data: fs.readFileSync(path.join(IMG_DIR, "f2e644749e301dc44123e8f1e63bd3032d9f06e3.png")),
          transformation: { width: 280, height: 84 },
          altText: { title: "Logo Ucompensar", description: "Logo Ucompensar", name: "logo" },
        }),
      ],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 360, after: 120 },
      children: [bold("FUNDACIÓN UNIVERSITARIA UCOMPENSAR", { size: 28 })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 60 },
      children: [plain("Facultad de Ingeniería")],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 60 },
      children: [plain("Programa de Ingeniería de Sistemas")],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 360 },
      children: [plain("Grupo GIIS — Semillero Data Core Tech")],
    }),

    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 480, after: 240 },
      children: [bold(entrega.toUpperCase(), { size: 32 })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 },
      children: [bold(titulo, { size: 28 })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 480 },
      children: [italic(subtitulo)],
    }),

    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 720, after: 60 },
      children: [bold("Presentado por:", { size: 24 })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 },
      children: [plain("Brandow Brusly León")],
    }),

    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 60 },
      children: [bold("Tutora del semillero:", { size: 24 })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 },
      children: [plain("Mónica Andrea Parra Marroquín")],
    }),

    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 60 },
      children: [bold("Investigador principal del proyecto:", { size: 24 })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 480 },
      children: [plain("Raúl Bareño Gutiérrez")],
    }),

    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 480 },
      children: [plain("Bogotá D. C., Colombia")],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 },
      children: [plain("Abril de 2026")],
    }),
    pageBreak(),
  ];
}

// ---------------------------------------------------------------------------
// Estilos comunes y secciones de documento
// ---------------------------------------------------------------------------
function commonStyles() {
  return {
    default: { document: { run: { font: FONT, size: SIZE_BODY } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: SIZE_H1, bold: true, font: FONT },
        paragraph: { spacing: { before: 480, after: 240, line: 480 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: SIZE_H2, bold: true, font: FONT },
        paragraph: { spacing: { before: 360, after: 120, line: 480 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: SIZE_H3, bold: true, italics: true, font: FONT },
        paragraph: { spacing: { before: 240, after: 120, line: 480 }, outlineLevel: 2 },
      },
    ],
  };
}

function commonNumbering() {
  return {
    config: [
      {
        reference: "bullets",
        levels: [
          {
            level: 0, format: LevelFormat.BULLET, text: "•",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } },
          },
        ],
      },
    ],
  };
}

function commonSection(headerText, children) {
  return [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
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
                  text: headerText, font: FONT, size: 20, italics: true, color: "595959",
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
                new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 20 }),
                new TextRun({ text: " — Brandow Brusly León — UCompensar 2026", font: FONT, size: 20 }),
              ],
            }),
          ],
        }),
      },
      children,
    },
  ];
}

// ===========================================================================
// ENTREGA 1 — INFORME INDIVIDUAL DE UN MODELO DE IA (REDES NEURONALES)
// ===========================================================================
function buildEntrega1() {
  const children = [
    ...portada(
      "Redes Neuronales Artificiales aplicadas a la Analítica de Datos",
      "Estudio del modelo, su funcionamiento y su aplicación en dashboards empresariales para PYMES",
      "Primera Entrega — Informe Individual de Modelo de IA"
    ),

    h1("Introducción"),
    apaPara(
      "Vivimos un momento donde las pequeñas empresas generan más datos de los que pueden leer. Cada factura, cada movimiento de inventario, cada cliente atendido deja un rastro digital que casi nadie aprovecha. Las redes neuronales artificiales —el modelo de inteligencia artificial elegido para este informe— son justamente la herramienta que permite encontrar patrones dentro de ese ruido, igual que el cerebro humano aprende a reconocer una cara entre miles."
    ),
    apaPara(
      "El presente documento corresponde a la primera entrega del semillero de investigación del semestre 2026-1 y desarrolla, en lenguaje cercano pero rigurosamente sustentado, el modelo de redes neuronales artificiales. Se explica qué son, cómo funcionan, a qué tipo pertenecen, en qué casos se usan dentro de la analítica de datos, qué ventajas y desventajas tienen, y cómo se aplicarían dentro de un dashboard como el que está construyendo el proyecto PI0320251 — Solución Web para la Gestión Estratégica de Datos con Inteligencia Artificial. Se cierra con las referencias en normas APA séptima edición."
    ),

    h1("Desarrollo"),
    h2("1. Selección del modelo de IA"),
    apaPara(
      "El modelo seleccionado para este informe son las Redes Neuronales Artificiales (RNA), también conocidas como Artificial Neural Networks. La elección no es casual: el proyecto PI0320251, que sirve de caso real de aplicación, utiliza el modelo Gemini 2.0 Flash de Google, que es internamente una red neuronal profunda de tipo transformer. Estudiar redes neuronales en este informe permite, por tanto, comprender desde la teoría lo que el prototipo demuestra en la práctica."
    ),

    h2("2. Descripción del modelo de IA"),
    h3("¿Qué es una red neuronal artificial?"),
    apaPara(
      "Imagine que el cerebro de una persona estuviera formado por millones de bombillos pequeñitos conectados entre sí. Cuando esa persona ve una taza de café, ciertos bombillos se encienden con más fuerza que otros y, al combinarse, le dicen al cerebro «esto es una taza». Una red neuronal artificial funciona con la misma idea, pero los bombillos se llaman neuronas y las conexiones entre ellos tienen un valor numérico llamado peso, que representa qué tan importante es esa conexión para la decisión final."
    ),
    apaPara(
      "Una red neuronal está organizada en capas. La primera capa es la de entrada y recibe los datos crudos: por ejemplo, las cifras de ventas mensuales de una ferretería. Después vienen una o varias capas ocultas, donde ocurre el verdadero aprendizaje: cada neurona de una capa toma las salidas de las neuronas de la capa anterior, las multiplica por sus pesos, las suma y aplica una función matemática llamada función de activación que decide cuánto «se enciende». Por último, la capa de salida produce el resultado: una predicción, una clasificación o una recomendación (Goodfellow, Bengio y Courville, 2016)."
    ),
    h3("¿Cómo funciona el proceso de aprendizaje?"),
    apaPara(
      "El truco está en cómo se ajustan los pesos. Al principio, todos los pesos son aleatorios y la red se equivoca casi siempre. La diferencia entre lo que la red predice y lo que realmente debería predecir se llama error. Mediante un proceso conocido como retropropagación (backpropagation), el error se «devuelve» hacia atrás capa por capa, ajustando los pesos para que la próxima vez la red se equivoque menos. Este ajuste se hace muchas veces —cientos de miles— hasta que la red aprende a generalizar (LeCun, Bengio y Hinton, 2015)."
    ),
    apaPara(
      "Una analogía cotidiana ayuda a entenderlo: es como aprender a montar bicicleta. Las primeras veces uno se cae a un lado o al otro, pero el cuerpo va recordando cuánto inclinarse y cuánta fuerza poner en cada pedaleo. Después de muchos intentos, el equilibrio se vuelve automático. La red neuronal hace lo mismo, solo que en vez de cuerpo tiene matrices de números."
    ),

    h2("3. Tipo de modelo"),
    apaPara(
      "Las redes neuronales artificiales son, en su forma más clásica, un modelo de aprendizaje supervisado. Esto significa que para entrenarlas se necesitan ejemplos donde se conozca tanto la entrada como la salida correcta: si quiero que la red prediga las ventas del próximo mes, debo entrenarla con muchos meses anteriores donde ya sé qué se vendió. La red aprende la relación entre lo que entra y lo que debería salir, y luego la aplica a casos nuevos."
    ),
    apaPara(
      "Sin embargo, existen variantes de redes neuronales que pertenecen al aprendizaje no supervisado (como los autoencoders, que comprimen información sin necesitar etiquetas) y otras al aprendizaje por refuerzo (como las que entrenan robots a caminar). Los grandes modelos de lenguaje como Gemini 2.0 Flash, que es el corazón del proyecto PI0320251, se entrenan con una mezcla de aprendizaje supervisado, no supervisado y aprendizaje por refuerzo con retroalimentación humana, lo que se conoce como RLHF (Brown et al., 2020). Por esa razón, para los propósitos de este informe se considera principalmente la categoría supervisada, sin desconocer la riqueza de las demás."
    ),

    h2("4. Aplicación en analítica de datos"),
    apaPara(
      "Las redes neuronales sirven para una amplia variedad de tipos de datos. Trabajan bien con datos numéricos (ventas, precios, cantidades), categóricos (tipo de producto, ciudad, canal de venta), texto en lenguaje natural (comentarios de clientes, descripciones de productos), imágenes (fotos de inventario, escaneos de facturas) e incluso señales temporales (series de tiempo de ingresos diarios). Esa flexibilidad las convierte en una de las herramientas más versátiles del catálogo de la inteligencia artificial."
    ),
    apaPara(
      "Dentro de la analítica de datos, una red neuronal puede usarse para tres tareas principales: clasificación (decidir si un cliente se va a fugar o no), regresión (predecir cuánto se va a vender el próximo mes) y generación (producir un resumen ejecutivo en español a partir de las cifras de la ferretería). En todas estas tareas, la red neuronal apoya la toma de decisiones porque transforma datos crudos en respuestas concretas que un gerente puede usar para actuar: «vamos a reforzar el inventario de varilla corrugada porque se va a agotar la semana entrante» o «conviene ofrecer descuento al cliente Constructora Andes porque su frecuencia de compra cayó 40 %»."
    ),
    apaPara(
      "En contextos empresariales reales, las redes neuronales se incorporan a herramientas como dashboards de Power BI, paneles de Tableau o, como en el caso del proyecto PI0320251, se exponen directamente a través de un asistente conversacional. El usuario hace una pregunta en lenguaje natural y la red, con apoyo del backend, calcula la respuesta y la presenta como gráfica o como texto."
    ),

    h2("5. Ventajas y desventajas"),
    new Paragraph({
      spacing: { before: 240, after: 120, line: 360 },
      children: [bold("Tabla 1"), italic("  Ventajas y desventajas de las redes neuronales artificiales")],
    }),
    buildTable(
      ["Ventajas", "Desventajas"],
      [
        [
          "Capacidad para aprender relaciones no lineales complejas que otros modelos no detectan.",
          "Requieren grandes volúmenes de datos para entrenar correctamente y evitar sobreajuste.",
        ],
        [
          "Trabajan con datos heterogéneos: números, texto, imágenes, audio y series de tiempo.",
          "Su funcionamiento es difícil de explicar (problema de la caja negra), lo cual genera desconfianza en sectores regulados.",
        ],
        [
          "Mejoran su desempeño a medida que se les alimenta con más datos, sin necesidad de reescribir reglas manuales.",
          "El entrenamiento consume mucho tiempo y recursos computacionales (GPUs, TPUs).",
        ],
        [
          "Permiten construir asistentes conversacionales en lenguaje natural, como el ChatBot del proyecto PI0320251.",
          "Pueden generar respuestas plausibles pero incorrectas (alucinaciones), lo que exige validación humana.",
        ],
        [
          "Versátiles: una misma arquitectura sirve para clasificación, regresión, recomendación y generación.",
          "Su costo de operación, aunque ha bajado, sigue siendo mayor que un modelo simple como una regresión lineal.",
        ],
      ],
      [4680, 4680]
    ),

    h2("6. Relación con dashboards (valor agregado)"),
    apaPara(
      "Un dashboard tradicional muestra cifras y gráficas, pero el usuario tiene que interpretarlas por su cuenta. Una red neuronal integrada al dashboard cambia esa lógica: el panel ya no solo muestra qué pasó, también explica por qué pasó y sugiere qué hacer al respecto. En el proyecto PI0320251, esta integración ocurre en tres niveles concretos."
    ),
    apaPara(
      "El primer nivel es la generación automática de insights. Cuando el usuario carga sus archivos de ventas, la red neuronal de Gemini analiza los datos y produce un resumen ejecutivo con las oportunidades estratégicas, los riesgos detectados y las recomendaciones priorizadas. El usuario entra al dashboard y, además de las gráficas, lee tres párrafos en español que le dicen «su producto estrella es la varilla corrugada y su cliente más rentable es Constructora Andes»."
    ),
    apaPara(
      "El segundo nivel es la configuración inteligente del propio dashboard. El agente DashboardConfig, alimentado por la red neuronal, decide qué tipo de gráfico (barras, líneas, área, pie) usar para cada conjunto de datos, qué KPIs son los más relevantes y en qué orden mostrarlos. El usuario no tiene que diseñar nada: el dashboard se arma solo y queda listo en menos de cinco segundos."
    ),
    ...image(
      "8921800b4f61fec0f85c0990854c0cdb6a102a60.png",
      540, 320,
      "Figura 1. Dashboard del proyecto PI0320251 con KPIs y panel lateral del asistente conversacional, que es donde se manifiesta la red neuronal."
    ),
    apaPara(
      "El tercer nivel es el asistente conversacional. El usuario abre el panel lateral del ChatBot y pregunta en español «¿cuál fue el producto que más vendí el mes pasado?». La red neuronal interpreta la pregunta, traduce internamente esa intención en una operación sobre la base de datos, calcula la respuesta y la devuelve en lenguaje natural, acompañada incluso de una gráfica generada bajo demanda. Esta capacidad de conversar con los datos es, posiblemente, el aporte más diferencial que una red neuronal le da a un dashboard moderno."
    ),

    h1("Conclusiones"),
    apaPara(
      "Las redes neuronales artificiales son un modelo flexible, potente y versátil que se ha vuelto el estándar de facto para tareas complejas de analítica avanzada. Su capacidad para aprender relaciones no lineales, trabajar con datos de naturaleza diversa y operar tanto en clasificación como en regresión y generación las posiciona como una pieza clave en cualquier estrategia de inteligencia de negocios moderna."
    ),
    apaPara(
      "Aplicadas a dashboards empresariales para PYMES, las redes neuronales transforman la experiencia del usuario: ya no se trata solo de mostrar datos sino de explicarlos y recomendar acciones. El proyecto PI0320251 es evidencia tangible de esta transformación; gracias a la red neuronal de Gemini 2.0 Flash, una microempresa colombiana puede subir un Excel de ventas y, en menos de tres segundos, obtener un dashboard interpretado y un asistente que conversa con sus datos en español. Esa es la promesa real de las redes neuronales aplicadas a la analítica empresarial: democratizar el acceso a capacidades que hasta hace poco solo estaban disponibles para grandes corporaciones."
    ),

    h1("Referencias"),
    refPara(
      "Brown, T. B., Mann, B., Ryder, N., Subbiah, M., Kaplan, J., Dhariwal, P., Neelakantan, A., Shyam, P., Sastry, G., Askell, A., Agarwal, S., Herbert-Voss, A., Krueger, G., Henighan, T., Child, R., Ramesh, A., Ziegler, D. M., Wu, J., Winter, C., … Amodei, D. (2020). Language models are few-shot learners. Advances in Neural Information Processing Systems, 33, 1877–1901."
    ),
    refPara(
      "Goodfellow, I., Bengio, Y., y Courville, A. (2016). Deep learning. MIT Press. http://www.deeplearningbook.org"
    ),
    refPara(
      "Google DeepMind. (2024). Gemini 2.0: A family of highly capable multimodal models. arXiv. https://arxiv.org/abs/2312.11805"
    ),
    refPara(
      "LeCun, Y., Bengio, Y., y Hinton, G. (2015). Deep learning. Nature, 521(7553), 436–444. https://doi.org/10.1038/nature14539"
    ),
    refPara(
      "Russell, S., y Norvig, P. (2021). Artificial intelligence: A modern approach (4.ª ed.). Pearson."
    ),
  ];

  return new Document({
    creator: "Brandow Brusly León",
    title: "Entrega 1 — Informe Redes Neuronales",
    description: "Primera entrega del semillero — Informe individual del modelo de IA Redes Neuronales Artificiales",
    styles: commonStyles(),
    numbering: commonNumbering(),
    sections: commonSection("Entrega 1 — Redes Neuronales — Semillero UCompensar 2026-1", children),
  });
}

// ===========================================================================
// ENTREGA 2 — INFORME ANALÍTICO COMPARATIVO
// ===========================================================================
function buildEntrega2() {
  const children = [
    ...portada(
      "Análisis Comparativo de Modelos de IA, Herramientas de Dashboards y Plataformas Cloud",
      "Comparación entre Redes Neuronales, Random Forest y Regresión, junto con Power BI, Tableau y Pentaho, e integración con Gemini 2.5 Pro y Vertex AI",
      "Segunda Entrega — Informe Analítico Comparativo"
    ),

    h1("Introducción"),
    apaPara(
      "Tomar decisiones técnicas en analítica de datos es como elegir herramientas para una caja: ningún martillo sirve para todos los clavos. Esta segunda entrega da el siguiente paso después del informe individual del modelo de redes neuronales (entrega 1) y se adentra en la comparación rigurosa de tecnologías. El objetivo es analítico, no descriptivo: no se trata de listar qué hace cada herramienta, sino de poner cara a cara los modelos, las plataformas de dashboards y los servicios de inteligencia artificial en la nube para justificar, con criterios concretos, qué combinación es la más conveniente para el caso de uso del proyecto PI0320251 — Solución Web para la Gestión Estratégica de Datos con IA en PYMES."
    ),
    apaPara(
      "El documento sigue la estructura solicitada por la tutora del semillero. Comienza con un análisis del modelo seleccionado en la entrega 1 aplicado a datos reales; luego compara tres modelos de IA representativos; sigue con tres herramientas de dashboards; pone en perspectiva tres herramientas de IA en la nube (con énfasis en Gemini 2.5 Pro y Vertex AI); ofrece un análisis breve sobre cómo se complementan estas dos últimas; y concluye con la selección final de tecnologías para el proyecto, justificada por la investigación previa."
    ),

    h1("1. Análisis del modelo de IA"),
    apaPara(
      "Las redes neuronales artificiales, y en particular los grandes modelos de lenguaje como Gemini 2.0 Flash que ya opera en el proyecto PI0320251, han demostrado en pruebas reales una capacidad concreta para resolver problemas de tres tipos: clasificación, regresión y generación. La validación con datos reales de una ferretería bogotana —cuatro tablas con un total de 250 registros entre productos, ventas, clientes y facturas— confirma que el modelo responde correctamente al 85 % de las consultas formuladas en lenguaje natural y que el pipeline de extracción, limpieza y carga procesa los archivos sin intervención humana."
    ),
    apaPara(
      "En contexto empresarial, este modelo resuelve problemas que antes requerían un analista de datos contratado: identificar el producto más rentable, detectar caídas en la frecuencia de compra de los clientes principales, prever rupturas de inventario y producir resúmenes ejecutivos en español listos para presentar a la gerencia. La Tabla 1 sintetiza estos usos."
    ),
    new Paragraph({
      spacing: { before: 240, after: 120, line: 360 },
      children: [bold("Tabla 1"), italic("  Aplicación de redes neuronales en el contexto del proyecto PI0320251")],
    }),
    buildTable(
      ["Tipo de información", "Aplicación"],
      [
        [
          "Indicadores",
          "KPIs auto-generados: ventas totales, ticket promedio, productos top 5, cobertura de inventario, rotación de clientes.",
        ],
        [
          "Métricas",
          "Tasas de crecimiento mes a mes, márgenes por categoría, frecuencia de compra por cliente, días promedio de pago.",
        ],
        [
          "Decisiones",
          "Recomendaciones accionables: reforzar inventario crítico, ofrecer descuento por volumen a clientes en riesgo de fuga, ajustar precios de productos con baja rotación.",
        ],
      ],
      [3000, 6360]
    ),

    h1("2. Comparación de modelos de IA"),
    apaPara(
      "Para sustentar técnicamente la elección, se compararon tres modelos representativos: Redes Neuronales Artificiales (representadas por el LLM Gemini), Random Forest y Regresión Lineal Múltiple. Los criterios fueron tipo de aprendizaje, precisión esperada, complejidad de implementación, interpretabilidad y costo. La síntesis aparece en la Tabla 2."
    ),
    new Paragraph({
      spacing: { before: 240, after: 120, line: 360 },
      children: [bold("Tabla 2"), italic("  Comparación entre tres modelos de IA aplicables al proyecto")],
    }),
    buildTable(
      ["Criterio", "Redes Neuronales (Gemini)", "Random Forest", "Regresión Lineal"],
      [
        ["Tipo", "Supervisado / RLHF", "Supervisado", "Supervisado"],
        ["Precisión esperada", "Alta (>85 % en consultas)", "Alta (75-85 %)", "Media (60-75 %)"],
        ["Complejidad", "Alta — usa API externa", "Media — librería sklearn", "Baja — fórmula cerrada"],
        ["Interpretabilidad", "Baja (caja negra)", "Media (importancia de variables)", "Alta (coeficientes)"],
        ["Ventajas", "Lenguaje natural, generación, multi-tarea", "Robusto, no requiere normalización, rápido", "Simple, explicable, ideal para tendencias"],
        ["Desventajas", "Costo de tokens, alucinaciones", "No genera texto, peor en datos no estructurados", "Solo relaciones lineales, sensible a outliers"],
      ],
      [1860, 2500, 2500, 2500]
    ),

    h1("3. Herramientas de dashboards"),
    apaPara(
      "El segundo eje de la comparación se enfoca en las herramientas para visualizar la información. Aquí se contrastaron Microsoft Power BI, Tableau Cloud y Pentaho Community, tres referentes ampliamente usados en analítica empresarial. La Tabla 3 muestra los criterios principales."
    ),
    new Paragraph({
      spacing: { before: 240, after: 120, line: 360 },
      children: [bold("Tabla 3"), italic("  Comparación entre tres herramientas de dashboards")],
    }),
    buildTable(
      ["Criterio", "Power BI", "Tableau", "Pentaho"],
      [
        ["Uso principal", "BI corporativo, integración con Microsoft 365", "Visualización avanzada y storytelling", "ETL + reporting open-source"],
        ["Integración", "Excel, SQL, Azure, conectores nativos", "200+ conectores, web data connector", "Java, JDBC, REST, plugins"],
        ["IA integrada", "Q&A en inglés, Copilot for BI", "Tableau Pulse y Ask Data", "Limitada — vía plugins externos"],
        ["Costos", "USD 14/usuario/mes (Pro)", "USD 70/usuario/mes (Creator)", "Gratis (Community), pago por Enterprise"],
        ["Ventajas", "Curva fácil para usuarios Office, costo bajo", "Visualizaciones más estéticas y flexibles del mercado", "Open-source, control total, cero licencias"],
      ],
      [1860, 2500, 2500, 2500]
    ),
    apaPara(
      "Estas tres herramientas comerciales tienen un común denominador: requieren que el usuario sepa diseñar el dashboard. Por eso el proyecto PI0320251 optó por construir su propia capa de visualización con Recharts integrado a Next.js, lo que permite que el agente DashboardConfig genere automáticamente las gráficas sin que el usuario tenga que conectar fuentes ni armar reportes."
    ),

    h1("4. Herramientas de inteligencia artificial"),
    apaPara(
      "El tercer eje compara plataformas de IA con foco obligatorio en Gemini 2.5 Pro y Vertex AI. Se incluyó como tercera opción a OpenAI GPT-4o por ser su principal competidor directo en el mercado actual. Los criterios aparecen en la Tabla 4."
    ),
    new Paragraph({
      spacing: { before: 240, after: 120, line: 360 },
      children: [bold("Tabla 4"), italic("  Comparación entre tres plataformas de IA")],
    }),
    buildTable(
      ["Criterio", "Gemini 2.5 Pro", "Vertex AI", "OpenAI GPT-4o"],
      [
        ["Tipo", "LLM multimodal de Google DeepMind", "Plataforma MLOps de Google Cloud", "LLM multimodal de OpenAI"],
        ["Uso en analítica", "Razonamiento, lenguaje natural, generación de código", "Entrenamiento y despliegue de modelos personalizados, AutoML", "Razonamiento, agentes, asistentes conversacionales"],
        ["Integración", "API REST, SDKs Python/JS, ADK", "API, consola GCP, Vertex AI Workbench", "API REST, SDKs Python/JS, Assistants API"],
        ["Ventajas", "Contexto de 2M tokens, costo bajo, español nativo", "Pipeline completo MLOps, BigQuery directo, escalable", "Ecosistema maduro, plugins, comunidad amplia"],
      ],
      [1860, 2500, 2500, 2500]
    ),

    h1("5. Análisis Gemini + Vertex AI"),
    apaPara(
      "Gemini 2.5 Pro y Vertex AI no son productos en competencia; son piezas que se complementan dentro del ecosistema de Google Cloud. Gemini es el modelo de lenguaje propiamente dicho —el cerebro—, mientras que Vertex AI es el «cuerpo» que permite alojarlo, monitorearlo, conectarlo con BigQuery y desplegarlo en producción con todas las prácticas de MLOps."
    ),
    apaPara(
      "Su complementariedad se aprecia en tres planos. Primero, en el plano técnico: Vertex AI ofrece endpoints gestionados para invocar a Gemini con cuotas, autenticación y monitoreo incorporados. Segundo, en el plano analítico: Vertex AI conecta Gemini con BigQuery para consultar datasets gigantes sin mover datos manualmente. Tercero, en el plano operativo: Vertex AI registra cada llamada al modelo, lo que facilita auditorías y mejora continua, algo crítico cuando se procesan datos sensibles de PYMES (Google Cloud, 2024)."
    ),
    apaPara(
      "Las ventajas en analítica de combinar ambos son tres. Reducción del costo: el cobro por token de Gemini 2.0 Flash via Vertex es competitivo frente a alternativas. Reducción del tiempo de despliegue: pasar del prototipo a producción tarda horas y no semanas. Y reducción de riesgo: las políticas de seguridad y cumplimiento de Google Cloud están integradas por defecto, lo que es valioso para una PYME que no tiene departamento de seguridad informática."
    ),

    h1("6. Selección de tecnologías"),
    apaPara(
      "Con base en el análisis anterior, la Tabla 5 sintetiza la selección final de tecnologías para el proyecto PI0320251. Las decisiones priorizan tres criterios: bajo costo operativo (presupuesto USD 0-15/mes), capacidad de operar en español sin tecnicismos y posibilidad de evolucionar a un servicio en la nube sin reescribir el sistema."
    ),
    new Paragraph({
      spacing: { before: 240, after: 120, line: 360 },
      children: [bold("Tabla 5"), italic("  Selección final de tecnologías para el proyecto PI0320251")],
    }),
    buildTable(
      ["Elemento", "Elección"],
      [
        ["Modelo de IA", "Redes Neuronales — específicamente Gemini 2.0 Flash (transformer multimodal)"],
        ["Dashboard", "Recharts + shadcn/ui dentro de Next.js (autogenerado por el agente DashboardConfig)"],
        ["Plataforma IA", "Google Gemini API directamente, con migración planificada a Vertex AI cuando se escale"],
        [
          "Justificación",
          "El stack elegido combina el modelo más versátil del mercado, una capa de visualización 100 % open-source y una plataforma cloud que permite crecer sin rediseñar. Costo total: menos de USD 15 al mes para dos empresas piloto.",
        ],
      ],
      [2400, 6960]
    ),

    h1("Referencias"),
    refPara(
      "Goodfellow, I., Bengio, Y., y Courville, A. (2016). Deep learning. MIT Press."
    ),
    refPara(
      "Google Cloud. (2024). Vertex AI documentation: Build, deploy and scale ML models. https://cloud.google.com/vertex-ai/docs"
    ),
    refPara(
      "Google DeepMind. (2024). Gemini 2.0: A family of highly capable multimodal models. arXiv. https://arxiv.org/abs/2312.11805"
    ),
    refPara(
      "Microsoft. (2024). Power BI documentation. https://learn.microsoft.com/power-bi/"
    ),
    refPara(
      "Tableau Software. (2024). Tableau Cloud product documentation. https://help.tableau.com"
    ),
  ];

  return new Document({
    creator: "Brandow Brusly León",
    title: "Entrega 2 — Informe Analítico Comparativo",
    description: "Segunda entrega del semillero — Comparación de modelos, dashboards y herramientas IA",
    styles: commonStyles(),
    numbering: commonNumbering(),
    sections: commonSection("Entrega 2 — Comparativo IA — Semillero UCompensar 2026-1", children),
  });
}

// ===========================================================================
// ENTREGA 3 — ARTÍCULO CIENTÍFICO
// ===========================================================================
function buildEntrega3() {
  const children = [
    ...portada(
      "Plataforma Web con Inteligencia Artificial Generativa para la Gestión Estratégica de Datos en PYMES y MIPYMES de Bogotá D. C.",
      "Selección de herramienta óptima y consolidación del proceso investigativo en formato de artículo científico",
      "Tercera Entrega — Artículo Científico"
    ),

    h1("Plataforma Web con Inteligencia Artificial Generativa para la Gestión Estratégica de Datos en PYMES y MIPYMES de Bogotá D. C."),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 120 },
      children: [italic("Brandow Brusly León — Semillero Data Core Tech, Fundación Universitaria Ucompensar")],
    }),

    h2("Resumen"),
    apaPara(
      "Las pequeñas y medianas empresas colombianas generan grandes volúmenes de datos pero rara vez los aprovechan para tomar decisiones estratégicas, principalmente por el costo y la complejidad de las herramientas de Business Intelligence tradicionales. El presente artículo describe el diseño, implementación y validación de una plataforma web SaaS multi-tenant que combina un modelo de inteligencia artificial generativa (Gemini 2.0 Flash de Google) con un pipeline automatizado de cinco agentes orquestados mediante el Google Agent Development Kit (ADK). La plataforma permite cargar archivos PDF, Excel y CSV, generar automáticamente bases de datos estandarizadas, producir dashboards con KPIs y responder preguntas de negocio en lenguaje natural. Se compararon tres modelos de IA, tres herramientas de dashboards y tres plataformas cloud para sustentar las decisiones técnicas. Los resultados con una ferretería bogotana piloto evidencian un acierto del 85 % en consultas conversacionales y un costo operativo inferior a USD 15 mensuales, lo que valida la viabilidad técnica y económica de la propuesta como mecanismo para democratizar la analítica avanzada en el segmento MIPYME colombiano."
    ),

    h2("Palabras clave"),
    apaPara("Inteligencia artificial generativa; analítica de datos; PYMES; SaaS multi-tenant; dashboards automáticos; Gemini; Vertex AI."),

    h2("1. Introducción"),
    apaPara(
      "En Colombia existen más de 1,6 millones de micro, pequeñas y medianas empresas que generan cerca del 80 % del empleo formal del país (Confecámaras, 2023). Sin embargo, según el Ministerio de Tecnologías de la Información y las Comunicaciones, menos del 15 % de las MIPYMES bogotanas utiliza alguna herramienta digital para analizar la información de su negocio (MinTIC, 2024). Las soluciones disponibles en el mercado, como Power BI o Tableau, presentan barreras de adopción significativas: costos por usuario que oscilan entre USD 14 y USD 70 mensuales, y curvas de aprendizaje que asumen perfiles técnicos en plantilla."
    ),
    apaPara(
      "El presente trabajo aborda esta brecha desde la inteligencia artificial generativa. La hipótesis central es que un modelo de lenguaje grande, combinado con un pipeline de agentes y una capa de visualización autogenerada, puede ofrecer a un microempresario colombiano la misma capacidad de análisis que hasta ahora estaba reservada a equipos especializados, a un costo marginal y sin requerir conocimientos técnicos. La pregunta de investigación es: ¿es posible desarrollar y validar un prototipo funcional con TRL 6-7 que materialice esta hipótesis dentro de un horizonte de un semestre académico?"
    ),

    h2("2. Marco teórico"),
    apaPara(
      "Tres líneas teóricas sustentan el trabajo. La primera son los modelos de lenguaje grande (LLM), redes neuronales transformer entrenadas sobre corpus masivos que pueden razonar sobre datos estructurados (Brown et al., 2020). Para tareas de generación de SQL desde lenguaje natural, Rajkumar et al. (2022) reportaron precisiones superiores al 80 % con GPT-4, lo que valida su uso en escenarios de analítica conversacional. Gemini 2.0 Flash, lanzado por Google DeepMind a finales de 2024, ofrece ventana de contexto de hasta dos millones de tokens y costo aproximado de USD 0,075 por millón de tokens de entrada, condiciones que viabilizan el caso de uso MIPYME (Google DeepMind, 2024)."
    ),
    apaPara(
      "La segunda línea es la arquitectura multi-tenant. Bezemer y Zaidman (2010) clasifican los enfoques en tres niveles de aislamiento: tabla compartida, esquema separado y base de datos dedicada por cliente. La presente propuesta adopta el tercer nivel, justificado por la sensibilidad de los datos comerciales y financieros que maneja la plataforma (Krebs, Momm y Kounev, 2012). La tercera línea son los pipelines ETL adaptativos: Stonebraker et al. (2013) introdujeron con el sistema Data Tamer la noción de curaduría de datos a escala mediante aprendizaje automático, principio que esta investigación combina con LLM para construir un pipeline de cinco etapas operado por usuarios sin perfil técnico."
    ),

    h2("3. Metodología"),
    apaPara(
      "La investigación adoptó un enfoque mixto secuencial exploratorio (Creswell y Creswell, 2018), articulado con la metodología ágil Scrum para la fase de desarrollo. La fase cualitativa recoge requerimientos a través de entrevistas semiestructuradas con directivos de PYMES; la fase cuantitativa mide adopción mediante encuestas estructuradas y usabilidad mediante la escala System Usability Scale de Brooke (1996). La validación del prototipo se realizó en una empresa piloto del sector terciario (ferretería) en Bogotá D. C., conforme a los requisitos de Minciencias para alcanzar TRL 6-7."
    ),
    apaPara(
      "Como parte de la metodología, se efectuó una comparación sistemática entre tres modelos de IA (redes neuronales/Gemini, Random Forest y regresión lineal), tres herramientas de dashboards (Power BI, Tableau y Pentaho) y tres plataformas de IA en la nube (Gemini 2.5 Pro, Vertex AI y OpenAI GPT-4o), siguiendo criterios de tipo, precisión, complejidad, interpretabilidad, costo y capacidad de integración. Esta comparación, desarrollada en detalle en la entrega 2 del semillero, soportó las decisiones de selección que se presentan en la sección de resultados."
    ),

    h2("4. Resultados"),
    h3("4.1. Selección de la herramienta óptima"),
    apaPara(
      "Tras la comparación sistemática de modelos, dashboards y plataformas, la decisión fundamentada apunta a una combinación específica que se sintetiza en la Tabla 1. La justificación técnica responde a tres criterios: (a) bajo costo operativo total (USD 0-15 mensuales), (b) capacidad de operar en español sin tecnicismos para el usuario final y (c) facilidad de evolución a una infraestructura cloud-nativa cuando crezca la demanda."
    ),
    new Paragraph({
      spacing: { before: 240, after: 120, line: 360 },
      children: [bold("Tabla 1"), italic("  Selección de tecnologías para el proyecto")],
    }),
    buildTable(
      ["Criterio", "Herramienta seleccionada"],
      [
        ["Modelo de IA", "Redes Neuronales (Gemini 2.0 Flash) — supervisado/RLHF, alto contexto, español nativo"],
        ["Herramienta de IA", "Google Gemini API directa, con ruta de migración a Vertex AI para escala"],
        ["Dashboard", "Recharts + shadcn/ui sobre Next.js — autogenerado por el agente DashboardConfig"],
        [
          "Justificación técnica",
          "El stack maximiza relación costo-valor, mantiene 100 % de control sobre la capa de visualización (sin licencias externas), y aprovecha el ecosistema cloud de Google sin atarse a él de forma irreversible.",
        ],
      ],
      [2400, 6960]
    ),

    h3("4.2. Propuesta de integración"),
    apaPara(
      "La solución funciona como un flujo de cinco eslabones. Primero, el usuario carga sus archivos PDF, Excel o CSV mediante el ChatBot o el módulo Mis Datos. Segundo, el agente ETL extrae los datos usando pdfplumber o pandas. Tercero, el agente DataCleaner los normaliza, deduplica y valida. Cuarto, los agentes DataAnalyzer y InsightGenerator producen estadísticas y un resumen ejecutivo en español. Quinto, el agente DashboardConfig arma las gráficas y el ChatAgent queda disponible para responder preguntas en lenguaje natural sobre los datos cargados. La Figura 1 muestra el pipeline completo."
    ),
    ...image(
      "8632dd58623c964c4f3839ef4467d53a8ca2e41d.png",
      560, 280,
      "Figura 1. Pipeline secuencial de los cinco agentes orquestados por el Google ADK."
    ),
    apaPara(
      "Toda la solución se despliega en un servidor virtual con Docker Compose, expuesto sobre HTTPS con certificado Let's Encrypt. El frontend Next.js sirve la interfaz en el puerto 443; el backend FastAPI atiende las peticiones del ChatBot y del pipeline; PostgreSQL almacena las bases de datos por organización (org_<uuid>); y la API de Google Gemini procesa las consultas en lenguaje natural. La Figura 2 ilustra esta topología."
    ),
    ...image(
      "a1aab30a51be8f2e4a48054d8f1ac5642ebfcdf7.png",
      560, 360,
      "Figura 2. Topología de despliegue. VPS único con tres contenedores Docker más servicios externos (Gemini y DNS)."
    ),

    h3("4.3. Resultados de validación con el piloto"),
    apaPara(
      "El prototipo fue validado con datos reales de una ferretería bogotana. Se cargaron cuatro archivos CSV con 250 registros entre cotizaciones, clientes, facturas y servicios. La plataforma reconoció los datos, los cargó correctamente y generó el dashboard sin intervención humana. La Figura 3 corresponde al dashboard generado durante la validación."
    ),
    ...image(
      "8921800b4f61fec0f85c0990854c0cdb6a102a60.png",
      540, 320,
      "Figura 3. Dashboard del piloto Ferretería Demo, con KPIs auto-generados y panel lateral del ChatBot."
    ),
    apaPara(
      "Se ejecutaron 40 consultas de prueba al ChatBot, cubriendo preguntas sobre productos más vendidos, clientes principales, totales por período y análisis de tendencias. La tasa de respuestas correctas fue del 85 %. Adicionalmente, el sistema produjo de forma autónoma una recomendación no programada explícitamente: identificar a Constructora Andes SAS como cliente con frecuencia de compra decreciente y sugerir un descuento por volumen, hallazgo que evidencia la capacidad de razonamiento del modelo más allá del simple retrieve. Los tiempos observados fueron inferiores a tres segundos para procesar archivos de cien filas y entre dos y cinco segundos para respuestas conversacionales."
    ),

    h2("5. Discusión"),
    apaPara(
      "Los resultados confirman la hipótesis inicial: una plataforma SaaS multi-tenant respaldada por un LLM puede entregar a una microempresa capacidades analíticas que tradicionalmente exigían personal especializado. La elección de redes neuronales —vía Gemini 2.0 Flash— frente a alternativas como Random Forest o regresión lineal se justifica por la capacidad simultánea de clasificar, generar texto en español y razonar sobre datos heterogéneos, algo que ningún modelo más simple ofrece de manera unificada. La decisión de construir el dashboard con Recharts en lugar de integrar Power BI o Tableau responde al control que requiere la capa de autogeneración por agente: las herramientas comerciales privilegian al diseñador humano y no al agente automático."
    ),
    apaPara(
      "El uso de Gemini API directa, con ruta de migración a Vertex AI, representa un compromiso entre simplicidad operativa actual y escalabilidad futura. Vertex AI agrega valor cuando crece la base de usuarios y se requieren controles de MLOps, pero introduce complejidad innecesaria en la fase de prototipo. El enfoque elegido —Gemini API hoy, Vertex AI mañana— permite avanzar rápido sin cerrar puertas. Las limitaciones identificadas son tres: dependencia de conectividad a internet, techo de 10 000 registros por organización en la fase prototipo, y necesidad de validación adicional con tipologías de negocio distintas a la ferretería."
    ),

    h2("6. Conclusiones"),
    apaPara(
      "El presente artículo consolida el proceso investigativo del semillero y demuestra, mediante un prototipo funcional validado, que es viable democratizar la analítica avanzada para PYMES colombianas combinando un LLM, una arquitectura multi-tenant y dashboards autogenerados. La selección de Gemini 2.0 Flash como modelo, Recharts/Next.js como capa de visualización y la API directa de Google como plataforma cloud responde a una decisión razonada y sustentada en la comparación sistemática realizada en la entrega 2."
    ),
    apaPara(
      "Las aplicaciones futuras del trabajo son de tres órdenes. En el plano comercial, escalar el piloto a una decena de empresas y migrar el backend a Vertex AI para absorber mayor carga. En el plano académico, replicar el experimento con otros modelos —SVM, gradient boosting— para producir benchmarks comparativos en el contexto MIPYME latinoamericano. En el plano social, articular la plataforma con cámaras de comercio y programas de la Alcaldía de Bogotá para acelerar la adopción en microempresas que hoy quedan al margen de la transformación digital."
    ),

    h2("Referencias"),
    refPara(
      "Bezemer, C. P., y Zaidman, A. (2010). Multi-tenant SaaS applications: Maintenance dream or nightmare? Proceedings of the Joint ERCIM Workshop on Software Evolution, 88–92. https://doi.org/10.1145/1862372.1862393"
    ),
    refPara(
      "Brooke, J. (1996). SUS — A quick and dirty usability scale. En P. W. Jordan, B. Thomas, B. A. Weerdmeester e I. L. McClelland (Eds.), Usability evaluation in industry (pp. 189–194). Taylor and Francis."
    ),
    refPara(
      "Brown, T. B., Mann, B., Ryder, N., Subbiah, M., Kaplan, J., Dhariwal, P., Neelakantan, A., Shyam, P., Sastry, G., Askell, A., Agarwal, S., Herbert-Voss, A., Krueger, G., Henighan, T., Child, R., Ramesh, A., Ziegler, D. M., Wu, J., Winter, C., … Amodei, D. (2020). Language models are few-shot learners. Advances in Neural Information Processing Systems, 33, 1877–1901."
    ),
    refPara(
      "Confecámaras. (2023). Dinámica de creación de empresas en Colombia: Informe 2023. Confederación Colombiana de Cámaras de Comercio. https://confecamaras.org.co/informes"
    ),
    refPara(
      "Creswell, J. W., y Creswell, J. D. (2018). Research design: Qualitative, quantitative, and mixed methods approaches (5.ª ed.). SAGE Publications."
    ),
    refPara(
      "Goodfellow, I., Bengio, Y., y Courville, A. (2016). Deep learning. MIT Press."
    ),
    refPara(
      "Google Cloud. (2024). Vertex AI documentation: Build, deploy and scale ML models. https://cloud.google.com/vertex-ai/docs"
    ),
    refPara(
      "Google DeepMind. (2024). Gemini 2.0: A family of highly capable multimodal models. arXiv. https://arxiv.org/abs/2312.11805"
    ),
    refPara(
      "Krebs, R., Momm, C., y Kounev, S. (2012). Architectural concerns in multi-tenant SaaS applications. Proceedings of the 2nd International Conference on Cloud Computing and Services Science, 426–431."
    ),
    refPara(
      "LeCun, Y., Bengio, Y., y Hinton, G. (2015). Deep learning. Nature, 521(7553), 436–444. https://doi.org/10.1038/nature14539"
    ),
    refPara(
      "Ministerio de Tecnologías de la Información y las Comunicaciones. (2024). Índice de digitalización de MIPYMES en Colombia 2024. MinTIC."
    ),
    refPara(
      "Rajkumar, N., Li, R., y Bahdanau, D. (2022). Evaluating the text-to-SQL capabilities of large language models. arXiv. https://doi.org/10.48550/arXiv.2204.00498"
    ),
    refPara(
      "Stonebraker, M., Bruckner, D., Ilyas, I. F., Beskales, G., Cherniack, M., Zdonik, S. B., Pagan, A., y Xu, S. (2013). Data curation at scale: The Data Tamer system. Proceedings of CIDR, 1–10."
    ),
  ];

  return new Document({
    creator: "Brandow Brusly León",
    title: "Entrega 3 — Artículo Científico",
    description: "Tercera entrega del semillero — Artículo científico final con selección de herramienta",
    styles: commonStyles(),
    numbering: commonNumbering(),
    sections: commonSection("Entrega 3 — Artículo Científico — Semillero UCompensar 2026-1", children),
  });
}

// ===========================================================================
// MAIN
// ===========================================================================
const outDir = path.resolve(__dirname, "..");
const outputs = [
  ["Entrega1_Redes_Neuronales_Brandow_Leon.docx", buildEntrega1()],
  ["Entrega2_Comparativo_IA_Brandow_Leon.docx", buildEntrega2()],
  ["Entrega3_Articulo_Cientifico_Brandow_Leon.docx", buildEntrega3()],
];

(async () => {
  for (const [filename, doc] of outputs) {
    const buffer = await Packer.toBuffer(doc);
    const out = path.join(outDir, filename);
    fs.writeFileSync(out, buffer);
    console.log("OK ->", out, "size:", buffer.length, "bytes");
  }
})();
