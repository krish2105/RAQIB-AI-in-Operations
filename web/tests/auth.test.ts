import { describe, expect, it } from "vitest";
import { authHeaders, currentToken, setTokenForTests } from "@/lib/auth";

describe("auth headers", () => {
  it("adds a bearer header only when a session token exists", () => {
    setTokenForTests(null);
    expect(currentToken()).toBeNull();
    expect(authHeaders({ "content-type": "application/json" })).toEqual({ "content-type": "application/json" });
    setTokenForTests("tok.en");
    expect(authHeaders({ "content-type": "application/json" })).toEqual({ "content-type": "application/json", Authorization: "Bearer tok.en" });
    expect(authHeaders(undefined)).toEqual({ Authorization: "Bearer tok.en" });
    setTokenForTests(null);
  });
});
