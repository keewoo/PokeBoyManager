import { afterEach, describe, expect, it } from "vitest";
import { getApiBaseUrl } from "@/lib/config";

describe("getApiBaseUrl", () => {
  const originalUrl = process.env.NEXT_PUBLIC_API_URL;

  afterEach(() => {
    process.env.NEXT_PUBLIC_API_URL = originalUrl;
  });

  it("falls back to localhost:8000 when unset", () => {
    delete process.env.NEXT_PUBLIC_API_URL;
    expect(getApiBaseUrl()).toBe("http://localhost:8000");
  });

  it("strips trailing slashes from a configured URL", () => {
    process.env.NEXT_PUBLIC_API_URL = "https://api.example.com/";
    expect(getApiBaseUrl()).toBe("https://api.example.com");
  });
});
