export const C = {
  ink: "#172033",
  sub: "#566176",
  quiet: "#7A8496",
  paper: "#F7F8FA",
  line: "#D7DCE5",
  blue: "#2457A6",
  cyan: "#1897A6",
  green: "#2F7D59",
  amber: "#B7791F",
  red: "#B54747",
  navy: "#10243F",
  white: "#FFFFFF",
  paleBlue: "#EAF1FB",
  paleGreen: "#EAF6EF",
  paleAmber: "#FFF4DA",
  paleRed: "#FBEAEA",
};

export function bg(slide, ctx, color = C.paper) {
  ctx.addShape(slide, { x: 0, y: 0, w: 1280, h: 720, fill: color, line: ctx.line("#00000000", 0) });
}

export function footer(slide, ctx, n) {
  ctx.addText(slide, { text: "Power Equipment RAG · academic report",
    x: 54, y: 682, w: 520, h: 20, fontSize: 12, color: C.quiet, typeface: "Aptos",
  });
  ctx.addText(slide, { text: String(n).padStart(2, "0"),
    x: 1200, y: 680, w: 40, h: 22, fontSize: 12, color: C.quiet, align: "right", typeface: "Aptos",
  });
}

export function title(slide, ctx, kicker, claim, n) {
  ctx.addText(slide, { text: kicker.toUpperCase(),
    x: 54, y: 34, w: 360, h: 24, fontSize: 12, bold: true, color: C.cyan, typeface: "Aptos",
  });
  ctx.addText(slide, { text: claim,
    x: 54, y: 62, w: 980, h: 58, fontSize: 30, bold: true, color: C.ink, typeface: "Microsoft YaHei",
  });
  ctx.addShape(slide, { x: 54, y: 128, w: 1160, h: 1, fill: C.line, line: ctx.line("#00000000", 0) });
  footer(slide, ctx, n);
}

export function label(slide, ctx, text, x, y, w, h, opts = {}) {
  ctx.addText(slide, { text,
    x, y, w, h,
    fontSize: opts.size ?? 16,
    bold: opts.bold ?? false,
    color: opts.color ?? C.ink,
    typeface: opts.face ?? "Microsoft YaHei",
    align: opts.align ?? "left",
    valign: opts.valign ?? "top",
    insets: opts.insets ?? { left: 0, right: 0, top: 0, bottom: 0 },
  });
}

export function box(slide, ctx, x, y, w, h, fill = C.white, line = C.line) {
  return ctx.addShape(slide, { x, y, w, h, fill, line: ctx.line(line, 1) });
}

export function metric(slide, ctx, value, name, x, y, color = C.blue) {
  ctx.addText(slide, { text: value, x, y, w: 130, h: 38, fontSize: 30, bold: true, color, typeface: "Aptos Display" });
  ctx.addText(slide, { text: name, x, y: y + 42, w: 150, h: 36, fontSize: 13, color: C.sub, typeface: "Microsoft YaHei" });
}

export function bar(slide, ctx, labelText, value, max, x, y, w, color, suffix = "") {
  const display = Number.isFinite(value) && Math.abs(value) < 10
    ? String(Number(value.toFixed(3))).replace(/\.0$/, "")
    : String(value);
  label(slide, ctx, labelText, x, y - 2, 180, 24, { size: 14, color: C.sub });
  ctx.addShape(slide, { x: x + 190, y, w, h: 18, fill: "#E6EAF0", line: ctx.line("#00000000", 0) });
  ctx.addShape(slide, { x: x + 190, y, w: Math.max(4, w * value / max), h: 18, fill: color, line: ctx.line("#00000000", 0) });
  label(slide, ctx, `${display}${suffix}`, x + 200 + w, y - 3, 90, 24, { size: 14, bold: true, color });
}

export function stage(slide, ctx, index, text, x, y, w, h, fill) {
  box(slide, ctx, x, y, w, h, fill, "#C9D2DF");
  ctx.addText(slide, { text: String(index), x: x + 14, y: y + 14, w: 32, h: 30, fontSize: 18, bold: true, color: C.blue, typeface: "Aptos" });
  label(slide, ctx, text, x + 52, y + 14, w - 66, h - 24, { size: 15, bold: true, color: C.ink });
}

export function smallNote(slide, ctx, text, x, y, w, h) {
  label(slide, ctx, text, x, y, w, h, { size: 13, color: C.sub });
}
