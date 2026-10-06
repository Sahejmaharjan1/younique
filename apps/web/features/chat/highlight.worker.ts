/// <reference lib="webworker" />

export {};

self.onmessage = (event: MessageEvent<{ code: string; lang: string }>) => {
  const { code, lang } = event.data;
  void import("shiki")
    .then((shiki) =>
      shiki.codeToHtml(code, { lang: lang || "text", theme: "github-light" }),
    )
    .then((html) => {
      self.postMessage(html);
    })
    .catch(() => {
      self.postMessage(`<pre>${code.replace(/</g, "&lt;")}</pre>`);
    });
};
