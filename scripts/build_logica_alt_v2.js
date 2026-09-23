/**
 * v2 — Bloque "¿Qué alternativa novedosa de solución tengo?"
 *
 * Estructura nueva pedida por la usuaria:
 *   Propuesta 1: Lógica proposicional V = p ∧ (q ∨ r) con tabla de verdad de 8 filas
 *   Propuesta 2: Teoría de conjuntos A ∩ B ∩ C con diagrama de Venn
 *   Propuesta 3: Pseudocódigo con estructuras de control SI–ENTONCES
 *
 * Tono: muy humano, analogías cotidianas (portero, torta de capas, receta).
 * Audiencia: alguien que NO sabe nada del tema.
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
const SIZE_BODY = 24;
const SIZE_H1 = 28;
const SIZE_H2 = 26;
const SIZE_H3 = 24;
const MONO = "Consolas";
const IMG = "/sessions/nice-vigilant-tesla/mnt/outputs/img_logica_v2";

const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const cellBorders = { top: border, bottom: border, left: border, right: border };

function plain(text, opts = {}) { return new TextRun({ text, font: FONT, size: SIZE_BODY, ...opts }); }
function bold(text, opts = {}) { return new TextRun({ text, font: FONT, size: SIZE_BODY, bold: true, ...opts }); }
function italic(text, opts = {}) { return new TextRun({ text, font: FONT, size: SIZE_BODY, italics: true, ...opts }); }
function code(text, opts = {}) { return new TextRun({ text, font: MONO, size: 20, ...opts }); }

function p(textOrRuns, opts = {}) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    spacing: { line: 360, after: 120 },
    indent: opts.indent === false ? undefined : { firstLine: 720 },
    children: typeof textOrRuns === "string"
      ? [new TextRun({ text: textOrRuns, font: FONT, size: SIZE_BODY })]
      : textOrRuns,
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 180, line: 360 },
    children: [new TextRun({ text, font: FONT, size: SIZE_H1, bold: true })],
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 300, after: 120, line: 360 },
    children: [new TextRun({ text, font: FONT, size: SIZE_H2, bold: true })],
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 80, line: 360 },
    children: [new TextRun({ text, font: FONT, size: SIZE_H3, bold: true, italics: true })],
  });
}

function bullet(textOrRuns) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { line: 320, after: 60 },
    alignment: AlignmentType.JUSTIFIED,
    children: typeof textOrRuns === "string"
      ? [new TextRun({ text: textOrRuns, font: FONT, size: SIZE_BODY })]
      : textOrRuns,
  });
}

function pageBreak() { return new Paragraph({ children: [new PageBreak()] }); }

function codeBlock(lines) {
  return lines.map((line) =>
    new Paragraph({
      spacing: { line: 260, after: 0 },
      shading: { fill: "F3F3F3", type: ShadingType.CLEAR, color: "auto" },
      indent: { left: 360 },
      children: [code(line || " ")],
    })
  );
}

function image(filename, w, h, caption) {
  const filePath = path.join(IMG, filename);
  return [
    new Paragraph({
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
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 },
      children: [italic(caption)],
    }),
  ];
}

// Caja de "Analogía" con fondo crema
function analogyBox(title, body) {
  const cells = [
    new TableCell({
      borders: cellBorders,
      width: { size: 9360, type: WidthType.DXA },
      margins: { top: 200, bottom: 200, left: 220, right: 220 },
      shading: { fill: "FFF8E1", type: ShadingType.CLEAR, color: "auto" },
      children: [
        new Paragraph({
          spacing: { after: 80, line: 320 },
          children: [bold("📌  " + title, { color: "BF6F00" })],
        }),
        new Paragraph({
          spacing: { line: 320 },
          alignment: AlignmentType.JUSTIFIED,
          children: [plain(body)],
        }),
      ],
    }),
  ];
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [new TableRow({ children: cells })],
  });
}

// ===========================================================================
// CONTENIDO
// ===========================================================================
const contenido = [

  h1("c. ¿Qué alternativa novedosa de solución tengo?"),
  p(
    "Para dar respuesta a la problemática del filtrado ineficiente en el chatbot inmobiliario, proponemos tres alternativas de solución que se apoyan directamente en lo que hemos visto en clase: lógica matemática, teoría de conjuntos y estructuras de programación. Las tres propuestas funcionan juntas, como las piezas de un mismo rompecabezas, pero cada una resuelve una parte distinta del problema. La primera decide quién es un cliente que vale la pena atender; la segunda decide qué propiedades le vamos a mostrar; y la tercera traduce todo lo anterior a un programa de computador que el chatbot puede ejecutar."
  ),
  p(
    "Antes de meternos en la teoría, vale la pena recordar el problema en una frase: la inmobiliaria recibe muchísimas consultas por su chatbot, pero hoy no tiene forma de saber cuáles consultas vienen de un cliente que de verdad puede comprar y cuáles vienen de alguien que solo está mirando. Eso satura al equipo de ventas y deja escapar oportunidades. Las tres propuestas que siguen apuntan justamente a resolver ese cuello de botella."
  ),

  // =====================================================================
  // PROPUESTA 1
  // =====================================================================
  h2("Propuesta 1 — Modelo de calificación de leads con lógica proposicional"),
  analogyBox(
    "Una analogía para entenderlo",
    "Imaginemos un portero de discoteca. Antes de dejar entrar a alguien, mira tres cosas en una lista: que sea mayor de edad, que esté vestido como pide el lugar y que traiga la entrada o tenga reserva. Si falla la edad, no entra, así tenga las otras dos. Si tiene la edad y el código de vestimenta, le basta con cualquiera de las dos formas de pago: la entrada física o la reserva. Nuestro chatbot va a funcionar exactamente como ese portero: revisa una lista corta y, según unas reglas, decide si el cliente pasa o no pasa."
  ),
  p(""),
  p(
    "La idea concreta es la siguiente: el chatbot le hace al cliente tres preguntas muy puntuales y, con sus respuestas, calcula una conclusión. En lógica matemática, a esas preguntas se les llama proposiciones simples y se les pone una letra para no estar repitiendo todo el tiempo el enunciado completo."
  ),
  bullet([bold("p:  "), plain("el cliente tiene un presupuesto mayor o igual a $150.000.000 COP.")]),
  bullet([bold("q:  "), plain("el cliente cuenta con un crédito pre-aprobado.")]),
  bullet([bold("r:  "), plain("el cliente dispone del dinero de contado.")]),
  p(
    "Cada una de estas tres proposiciones puede ser verdadera (V) o falsa (F). Lo bonito de la lógica matemática es que podemos combinar varias proposiciones con conectores —que son palabras como “y”, “o”, “no”— para construir reglas más complejas. Para nuestro caso, la regla que define cuándo un cliente es VIABLE (es decir, que vale la pena pasarlo a un asesor humano) es esta:"
  ),
  ...codeBlock([
    "                V  =  p  ∧  (q  ∨  r)",
  ]),
  p(
    "En palabras de todos los días: el cliente es viable cuando tiene presupuesto suficiente Y, además, tiene crédito pre-aprobado O dinero de contado. El símbolo ∧ es el “Y” lógico (conjunción), el símbolo ∨ es el “O” lógico (disyunción) y el = significa que el resultado V queda definido por toda esa expresión. Fíjate en algo importante: el “Y” es exigente —pide que las dos cosas pasen al tiempo— mientras que el “O” es más flexible —con una de las dos basta—."
  ),
  ...image("04_analogia_portero.png", 480, 240, "Figura 1. El chatbot funciona como un portero con su lista. Aplica la regla V = p ∧ (q ∨ r) y solo deja “entrar” a quien la cumple."),

  h3("Tabla de verdad — todas las combinaciones posibles"),
  p(
    "Como tenemos tres proposiciones (p, q, r) y cada una puede ser V o F, en total existen 2 × 2 × 2 = 8 combinaciones posibles. La tabla de verdad nos sirve para verlas todas a la vez y comprobar en cuáles el cliente queda VIABLE y en cuáles no. Es como una hoja de Excel donde escribimos cada caso y dejamos que la lógica nos diga la respuesta."
  ),
  ...image("01_tabla_verdad.png", 520, 380, "Figura 2. Tabla de verdad para V = p ∧ (q ∨ r). Solo tres de las ocho combinaciones dan cliente viable, todas con presupuesto verdadero (p = V)."),
  p(
    "La conclusión salta a la vista: si p es falso —es decir, si el cliente no tiene el presupuesto mínimo— el resultado siempre es F, sin importar qué pase con q y r. Eso refleja exactamente la realidad del negocio: si alguien no puede pagar, no importa si tiene crédito aprobado, el negocio no se va a cerrar. Por eso el “Y” entre p y el resto es una decisión deliberada del equipo: el presupuesto es la primera barrera que se debe cumplir."
  ),

  // =====================================================================
  // PROPUESTA 2
  // =====================================================================
  h2("Propuesta 2 — Segmentación de propiedades con teoría de conjuntos"),
  analogyBox(
    "Una analogía para entenderlo",
    "Pensemos en una torta de tres capas. La capa de abajo son todos los ingredientes que tenemos en la cocina; la del medio son solo los ingredientes que están frescos hoy; y la de arriba son los ingredientes que combinan bien con chocolate. Si quiero hacer un postre fresco con chocolate, lo que me sirve es justo el pedacito que aparece en las tres capas a la vez. La intersección. En el chatbot pasa lo mismo: tenemos varias listas de propiedades y nos quedamos con las que aparecen en todas las listas que el cliente pidió."
  ),
  p(""),
  p(
    "Una vez el chatbot determinó con la Propuesta 1 que el cliente es viable, tiene que mostrarle propiedades. Pero no cualquier propiedad: tienen que coincidir con lo que el cliente está buscando. Aquí entra la teoría de conjuntos, que es como agrupar cosas en cajas y hacer cuentas entre cajas."
  ),
  p(
    "Para nuestro escenario, definimos los siguientes conjuntos dentro de la base de datos de la inmobiliaria:"
  ),
  bullet([bold("U: "), plain("conjunto universal — todos los inmuebles que tiene la inmobiliaria.")]),
  bullet([bold("A: "), plain("inmuebles ubicados en Bogotá.")]),
  bullet([bold("B: "), plain("inmuebles del tipo apartamento.")]),
  bullet([bold("C: "), plain("inmuebles con un valor menor a $250.000.000 COP.")]),
  p(
    "Si un cliente le dice al chatbot “quiero un apartamento económico en Bogotá”, el chatbot tiene que devolverle solo las propiedades que cumplan las tres condiciones a la vez. Eso, en lenguaje de conjuntos, se llama intersección y se escribe con el símbolo ∩. La fórmula queda así:"
  ),
  ...codeBlock([
    "             Solución  =  A  ∩  B  ∩  C",
  ]),
  p(
    "Visualmente, una intersección se entiende mejor con un diagrama de Venn, que son círculos que se cruzan. Cada círculo representa un conjunto y la región donde se cruzan los tres es la intersección que estamos buscando: la zona donde un inmueble cumple los tres requisitos a la vez."
  ),
  ...image("02_venn.png", 460, 380, "Figura 3. Diagrama de Venn con los tres filtros. La estrella roja en el centro marca la intersección A ∩ B ∩ C, que es el conjunto exacto de propiedades que el chatbot le devolverá al cliente."),
  p(
    "La gran ventaja de usar conjuntos es que la búsqueda queda libre de errores: el chatbot no le va a mostrar una casa de Cali, ni una bodega industrial, ni un apartamento de mil millones. Solo lo que cae dentro de los tres círculos al mismo tiempo. Y para la base de datos también es bueno: en vez de leer toda la tabla de inmuebles, hace tres filtros consecutivos y entrega la respuesta más rápido."
  ),

  // =====================================================================
  // PROPUESTA 3
  // =====================================================================
  h2("Propuesta 3 — Estructura de control y pseudocódigo del agente virtual"),
  analogyBox(
    "Una analogía para entenderlo",
    "Las dos propuestas anteriores son la teoría: dicen QUÉ tiene que hacer el chatbot. Pero un computador no entiende teoría, necesita instrucciones paso a paso, como una receta de cocina: primero pica la cebolla, después calienta el aceite, si la sartén está caliente echa la cebolla, si no espera. Esta tercera propuesta es esa receta: un pseudocódigo que dice, en orden, lo que el chatbot debe hacer desde que el cliente saluda hasta que lo despide."
  ),
  p(""),
  p(
    "El pseudocódigo es una manera de escribir programas usando palabras parecidas al español pero con una estructura clara y ordenada. Lo bonito es que cualquier programador puede tomar este pseudocódigo y traducirlo a un lenguaje real como Python o JavaScript sin perderse. Los elementos que vamos a usar son los SI–ENTONCES (estructuras de control) que sirven para tomar decisiones, y las variables que sirven para guardar valores."
  ),
  ...codeBlock([
    "INICIO",
    "  Definir presupuesto Como Real",
    "  Definir tiene_credito, tiene_contado, cliente_viable Como Logico",
    "",
    "  Escribir \"Bienvenido a InmobiliaryAI. Para brindarle la\"",
    "  Escribir \"mejor atención, por favor responda:\"",
    "  Escribir \"¿Cuál es su presupuesto estimado?\"",
    "  Leer presupuesto",
    "",
    "  Si presupuesto >= 150000000 Entonces",
    "      Escribir \"¿Cuenta con crédito pre-aprobado? (V/F)\"",
    "      Leer tiene_credito",
    "      Escribir \"¿Cuenta con pago de contado? (V/F)\"",
    "      Leer tiene_contado",
    "",
    "      // Aplicación de la regla de la Propuesta 1",
    "      cliente_viable = (tiene_credito O tiene_contado)",
    "",
    "      Si cliente_viable == Verdadero Entonces",
    "          Escribir \"¡Perfecto! Lo contactaremos con un asesor VIP.\"",
    "          Llamar_Asesor_Humano()",
    "      Sino",
    "          Escribir \"Le enviaremos opciones alternativas a su correo.\"",
    "          Guardar_En_Base_Datos_Espera()",
    "      Fin Si",
    "  Sino",
    "      Escribir \"Actualmente no contamos con inventario en ese rango.\"",
    "  Fin Si",
    "FIN",
  ]),
  p(
    "El pseudocódigo se lee de arriba hacia abajo, como una historieta. Primero el chatbot saluda, después pregunta el presupuesto. Si el presupuesto es menor a 150 millones, le dice amablemente que no hay inventario en ese rango y termina la conversación: ahí estamos aplicando la primera mitad de nuestra regla lógica (la condición p). Si el presupuesto sí cumple, hace dos preguntas más sobre crédito y contado, y combina las respuestas con un “O” —exactamente la disyunción (q ∨ r) de la Propuesta 1—. Si la combinación da verdadero, el cliente es viable y el sistema llama a un asesor humano; si no, lo guarda en una lista de espera para enviarle opciones por correo después."
  ),
  p(
    "El siguiente diagrama de flujo muestra esa misma receta pero en forma de dibujo. Cada caja es una acción, cada rombo amarillo es una pregunta cuya respuesta cambia el camino. Las flechas indican por dónde va el chatbot dependiendo de lo que conteste el cliente."
  ),
  ...image("03_diagrama_flujo.png", 440, 580, "Figura 4. Diagrama de flujo del chatbot. Es la traducción gráfica del pseudocódigo: primero filtra por presupuesto, luego por crédito o contado, y al final clasifica al cliente."),

  // =====================================================================
  // CIERRE
  // =====================================================================
  h2("Por qué estas tres propuestas funcionan mejor juntas"),
  p(
    "Las tres propuestas están conectadas, no son alternativas independientes que compitan entre sí. La Propuesta 1 le da al chatbot una regla lógica para saber QUIÉN es un cliente que vale la pena atender. La Propuesta 2 le da una manera ordenada de decidir QUÉ propiedades mostrarle, usando intersecciones de conjuntos. Y la Propuesta 3 le da la receta paso a paso para que un programador pueda implementarlas en código real."
  ),
  p(
    "Si la inmobiliaria adopta las tres, el resultado es un chatbot que ya no atiende a todo el mundo de la misma forma: filtra rápido, muestra solo lo que de verdad le interesa al cliente y libera tiempo de los asesores humanos para que se enfoquen en cerrar negocios. Y todo eso sin necesidad de inteligencia artificial sofisticada ni de tecnologías caras: con pura lógica matemática, conjuntos y estructuras de control que aprendimos en el primer semestre."
  ),
];

// ===========================================================================
const doc = new Document({
  creator: "Sharon León — Raquel Merlano — Angie Pérez — Cristhian Prieto",
  title: "Bloque c — Alternativa innovadora",
  description: "Bloque c de la Actividad 1 de Lógica Matemática y Programación",
  styles: {
    default: { document: { run: { font: FONT, size: SIZE_BODY } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: SIZE_H1, bold: true, font: FONT },
        paragraph: { spacing: { before: 360, after: 180, line: 360 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: SIZE_H2, bold: true, font: FONT },
        paragraph: { spacing: { before: 300, after: 120, line: 360 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: SIZE_H3, bold: true, italics: true, font: FONT },
        paragraph: { spacing: { before: 200, after: 80, line: 360 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ],
  },
  sections: [{
    properties: {
      page: { size: { width: 12240, height: 15840 },
              margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } },
    },
    headers: { default: new Header({ children: [
      new Paragraph({ alignment: AlignmentType.RIGHT,
        children: [new TextRun({
          text: "Lógica Matemática y Programación — Actividad 1 — bloque c",
          font: FONT, size: 20, italics: true, color: "595959" })] })
    ] }) },
    footers: { default: new Footer({ children: [
      new Paragraph({ alignment: AlignmentType.CENTER,
        children: [
          new TextRun({ text: "Página ", font: FONT, size: 20 }),
          new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 20 }),
          new TextRun({ text: " — Compensar 2026", font: FONT, size: 20 }),
        ] })
    ] }) },
    children: contenido,
  }],
});

const out = path.resolve(__dirname, "..", "Bloque_C_Alternativas_Humanizado.docx");
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(out, buffer);
  console.log("OK ->", out, "size:", buffer.length, "bytes");
});
