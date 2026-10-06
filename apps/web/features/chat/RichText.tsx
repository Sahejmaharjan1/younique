"use client";

import { useEffect, useState } from "react";
import { highlightCode } from "@/features/chat/highlight";

export function RichText({ text }: { text: string }) {
  const blocks = splitBlocks(text);
  return (
    <div className="rich">
      {blocks.map((block, index) => {
        if (block.kind === "code")
          return <CodeBlock key={index} code={block.body} lang={block.lang} />;
        if (block.kind === "table")
          return <DataTable key={index} rows={block.rows} />;
        if (block.kind === "csv")
          return <DataTable key={index} rows={parseCsv(block.body)} />;
        if (block.kind === "json")
          return <JsonTree key={index} text={block.body} />;
        if (block.kind === "pdf")
          return <PdfFrame key={index} text={block.body} />;
        return <p key={index}>{block.body}</p>;
      })}
    </div>
  );
}

function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [html, setHtml] = useState("");
  useEffect(() => {
    let live = true;
    void highlightCode(code, lang).then((value) => {
      if (live) setHtml(value);
    });
    return () => {
      live = false;
    };
  }, [code, lang]);
  if (!html) return <pre>{code}</pre>;
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}

function DataTable({ rows }: { rows: string[][] }) {
  if (rows.length === 0) return null;
  const [head, ...body] = rows;
  if (!head) return null;
  return (
    <table>
      <thead>
        <tr>
          {head.map((cell) => (
            <th key={cell}>{cell}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {body.map((row, index) => (
          <tr key={index}>
            {row.map((cell, cellIndex) => (
              <td key={cellIndex}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function JsonTree({ text }: { text: string }) {
  let pretty = text;
  try {
    pretty = JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    pretty = text;
  }
  return <pre>{pretty}</pre>;
}

function PdfFrame({ text }: { text: string }) {
  const srcDoc = `<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><p>${escapeHtml(text)}</p>`;
  return <iframe sandbox="" title="PDF preview" srcDoc={srcDoc} />;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

type Block =
  | { kind: "text"; body: string }
  | { kind: "code"; lang: string; body: string }
  | { kind: "table"; rows: string[][] }
  | { kind: "csv"; body: string }
  | { kind: "json"; body: string }
  | { kind: "pdf"; body: string };

function splitBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  const pattern = /```(\w+)?\n([\s\S]*?)```/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > cursor) blocks.push(...plainBlocks(text.slice(cursor, index)));
    const lang = match[1] || "text";
    const body = match[2] || "";
    if (lang === "csv") blocks.push({ kind: "csv", body });
    else if (lang === "json") blocks.push({ kind: "json", body });
    else if (lang === "pdf") blocks.push({ kind: "pdf", body });
    else blocks.push({ kind: "code", lang, body });
    cursor = index + match[0].length;
  }
  if (cursor < text.length) blocks.push(...plainBlocks(text.slice(cursor)));
  return blocks.length ? blocks : [{ kind: "text", body: text }];
}

function plainBlocks(text: string): Block[] {
  const lines = text.split("\n");
  const blocks: Block[] = [];
  let buffer: string[] = [];
  const flush = () => {
    if (buffer.length) {
      blocks.push({ kind: "text", body: buffer.join("\n").trim() });
      buffer = [];
    }
  };
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (line === undefined) break;
    const next = lines[index + 1];
    if (line.includes("|") && next?.includes("---")) {
      flush();
      const rows: string[][] = [];
      while (index < lines.length) {
        const rowLine = lines[index];
        if (rowLine === undefined || !rowLine.includes("|")) break;
        if (!rowLine.includes("---")) {
          rows.push(
            rowLine
              .split("|")
              .map((cell) => cell.trim())
              .filter(Boolean),
          );
        }
        index += 1;
      }
      blocks.push({ kind: "table", rows });
      continue;
    }
    buffer.push(line);
    index += 1;
  }
  flush();
  return blocks.filter((block) => block.kind !== "text" || block.body);
}

function parseCsv(text: string): string[][] {
  return text
    .trim()
    .split("\n")
    .map((line) => line.split(",").map((cell) => cell.trim()));
}
