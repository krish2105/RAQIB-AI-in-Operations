import { describe, expect, it } from "vitest";
import ar from "@/messages/ar.json";
import en from "@/messages/en.json";
import hi from "@/messages/hi.json";
import { dirFor, routing } from "@/i18n/routing";

function keys(obj: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) => (v && typeof v === "object" ? keys(v as Record<string, unknown>, `${prefix}${k}.`) : [`${prefix}${k}`]));
}

describe("message catalogues", () => {
  const enKeys = keys(en).sort();
  it("hi has every en key and nothing extra", () => {
    expect(keys(hi).sort()).toEqual(enKeys);
  });
  it("ar has every en key and nothing extra", () => {
    expect(keys(ar).sort()).toEqual(enKeys);
  });
  it("no empty strings in any catalogue", () => {
    for (const cat of [en, hi, ar]) {
      const flat = JSON.stringify(cat);
      expect(flat).not.toMatch(/":\s*""/);
    }
  });
  it("ICU placeholders match across languages", () => {
    // named arguments only: `{name}` or `{name, plural …}`; not the `{no events}` text inside a plural case
    const ph = (s: string) => (s.match(/\{[a-zA-Z_]+(?=[,}])/g) ?? []).sort().join(",");
    const flat = (o: Record<string, unknown>) => Object.fromEntries(keys(o).map((k) => [k, k.split(".").reduce<unknown>((acc, p) => (acc as Record<string, unknown>)[p], o) as string]));
    const e = flat(en), h = flat(hi), a = flat(ar);
    for (const k of Object.keys(e)) {
      expect(ph(h[k]), `hi:${k}`).toBe(ph(e[k]));
      expect(ph(a[k]), `ar:${k}`).toBe(ph(e[k]));
    }
  });
});

describe("routing", () => {
  it("supports en, hi, ar and marks ar as RTL", () => {
    expect([...routing.locales]).toEqual(["en", "hi", "ar"]);
    expect(dirFor("ar")).toBe("rtl");
    expect(dirFor("hi")).toBe("ltr");
    expect(dirFor("en")).toBe("ltr");
  });
});
