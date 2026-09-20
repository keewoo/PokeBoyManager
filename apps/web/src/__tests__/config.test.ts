import { afterEach, describe, expect, it } from "vitest";
import { getApiBaseUrl, getServerApiBaseUrl } from "@/lib/config";

describe("getApiBaseUrl", () => {
  const originalUrl = process.env.NEXT_PUBLIC_API_URL;

  afterEach(() => {
    process.env.NEXT_PUBLIC_API_URL = originalUrl;
  });

  it("falls back to a relative /api (never a hardcoded host) when unset", () => {
    delete process.env.NEXT_PUBLIC_API_URL;
    expect(getApiBaseUrl()).toBe("/api");
  });

  it("strips trailing slashes from a configured URL", () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com/";
    expect(getApiBaseUrl()).toBe("https://api.example.com");
  });
});

describe("getServerApiBaseUrl", () => {
  const originalUrl = process.env.NEXT_PUBLIC_API_URL;

  afterEach(() => {
    process.env.NEXT_PUBLIC_API_URL = originalUrl;
  });

  it("returns null without NEXT_PUBLIC_API_URL — a server fetch has no implicit origin to resolve a relative URL against", () => {
    delete process.env.NEXT_PUBLIC_API_URL;
    expect(getServerApiBaseUrl()).toBeNull();
  });

  it("returns the configured absolute URL, trailing slash stripped", () => {
    process.env.NEXT_PUBLIC_API_URL = "https://pokeboy.acx-connect.com/api/";
    expect(getServerApiBaseUrl()).toBe("https://pokeboy.acx-connect.com/api");
  });
});
