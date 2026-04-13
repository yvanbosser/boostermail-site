const fs = require("fs");
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
        ShadingType, PageNumber, PageBreak } = require("docx");

const BLUE = "1F4E79";
const LIGHT_BLUE = "D6E4F0";
const LIGHT_GRAY = "F2F2F2";
const WHITE = "FFFFFF";

const border = { style: BorderStyle.SINGLE, size: 1, color: "AAAAAA" };
const borders = { top: border, bottom: border, left: border, right: border };
const cm = { top: 60, bottom: 60, left: 100, right: 100 };

function hc(text, w) {
  return new TableCell({ borders, width: { size: w, type: WidthType.DXA },
    shading: { fill: BLUE, type: ShadingType.CLEAR }, margins: cm,
    children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ text, bold: true, color: "FFFFFF", font: "Calibri", size: 20 })] })] });
}

function dc(text, w, opts = {}) {
  const sh = opts.sh ? { fill: opts.sh, type: ShadingType.CLEAR } : undefined;
  return new TableCell({ borders, width: { size: w, type: WidthType.DXA }, shading: sh, margins: cm,
    children: [new Paragraph({ alignment: opts.a || AlignmentType.LEFT,
      children: [new TextRun({ text: String(text), bold: !!opts.b, font: "Calibri", size: 20, color: opts.c || "333333" })] })] });
}

function tbl(headers, rows, cw) {
  const tw = cw.reduce((a, b) => a + b, 0);
  const hr = new TableRow({ children: headers.map((h, i) => hc(h, cw[i])) });
  const dr = rows.map((row, ri) => {
    const isT = row[0].startsWith("Total");
    return new TableRow({ children: row.map((v, i) => dc(v, cw[i], {
      b: isT, a: i > 0 ? AlignmentType.CENTER : AlignmentType.LEFT,
      sh: isT ? LIGHT_BLUE : (ri % 2 === 1 ? LIGHT_GRAY : WHITE) })) });
  });
  return new Table({ width: { size: tw, type: WidthType.DXA }, columnWidths: cw, rows: [hr, ...dr] });
}

function h1(t) { return new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 400, after: 200 }, children: [new TextRun({ text: t, bold: true, font: "Calibri", color: BLUE })] }); }
function h2(t) { return new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 300, after: 150 }, children: [new TextRun({ text: t, bold: true, font: "Calibri", color: BLUE })] }); }
function p(t, o = {}) { return new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: t, font: "Calibri", size: 22, ...o })] }); }
function b(t) { return new Paragraph({ spacing: { after: 60 }, indent: { left: 360, hanging: 180 }, children: [new TextRun({ text: "\u2022 " + t, font: "Calibri", size: 22 })] }); }

const c5 = [2800, 1200, 1200, 1400, 1400];

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Calibri", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 36, bold: true, font: "Calibri", color: BLUE }, paragraph: { spacing: { before: 400, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 28, bold: true, font: "Calibri", color: BLUE }, paragraph: { spacing: { before: 300, after: 150 }, outlineLevel: 1 } },
    ]
  },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1200, right: 1200, bottom: 1200, left: 1200 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "EasyMail \u2014 Pricing & Co\u00fbts API", font: "Calibri", size: 16, color: "999999", italics: true })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Page ", font: "Calibri", size: 16, color: "999999" }), new TextRun({ children: [PageNumber.CURRENT], font: "Calibri", size: 16, color: "999999" })] })] }) },
    children: [
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [new TextRun({ text: "EasyMail", font: "Calibri", size: 52, bold: true, color: BLUE })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 50 }, children: [new TextRun({ text: "Analyse Pricing & Co\u00fbts API", font: "Calibri", size: 36, color: "555555" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 }, children: [new TextRun({ text: "Version d\u00e9finitive \u2014 Avril 2026", font: "Calibri", size: 22, color: "999999", italics: true })] }),

      h1("1. Hypoth\u00e8ses"),
      p("Mod\u00e8les IA", { bold: true }), b("Onboarding : Claude Sonnet ($3/$15 par 1M tokens) \u2014 1 seule fois"), b("G\u00e9n\u00e9ration S+H : GPT-5 mini ($0.25/$2 par 1M tokens)"), b("G\u00e9n\u00e9ration R : GPT-5 nano ($0.05/$0.40 par 1M tokens)"), b("Tout le reste : GPT-5 mini"),
      p("Optimisations", { bold: true }), b("Prompt caching actif (90% r\u00e9duction sur tokens syst\u00e8me)"), b("Templates intelligents : 20% des mails r\u00e9solus sans appel API"), b("Output court mails R : max 400 tokens"),
      p("3 profils utilisateurs", { bold: true }), b("Bon r\u00e9dacteur : 30 mails/jour, correction 20%, convergence 50 mails (~2 jours)"), b("R\u00e9dacteur moyen : 30 mails/jour, correction 40%, convergence 200 mails (~7 jours)"), b("R\u00e9dacteur faible : 10 mails/jour, correction 60%, convergence 500 mails (~2.5 mois)"),

      new Paragraph({ children: [new PageBreak()] }),
      h1("2. Bon r\u00e9dacteur \u2014 30 mails/jour, 20%, convergence 50 mails"),
      h2("Phase 1 \u2014 Formation (onboarding, one-shot)"),
      tbl(["T\u00e2che", "Mod\u00e8le", "Appels", "Co\u00fbt/appel", "Co\u00fbt total"], [["Analyse style + scoring", "Sonnet", "1", "$0.18", "$0.18"], ["Analyse contacts", "Mini", "~80", "$0.005", "$0.43"], ["Total Formation", "", "", "", "$0.61"]], c5),
      h2("Phase 2 \u2014 Transition (50 mails, ~2 jours)"),
      tbl(["T\u00e2che", "Mod\u00e8le", "Appels", "Co\u00fbt/appel", "Co\u00fbt total"], [["G\u00e9n\u00e9ration R (cache)", "Nano", "8", "$0.0008", "$0.006"], ["G\u00e9n\u00e9ration S+H (cache)", "Mini", "32", "$0.004", "$0.134"], ["Refinement", "Mini", "8", "$0.002", "$0.017"], ["Scan \u00e9ch\u00e9ances", "Mini", "40", "$0.0015", "$0.059"], ["Classification mail", "Mini", "10", "$0.002", "$0.019"], ["Classification PJ", "Mini", "7", "$0.002", "$0.013"], ["Analyse contacts", "Mini", "15", "$0.005", "$0.081"], ["D2 micro-analyse", "Mini", "8", "$0.001", "$0.006"], ["Recalibrage", "Mini", "5", "$0.017", "$0.084"], ["OCR", "Mini", "5", "$0.001", "$0.007"], ["Total Transition", "", "", "", "$0.43"]], c5),
      h2("Phase 3 \u2014 Autonomie (mensuel)"),
      tbl(["T\u00e2che", "Mod\u00e8le", "Appels/jour", "Co\u00fbt/jour", "Co\u00fbt/mois"], [["G\u00e9n\u00e9ration R (cache)", "Nano", "8", "$0.006", "$0.14"], ["G\u00e9n\u00e9ration S+H (cache)", "Mini", "16", "$0.063", "$1.39"], ["Refinement", "Mini", "5", "$0.011", "$0.23"], ["Scan \u00e9ch\u00e9ances", "Mini", "24", "$0.035", "$0.78"], ["Classification mail", "Mini", "6", "$0.011", "$0.25"], ["Classification PJ", "Mini", "5", "$0.010", "$0.21"], ["Analyse contacts", "Mini", "1", "$0.005", "$0.12"], ["D2 micro-analyse", "Mini", "5", "$0.004", "$0.08"], ["Recalibrage", "Mini", "1.5", "$0.025", "$0.55"], ["OCR", "Mini", "3", "$0.004", "$0.09"], ["Total/mois", "", "", "", "~$3.87"]], c5),

      new Paragraph({ children: [new PageBreak()] }),
      h1("3. R\u00e9dacteur moyen \u2014 30 mails/jour, 40%, convergence 200 mails"),
      h2("Phase 1 \u2014 Formation (onboarding, one-shot)"),
      tbl(["T\u00e2che", "Mod\u00e8le", "Appels", "Co\u00fbt/appel", "Co\u00fbt total"], [["Analyse style + scoring", "Sonnet", "1", "$0.18", "$0.18"], ["Analyse contacts", "Mini", "~80", "$0.005", "$0.43"], ["Total Formation", "", "", "", "$0.61"]], c5),
      h2("Phase 2 \u2014 Transition (200 mails, ~7 jours)"),
      tbl(["T\u00e2che", "Mod\u00e8le", "Appels", "Co\u00fbt/appel", "Co\u00fbt total"], [["G\u00e9n\u00e9ration R (cache)", "Nano", "32", "$0.0008", "$0.026"], ["G\u00e9n\u00e9ration S+H (cache)", "Mini", "128", "$0.004", "$0.536"], ["Refinement", "Mini", "64", "$0.002", "$0.138"], ["Scan \u00e9ch\u00e9ances", "Mini", "160", "$0.0015", "$0.236"], ["Classification mail", "Mini", "40", "$0.002", "$0.076"], ["Classification PJ", "Mini", "30", "$0.002", "$0.057"], ["Analyse contacts", "Mini", "30", "$0.005", "$0.161"], ["D2 micro-analyse", "Mini", "64", "$0.001", "$0.045"], ["Recalibrage", "Mini", "20", "$0.017", "$0.335"], ["OCR", "Mini", "15", "$0.001", "$0.021"], ["Total Transition", "", "", "", "$1.63"]], c5),
      h2("Phase 3 \u2014 Autonomie (mensuel)"),
      tbl(["T\u00e2che", "Mod\u00e8le", "Appels/jour", "Co\u00fbt/jour", "Co\u00fbt/mois"], [["G\u00e9n\u00e9ration R (cache)", "Nano", "8", "$0.006", "$0.14"], ["G\u00e9n\u00e9ration S+H (cache)", "Mini", "16", "$0.063", "$1.39"], ["Refinement", "Mini", "10", "$0.022", "$0.47"], ["Scan \u00e9ch\u00e9ances", "Mini", "24", "$0.035", "$0.78"], ["Classification mail", "Mini", "6", "$0.011", "$0.25"], ["Classification PJ", "Mini", "5", "$0.010", "$0.21"], ["Analyse contacts", "Mini", "1", "$0.005", "$0.12"], ["D2 micro-analyse", "Mini", "10", "$0.007", "$0.15"], ["Recalibrage", "Mini", "1.5", "$0.025", "$0.55"], ["OCR", "Mini", "3", "$0.004", "$0.09"], ["Total/mois", "", "", "", "~$4.17"]], c5),

      new Paragraph({ children: [new PageBreak()] }),
      h1("4. R\u00e9dacteur faible \u2014 10 mails/jour, 60%, convergence 500 mails"),
      h2("Phase 1 \u2014 Formation (onboarding, one-shot)"),
      tbl(["T\u00e2che", "Mod\u00e8le", "Appels", "Co\u00fbt/appel", "Co\u00fbt total"], [["Analyse style + scoring", "Sonnet", "1", "$0.18", "$0.18"], ["Analyse contacts", "Mini", "~40", "$0.005", "$0.22"], ["Total Formation", "", "", "", "$0.40"]], c5),
      h2("Phase 2 \u2014 Transition (500 mails, ~50 jours)"),
      tbl(["T\u00e2che", "Mod\u00e8le", "Appels", "Co\u00fbt/appel", "Co\u00fbt total"], [["G\u00e9n\u00e9ration R (cache)", "Nano", "80", "$0.0008", "$0.064"], ["G\u00e9n\u00e9ration S+H (cache)", "Mini", "320", "$0.004", "$1.339"], ["Refinement", "Mini", "240", "$0.002", "$0.516"], ["Scan \u00e9ch\u00e9ances", "Mini", "400", "$0.0015", "$0.590"], ["Classification mail", "Mini", "100", "$0.002", "$0.190"], ["Classification PJ", "Mini", "75", "$0.002", "$0.143"], ["Analyse contacts", "Mini", "40", "$0.005", "$0.215"], ["D2 micro-analyse", "Mini", "240", "$0.001", "$0.168"], ["Recalibrage", "Mini", "50", "$0.017", "$0.838"], ["OCR", "Mini", "30", "$0.001", "$0.041"], ["Total Transition", "", "", "", "$4.10"]], c5),
      h2("Phase 3 \u2014 Autonomie (mensuel)"),
      tbl(["T\u00e2che", "Mod\u00e8le", "Appels/jour", "Co\u00fbt/jour", "Co\u00fbt/mois"], [["G\u00e9n\u00e9ration R (cache)", "Nano", "3", "$0.002", "$0.05"], ["G\u00e9n\u00e9ration S+H (cache)", "Mini", "5", "$0.020", "$0.44"], ["Refinement", "Mini", "5", "$0.011", "$0.23"], ["Scan \u00e9ch\u00e9ances", "Mini", "8", "$0.012", "$0.26"], ["Classification mail", "Mini", "2", "$0.004", "$0.08"], ["Classification PJ", "Mini", "2", "$0.004", "$0.08"], ["Analyse contacts", "Mini", "0.5", "$0.003", "$0.06"], ["D2 micro-analyse", "Mini", "5", "$0.004", "$0.08"], ["Recalibrage", "Mini", "0.5", "$0.008", "$0.18"], ["OCR", "Mini", "1", "$0.001", "$0.03"], ["Total/mois", "", "", "", "~$1.49"]], c5),

      new Paragraph({ children: [new PageBreak()] }),
      h1("5. Synth\u00e8se sur 12 mois"),
      tbl(["", "Bon r\u00e9dacteur", "R\u00e9dacteur moyen", "R\u00e9dacteur faible"], [["Volume", "30 mails/jour", "30 mails/jour", "10 mails/jour"], ["Correction", "20%", "40%", "60%"], ["Convergence", "50 mails (2 j)", "200 mails (7 j)", "500 mails (2.5 mois)"], ["Formation (one-shot)", "$0.61", "$0.61", "$0.40"], ["Transition (one-shot)", "$0.45", "$1.63", "$4.10"], ["Autonomie (\u00d7mois)", "$3.87 \u00d7 11.9 = $46.05", "$4.17 \u00d7 11.7 = $48.79", "$1.49 \u00d7 9.5 = $14.16"], ["Total 12 mois", "$47.11", "$51.03", "$18.66"], ["Total Moyenne/mois", "$3.93", "$4.25", "$1.56"]], [2400, 2200, 2200, 2200]),

      h1("6. Pricing & Marge"),
      tbl(["", "Co\u00fbt/mois", "Pricing 29\u20ac", "Marge/mois", "Marge %"], [["Bon r\u00e9dacteur", "$3.93", "29\u20ac", "$25.07", "86%"], ["R\u00e9dacteur moyen", "$4.25", "29\u20ac", "$24.75", "85%"], ["R\u00e9dacteur faible", "$1.56", "29\u20ac", "$27.44", "95%"], ["Total Moyenne pond\u00e9r\u00e9e", "$3.25", "29\u20ac", "$25.75", "89%"]], [2200, 1600, 1600, 1600, 1400]),

      new Paragraph({ children: [new PageBreak()] }),
      h1("7. Guide de codage \u2014 Mod\u00e8les par t\u00e2che"),
      tbl(["T\u00e2che", "Mod\u00e8le", "Cl\u00e9 API", "Pourquoi"], [["Onboarding (style + scoring)", "Sonnet", "Anthropic", "Fondation critique, 1 fois"], ["G\u00e9n\u00e9ration importance R", "GPT-5 nano", "OpenAI", "Mails courts, profil compense"], ["G\u00e9n\u00e9ration importance S+H", "GPT-5 mini", "OpenAI", "Qualit\u00e9 \u2605\u2605\u2605\u2605"], ["Refinement", "GPT-5 mini", "OpenAI", "R\u00e9daction"], ["Scan \u00e9ch\u00e9ances", "GPT-5 mini", "OpenAI", "Extraction structur\u00e9e"], ["Classification mail", "GPT-5 mini", "OpenAI", "Choix dans une liste"], ["Classification PJ", "GPT-5 mini", "OpenAI", "Choix dans une liste"], ["Analyse contacts", "GPT-5 mini", "OpenAI", "Extraction JSON"], ["D2 micro-analyse", "GPT-5 mini", "OpenAI", "Classification"], ["Recalibrage", "GPT-5 mini", "OpenAI", "R\u00e9-\u00e9criture sections"], ["OCR", "GPT-5 mini", "OpenAI", "Transcription"]], [2400, 1600, 1400, 3000]),
      p("2 cl\u00e9s API dans config.json : ANTHROPIC_API_KEY (onboarding uniquement) + OPENAI_API_KEY (tout le reste)", { italics: true, color: "666666" }),

      h1("8. Optimisations int\u00e9gr\u00e9es"),
      tbl(["Optimisation", "Impact", "Appliqu\u00e9e en"], [["Templates intelligents (20%)", "-6 appels g\u00e9n\u00e9ration/jour", "Transition + Autonomie"], ["Output court mails R (400 tokens)", "-$0.0008/mail R", "Transition + Autonomie"], ["Prompt caching 90%", "-90% sur 11K tokens syst\u00e8me", "Partout"], ["GPT-5 nano pour mails R", "-32% co\u00fbt g\u00e9n\u00e9ration", "Transition + Autonomie"]], [3400, 2800, 2200]),
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("C:\\Users\\yvanb\\OneDrive\\Desktop\\EasyMail\\pricing_easymail.docx", buffer);
  console.log("OK: pricing_easymail.docx cree");
});
