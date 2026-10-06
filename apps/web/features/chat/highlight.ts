export async function highlightCode(
  code: string,
  lang: string,
): Promise<string> {
  if (code.split("\n").length > 200 && typeof Worker !== "undefined") {
    try {
      return await highlightInWorker(code, lang);
    } catch {
      return highlightInline(code, lang);
    }
  }
  return highlightInline(code, lang);
}

async function highlightInline(code: string, lang: string): Promise<string> {
  try {
    const shiki = await import("shiki");
    return await shiki.codeToHtml(code, {
      lang: lang || "text",
      theme: "github-light",
    });
  } catch {
    return `<pre>${escapeHtml(code)}</pre>`;
  }
}

function highlightInWorker(code: string, lang: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(
      new URL("./highlight.worker.ts", import.meta.url),
    );
    const timer = setTimeout(() => {
      worker.terminate();
      reject(new Error("highlight timeout"));
    }, 8000);
    worker.onmessage = (event: MessageEvent<string>) => {
      clearTimeout(timer);
      worker.terminate();
      resolve(event.data);
    };
    worker.onerror = () => {
      clearTimeout(timer);
      worker.terminate();
      reject(new Error("highlight worker failed"));
    };
    worker.postMessage({ code, lang });
  });
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
