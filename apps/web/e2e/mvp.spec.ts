import { expect, test, type Page } from "@playwright/test";

const EICAR =
  "X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*";

function jwt(email: string) {
  const segment = (value: object) =>
    Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${segment({ alg: "none", typ: "JWT" })}.${segment({
    sub: email,
    email,
    email_verified: true,
    firebase: { sign_in_provider: "password" },
  })}.sig`;
}

async function signIn(page: Page, email: string) {
  await page.route("**/identitytoolkit.googleapis.com/**", async (route) => {
    const body = route.request().postDataJSON() as { email?: string };
    await route.fulfill({
      json: {
        idToken: jwt(body.email || email),
        email: body.email || email,
        localId: body.email || email,
      },
    });
  });
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("password-123");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByRole("heading", { name: "Accept the current terms" }),
  ).toBeVisible();
  await acceptConsents(page);
  await expect(page.getByRole("heading", { name: "New chat" })).toBeVisible({
    timeout: 15_000,
  });
}

async function acceptConsents(page: Page) {
  await expect(
    page.getByRole("button", { name: "Accept" }).first(),
  ).toBeVisible();
  let previous = await page.getByRole("button", { name: "Accept" }).count();
  while (previous > 0 && !page.url().includes("/chat/new")) {
    await page
      .getByRole("button", { name: "Accept" })
      .first()
      .click({ noWaitAfter: true });
    await expect
      .poll(async () => page.getByRole("button", { name: "Accept" }).count())
      .toBeLessThan(previous);
    previous = await page.getByRole("button", { name: "Accept" }).count();
  }
}

test("E1 signup and consent lands in the app", async ({ page }) => {
  await signIn(page, `e1-${Date.now()}@example.com`);
  await expect(page.getByRole("button", { name: "Start" })).toBeVisible();
});

test("E2 invalid key is rejected and a valid key stays masked", async ({
  page,
}) => {
  await signIn(page, `e2-${Date.now()}@example.com`);
  await page.goto("/settings/keys");
  await page.getByLabel("Key").fill("nope");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("rejected this key")).toBeVisible();
  const saved = page.waitForResponse(
    (response) =>
      response.url().includes("/provider-keys") &&
      response.request().method() === "POST",
  );
  await page.getByLabel("Key").fill("valid-key");
  await page.getByRole("button", { name: "Save" }).click();
  const response = await saved;
  const payload = await response.text();
  expect(payload).not.toContain("valid-key");
  await expect(page.getByText("last four characters: -key")).toBeVisible();
  await page.getByRole("button", { name: "Rotate" }).click();
  await expect(page.getByText("last four characters:")).toBeVisible();
  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByText("revoked")).toBeVisible();
});

test("E3 streaming can be stopped and regenerated", async ({ page }) => {
  await signIn(page, `e3-${Date.now()}@example.com`);
  await openChat(page);
  await page.getByLabel("Message").fill("stream a long answer");
  const stop = page.getByRole("button", { name: "Stop" });
  await page.getByRole("button", { name: "Send" }).click();
  await expect(stop).toBeVisible({ timeout: 10_000 });
  await stop.click();
  await expect(page.getByText("Stopped. Partial output was kept.")).toBeVisible(
    { timeout: 15_000 },
  );
  await page.getByRole("button", { name: "Regenerate" }).click();
  await expect(page.getByText("Previous answer")).toBeVisible();
});

async function openChat(page: Page) {
  await page.goto("/chat/new");
  const start = page.getByRole("button", { name: "Start" });
  await expect(start).toBeVisible();
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (/\/chat\/(?!new)/.test(page.url())) break;
    await start.click();
    try {
      await page.waitForURL(/\/chat\/(?!new)/, { timeout: 5000 });
    } catch {
      continue;
    }
  }
  await expect(page.getByLabel("Message")).toBeVisible();
}

test("E4 smtp approval sends the captured message", async ({ page }) => {
  await signIn(page, `e4-${Date.now()}@example.com`);
  await page.goto("/connections");
  await page.getByRole("button", { name: "Connect SMTP" }).click();
  await expect(page.getByText("SMTP connected")).toBeVisible();
  await openChat(page);
  await page.getByLabel("Message").fill("send an email to ops@example.com");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByRole("heading", { name: /Approve smtp.send/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect
    .poll(async () => {
      const mailbox = await page.request.get("/api/v1/dev/mailbox");
      const body = (await mailbox.json()) as { data: { tool: string }[] };
      return body.data.filter((item) => item.tool === "smtp.send").length;
    })
    .toBeGreaterThan(0);
});

test("E5 never policy explains the refusal and does not call the provider", async ({
  page,
}) => {
  await signIn(page, `e5-${Date.now()}@example.com`);
  const before = await page.request.get("/api/v1/dev/mailbox");
  const prior = (
    (await before.json()) as { data: { tool: string }[] }
  ).data.filter((item) => item.tool === "gmail.send_email").length;
  await page.goto("/settings/tool-policies");
  await page.getByRole("button", { name: "Never send mail" }).click();
  await expect(page.getByText("gmail.send_email is never")).toBeVisible();
  await openChat(page);
  await page
    .getByLabel("Message")
    .fill("send a gmail email to ops@example.com");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("blocked by policy").first()).toBeVisible();
  const after = await page.request.get("/api/v1/dev/mailbox");
  const next = (
    (await after.json()) as { data: { tool: string }[] }
  ).data.filter((item) => item.tool === "gmail.send_email").length;
  expect(next).toBe(prior);
});

test("E6 an approval survives a second page", async ({ page }) => {
  await signIn(page, `e6-${Date.now()}@example.com`);
  await openChat(page);
  await page
    .getByLabel("Message")
    .fill("send an email to ops@example.com about the handoff");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
  const chatUrl = page.url();
  const second = await page.context().newPage();
  await second.goto("/approvals");
  await expect(
    second.getByRole("heading", { name: "Approvals" }),
  ).toBeVisible();
  await second.getByRole("button", { name: "Approve" }).click();
  await page.goto(chatUrl);
  await expect(page.getByText(/I'll send that email|Sent\./)).toBeVisible();
  await second.close();
});

test("E7 an EICAR upload is infected and not downloadable", async ({
  page,
}) => {
  await signIn(page, `e7-${Date.now()}@example.com`);
  await page.goto("/artifacts");
  await page.getByLabel("Upload file").setInputFiles({
    name: "eicar.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(EICAR),
  });
  await expect(page.getByText("eicar.txt · infected")).toBeVisible();
  await page.getByRole("button", { name: "Download" }).click();
  await expect(
    page.getByText("blocked while the file is infected"),
  ).toBeVisible();
});

test("E8 a share link cannot reach private resources and revoke cuts it off", async ({
  page,
  browser,
}) => {
  await signIn(page, `e8-${Date.now()}@example.com`);
  await openChat(page);
  await page.getByLabel("Message").fill("hello share");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Hello from Younique.").first()).toBeVisible();
  await page.getByRole("button", { name: "Share" }).click();
  const tokenText = await page.getByText(/Share token /).innerText();
  const token = tokenText.replace("Share token ", "").trim();
  const anon = await browser.newContext();
  const visitor = await anon.newPage();
  await visitor.goto(`/share/${token}`);
  await expect(visitor.getByText("Hello from Younique.")).toBeVisible();
  const connections = await visitor.request.get("/api/v1/connections");
  expect([401, 403, 404]).toContain(connections.status());
  await page.getByRole("button", { name: "Revoke share" }).click();
  await visitor.reload();
  await expect(visitor.getByText("not active")).toBeVisible();
  await anon.close();
});

test("E9 switching accounts isolates sessions", async ({ page }) => {
  const stamp = Date.now();
  await signIn(page, `e9a-${stamp}@example.com`);
  const firstId = (
    await page.getByRole("button", { name: /^Current / }).innerText()
  )
    .replace(/^Current\s+/, "")
    .trim();
  await page.goto("/login");
  await page.getByLabel("Email").fill(`e9b-${stamp}@example.com`);
  await page.getByLabel("Password").fill("password-123");
  await page.getByRole("button", { name: "Continue" }).click();
  await acceptConsents(page);
  await page.goto("/artifacts");
  await page.getByRole("button", { name: /^Switch / }).click();
  await expect(
    page.getByRole("button", { name: `Current ${firstId}` }),
  ).toBeVisible();
  await page.goto("/settings/sessions");
  await page.getByRole("button", { name: "Revoke" }).click();
  await page.evaluate(() =>
    window.localStorage.removeItem("younique.accountId"),
  );
  const mine = await page.request.get("/api/v1/me");
  expect(mine.status()).toBe(200);
  const switched = await page.request.get("/api/v1/me", {
    headers: { "x-account-id": firstId },
  });
  expect(switched.status()).toBe(401);
  const third = await page.request.get("/api/v1/me", {
    headers: { "x-account-id": "00000000-0000-7000-8000-000000000099" },
  });
  expect(third.status()).toBe(401);
});
