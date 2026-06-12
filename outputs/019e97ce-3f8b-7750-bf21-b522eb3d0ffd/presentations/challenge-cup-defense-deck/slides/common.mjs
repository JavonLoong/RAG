export const C = {
  ink: "#152033",
  sub: "#526173",
  quiet: "#7B8798",
  paper: "#F7F8FA",
  line: "#D8DEE8",
  blue: "#2457A6",
  cyan: "#1499A5",
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

export function shape(slide, ctx, x, y, w, h, fill, line = "#00000000") {
  return ctx.addShape(slide, { x, y, w, h, fill, line: ctx.line(line, line === "#00000000" ? 0 : 1) });
}

export function text(slide, ctx, value, x, y, w, h, opts = {}) {
  ctx.addText(slide, {
    text: value,
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

export function metric(slide, ctx, item, x, y, w = 138) {
  text(slide, ctx, item.value, x, y, w, 38, { size: 29, bold: true, color: item.color ?? C.blue, face: "Aptos Display" });
  text(slide, ctx, item.label, x, y + 40, w + 10, 38, { size: 12.5, color: C.sub });
}

export function footer(slide, ctx, number) {
  text(slide, ctx, "知燃知维 · Challenge Cup defense deck", 54, 682, 520, 18, { size: 11.5, color: C.quiet, face: "Aptos" });
  text(slide, ctx, String(number).padStart(2, "0"), 1200, 680, 42, 20, { size: 11.5, color: C.quiet, align: "right", face: "Aptos" });
}

export async function renderSlide(slide, ctx, spec) {
  shape(slide, ctx, 0, 0, 1280, 720, spec.dark ? C.navy : C.paper);
  const titleColor = spec.dark ? C.white : C.ink;
  const subColor = spec.dark ? "#C9D6E7" : C.sub;
  text(slide, ctx, spec.kicker.toUpperCase(), 54, 34, 620, 22, { size: 12, bold: true, color: spec.dark ? "#76D6E2" : C.cyan, face: "Aptos" });
  text(slide, ctx, spec.title, 54, 62, 980, 64, { size: spec.titleSize ?? 29, bold: true, color: titleColor });
  text(slide, ctx, spec.subtitle ?? "", 56, 126, 1000, 32, { size: 15.5, color: subColor });
  shape(slide, ctx, 54, 164, 1160, 1, spec.dark ? "#37506E" : C.line);

  if (spec.metrics) {
    const startX = spec.metricStartX ?? 70;
    spec.metrics.forEach((item, idx) => metric(slide, ctx, item, startX + idx * 172, spec.metricY ?? 204));
  }

  if (spec.bullets) {
    let y = spec.bulletY ?? 268;
    spec.bullets.forEach((item) => {
      shape(slide, ctx, 72, y + 8, 9, 9, item.color ?? C.cyan);
      text(slide, ctx, item.text, 96, y, spec.bulletW ?? 520, 44, { size: item.size ?? 17, color: spec.dark ? C.white : C.ink, bold: item.bold ?? false });
      y += item.gap ?? 58;
    });
  }

  if (spec.cards) {
    spec.cards.forEach((card) => {
      shape(slide, ctx, card.x, card.y, card.w, card.h, card.fill ?? C.white, card.line ?? C.line);
      text(slide, ctx, card.title, card.x + 18, card.y + 16, card.w - 36, 26, { size: 18, bold: true, color: card.color ?? C.blue });
      text(slide, ctx, card.body, card.x + 18, card.y + 54, card.w - 36, card.h - 66, { size: 15.5, color: C.ink });
    });
  }

  if (spec.image) {
    shape(slide, ctx, spec.image.x - 8, spec.image.y - 8, spec.image.w + 16, spec.image.h + 16, C.white, C.line);
    await ctx.addImage(slide, {
      path: spec.image.path,
      x: spec.image.x,
      y: spec.image.y,
      w: spec.image.w,
      h: spec.image.h,
      fit: spec.image.fit ?? "contain",
      alt: spec.image.alt ?? spec.title,
    });
  }

  if (spec.callout) {
    shape(slide, ctx, spec.callout.x, spec.callout.y, spec.callout.w, spec.callout.h, spec.callout.fill ?? C.paleAmber, spec.callout.line ?? "#E0C078");
    text(slide, ctx, spec.callout.text, spec.callout.x + 18, spec.callout.y + 16, spec.callout.w - 36, spec.callout.h - 26, { size: 16.5, bold: spec.callout.bold ?? true, color: spec.callout.color ?? C.ink });
  }
  footer(slide, ctx, spec.number);
}
