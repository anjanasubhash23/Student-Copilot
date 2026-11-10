"use client";

import katex from "katex";
import { Fragment, useMemo } from "react";

// Renders text with $inline$ and $$display$$ maths. Everything else is plain text: model output is never
// injected as HTML, only KaTeX's own output (KaTeX escapes its input; `trust` stays off).
const MATH = /(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$)/g;

function render(tex: string, display: boolean): string {
  try {
    return katex.renderToString(tex, { displayMode: display, throwOnError: false, trust: false, strict: "ignore" });
  } catch {
    return "";
  }
}

export function MathText({ text, className }: { text: string; className?: string }) {
  const parts = useMemo(() => text.split(MATH), [text]);
  return (
    <span className={className}>
      {parts.map((part, i) => {
        const display = part.startsWith("$$") && part.endsWith("$$") && part.length > 4;
        const inline = !display && part.startsWith("$") && part.endsWith("$") && part.length > 2;
        if (!display && !inline) return <Fragment key={i}>{part}</Fragment>;
        const html = render(display ? part.slice(2, -2) : part.slice(1, -1), display);
        return html ? <span key={i} dangerouslySetInnerHTML={{ __html: html }} /> : <Fragment key={i}>{part}</Fragment>;
      })}
    </span>
  );
}
