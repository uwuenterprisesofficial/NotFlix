import { headers } from "next/headers";

const API_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Server-side call to the FastAPI backend, forwarding the visitor's session cookie. */
export async function api<T>(path: string): Promise<T> {
  // Forward the raw header: cookies().toString() URL-encodes values, which breaks the signature
  // of the backend's session cookie.
  const cookie = (await headers()).get("cookie");
  const res = await fetch(`${API_URL}${path}`, {
    headers: cookie ? { cookie } : {},
    cache: "no-store",
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json() as Promise<T>;
}

/** Like `api`, but resolves to null for 401/404 instead of throwing. */
export async function apiOrNull<T>(path: string): Promise<T | null> {
  try {
    return await api<T>(path);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 404)) return null;
    throw e;
  }
}
