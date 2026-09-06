"use client";

/**
 * Supabase Auth on the client: magic link and Google. The session token is attached to every API request
 * as a Bearer header; the API verifies it server-side and maps the user to a role in its own users table.
 * Without NEXT_PUBLIC_SUPABASE_URL the app runs signed out (the API's AUTH_REQUIRED=false dev mode).
 */
import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";
import { useEffect, useState } from "react";

export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

let client: SupabaseClient | null = null;
let accessToken: string | null = null;

export function supabase(): SupabaseClient | null {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY || typeof window === "undefined") return null;
  if (!client) {
    client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } });
    client.auth.onAuthStateChange((_e, s) => {
      accessToken = s?.access_token ?? null;
    });
    client.auth.getSession().then(({ data }) => {
      accessToken = data.session?.access_token ?? null;
    });
  }
  return client;
}

/** Current bearer token, if any (synchronous so the API client can add the header). Exported for tests. */
export function currentToken(): string | null {
  return accessToken;
}

export function setTokenForTests(t: string | null): void {
  accessToken = t;
}

export function authHeaders(base: HeadersInit | undefined, token: string | null = currentToken()): HeadersInit {
  return token ? { ...(base || {}), Authorization: `Bearer ${token}` } : base || {};
}

export function useSession(): { session: Session | null; ready: boolean; enabled: boolean } {
  const enabled = !!SUPABASE_URL && !!SUPABASE_ANON_KEY;
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(!enabled); // signed-out mode is ready at once; otherwise wait for getSession()
  useEffect(() => {
    const c = supabase();
    if (!c) return;
    c.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data: sub } = c.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);
  return { session, ready, enabled };
}

export async function signInWithEmail(email: string, redirectTo: string): Promise<{ error: string | null }> {
  const c = supabase();
  if (!c) return { error: "auth not configured" };
  const { error } = await c.auth.signInWithOtp({ email, options: { emailRedirectTo: redirectTo } });
  return { error: error?.message ?? null };
}

export async function signInWithGoogle(redirectTo: string): Promise<{ error: string | null }> {
  const c = supabase();
  if (!c) return { error: "auth not configured" };
  const { error } = await c.auth.signInWithOAuth({ provider: "google", options: { redirectTo } });
  return { error: error?.message ?? null };
}

export async function signOut(): Promise<void> {
  await supabase()?.auth.signOut();
  accessToken = null;
}
