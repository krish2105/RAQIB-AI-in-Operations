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
  const base = new Date(now.getTime() - 50 * 60_000);
  const ulid = (i: number) => (Date.now() + i).toString(36).toUpperCase().padStart(26, "0").slice(-26);
  const arrivals = Array.from({ length: 150 }, (_, i) => ({
    id: ulid(i), site: SITE, camera: "cam1", ts: new Date(base.getTime() + i * 15_000).toISOString(), kind: "footfall_tick", severity: 1, payload: { zone: "entrance", track_id: i }, clip_path: null, rule_id: "R12",
  }));
  const queueId = ulid(999);
  const queue = { id: queueId, site: SITE, camera: "cam1", ts: new Date(now.getTime() - 60_000).toISOString(), kind: "queue_over", severity: 2, payload: { zone: "queue_till_1", till: 1, count: 7, sustained_s: 90, confidence: 0.86 }, clip_path: null, rule_id: "R10" };
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
  const card = page.locator("article").filter({ hasText: "Propose opening a till" }).first();
  await expect(card).toBeVisible();
  await card.getByTestId("approve").click();
  await expect(card.getByText("Executed")).toBeVisible();

  // Executed filter shows restock work orders created by the agent (shelf gaps in seeded history)
  await page.getByRole("tab", { name: "Executed" }).click();
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
