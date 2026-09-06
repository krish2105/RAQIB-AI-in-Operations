import { expect, test } from "@playwright/test";

const API = process.env.API_URL || "http://localhost:8011";
const SITE = "raqib_demo_store";

/** Event appears → open it → clip/overlay visible → approve a proposal → executed + tool call logged. */
test("grader path: event → clip → approve proposal → restock task", async ({ page, request }) => {
  // Fresh, deterministic history; the agent handles the last hours so proposals exist.
  const seed = await request.post(`${API}/admin/seed?site=${SITE}&days=21&run_agent_last_hours=12`);
  expect(seed.ok()).toBeTruthy();

  // A live-looking queue event with heavy arrivals in the same hour so rho > 0.85 → propose_open_till.
  const now = new Date();
  const ulid = (i: number) => (Date.now() + i).toString(36).toUpperCase().padStart(26, "0").slice(-26);
  // 150 arrivals spread over the last 50 minutes, dense enough that the slot holding the queue event has rho > 0.85.
  // ρ is computed per 15-minute slot, so the queue event sits at the last second of the most recent
  // complete slot and the arrivals fill that slot: the fixture is then independent of the wall clock.
  const slotStart = new Date(Math.floor(now.getTime() / 900_000) * 900_000);
  const prevSlot = new Date(slotStart.getTime() - 900_000);
  const arrivals = Array.from({ length: 150 }, (_, i) => ({
    id: ulid(i), site: SITE, camera: "cam1", ts: new Date(prevSlot.getTime() + i * 6_000).toISOString(), kind: "footfall_tick", severity: 1, payload: { zone: "entrance", track_id: i }, clip_path: null, rule_id: "R12",
  }));
  const queueId = ulid(999);
  const queue = { id: queueId, site: SITE, camera: "cam1", ts: new Date(slotStart.getTime() - 1_000).toISOString(), kind: "queue_over", severity: 2, payload: { zone: "queue_till_1", till: 1, count: 7, sustained_s: 90, confidence: 0.86 }, clip_path: null, rule_id: "R10" };
  const batch = await request.post(`${API}/events/batch`, { data: { events: [...arrivals, queue] } });
  expect(batch.ok()).toBeTruthy();
  const clip = await request.put(`${API}/clips/${queueId}`, { multipart: { file: { name: "c.mp4", mimeType: "video/mp4", buffer: Buffer.from("\x00\x00\x00\x18ftypmp42" + "x".repeat(64)) } } });
  expect(clip.status()).toBe(201);

  await page.goto("/en");
  await expect(page.getByRole("heading", { level: 1 })).toBeAttached();
  // The event appears in the stream
  const row = page.getByRole("listitem").filter({ hasText: "Queue over limit" }).first();
  await expect(row).toBeVisible();
  await row.getByRole("link", { name: "Open" }).click();

  await expect(page).toHaveURL(/\/events\//);
  await expect(page.getByTestId("clip")).toBeVisible();
  await expect(page.getByText(/^R10 — /)).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: "Queue over limit" })).toBeVisible();

  // Actions: approve the open-till proposal
  await page.goto("/en/actions");
  const first = page.locator("article").filter({ hasText: "Propose opening a till" }).first();
  await expect(first).toBeVisible();
  // Pin this exact card by its action id: seeded history may hold several open-till proposals.
  const testId = (await first.getAttribute("data-testid"))!;
  const card = page.getByTestId(testId);
  await card.getByTestId("approve").click();
  // Approved → executed: the card leaves the Proposed filter and appears under Executed with the decision recorded.
  await expect(card).toBeHidden();
  await page.getByRole("tab", { name: "Executed" }).click();
  const executed = page.getByTestId(testId);
  await expect(executed).toBeVisible();
  await expect(executed.getByText("Executed")).toBeVisible();
  await expect(executed.getByText("by operator")).toBeVisible();

  // Restock work orders raised autonomously for shelf gaps in the seeded history
  await expect(page.locator("article").filter({ hasText: "Create work order" }).first()).toBeVisible();

  // Audit table registered calls
  await expect(page.getByText("propose_open_till")).toBeVisible();
});

test("theme toggle and RTL locale", async ({ page }) => {
  await page.goto("/en");
  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Switch theme" }).click();
  await expect(html).toHaveAttribute("data-theme", "light");
  await page.goto("/ar");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByText("لوحة التحكم").first()).toBeVisible();
});

test("ask: cited answer, chip opens the event page", async ({ page, request }) => {
  // Index the seeded history (the first test seeds 21 days) so Ask has records to retrieve.
  const ix = await request.post(`${API}/admin/index?site=${SITE}&days=21`);
  expect(ix.ok()).toBeTruthy();
  await page.goto("/en/ask");
  await page.getByTestId("ask-input").fill("Which till had the longest queue last Friday evening?");
  await page.getByTestId("ask-submit").click();
  const card = page.getByTestId("answer-card");
  await expect(card).toBeVisible();
  const chips = card.getByTestId("citation");
  await expect(chips.first()).toBeVisible();
  expect(await chips.count()).toBeGreaterThanOrEqual(1);
  await expect(card.getByTestId("cite-ref").first()).toBeVisible();
  await chips.first().click();
  await expect(page).toHaveURL(/\/events\//);
  await expect(page.getByRole("heading", { level: 1, name: "Queue over limit" })).toBeVisible();
});
