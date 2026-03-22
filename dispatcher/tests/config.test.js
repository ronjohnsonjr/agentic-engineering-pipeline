import { describe, it, expect, beforeEach, afterEach } from "@jest/globals";
import { loadConfig } from "../src/config.js";

describe("loadConfig", () => {
  let originalEnv;

  beforeEach(() => {
    originalEnv = { ...process.env };
  });

  afterEach(() => {
    // Restore original env
    for (const key of Object.keys(process.env)) {
      if (!(key in originalEnv)) {
        delete process.env[key];
      }
    }
    Object.assign(process.env, originalEnv);
  });

  function setRequiredVars() {
    process.env.ANTHROPIC_API_KEY = "anthropic-key";
    process.env.LINEAR_API_KEY = "linear-key";
    process.env.LINEAR_TEAM_ID = "team-id-123";
    process.env.GITHUB_TOKEN = "gh-token";
    process.env.GITHUB_REPO = "owner/repo";
  }

  it("throws when required vars are missing", () => {
    delete process.env.ANTHROPIC_API_KEY;
    delete process.env.LINEAR_API_KEY;
    delete process.env.LINEAR_TEAM_ID;
    delete process.env.GITHUB_TOKEN;
    delete process.env.GITHUB_REPO;

    expect(() => loadConfig()).toThrow(/Missing required environment variables/);
  });

  it("lists all missing vars in the error message", () => {
    delete process.env.ANTHROPIC_API_KEY;
    delete process.env.LINEAR_API_KEY;
    delete process.env.LINEAR_TEAM_ID;
    delete process.env.GITHUB_TOKEN;
    delete process.env.GITHUB_REPO;

    expect(() => loadConfig()).toThrow(/ANTHROPIC_API_KEY/);
    expect(() => loadConfig()).toThrow(/LINEAR_API_KEY/);
  });

  it("returns correct config with all vars set", () => {
    setRequiredVars();
    process.env.POLL_INTERVAL_MS = "60000";
    process.env.MAX_CONCURRENT_SESSIONS = "5";
    process.env.LINEAR_TRIGGER_STATUS = "In Testing";

    const config = loadConfig();
    expect(config.anthropicApiKey).toBe("anthropic-key");
    expect(config.linearApiKey).toBe("linear-key");
    expect(config.linearTeamId).toBe("team-id-123");
    expect(config.githubToken).toBe("gh-token");
    expect(config.githubRepo).toBe("owner/repo");
    expect(config.pollIntervalMs).toBe(60000);
    expect(config.maxConcurrentSessions).toBe(5);
    expect(config.linearTriggerStatus).toBe("In Testing");
  });

  it("uses defaults for optional vars", () => {
    setRequiredVars();
    delete process.env.POLL_INTERVAL_MS;
    delete process.env.MAX_CONCURRENT_SESSIONS;
    delete process.env.LINEAR_TRIGGER_STATUS;

    const config = loadConfig();
    expect(config.pollIntervalMs).toBe(30000);
    expect(config.maxConcurrentSessions).toBe(3);
    expect(config.linearTriggerStatus).toBe("In Progress");
  });

  it("parses POLL_INTERVAL_MS as number", () => {
    setRequiredVars();
    process.env.POLL_INTERVAL_MS = "15000";

    const config = loadConfig();
    expect(typeof config.pollIntervalMs).toBe("number");
    expect(config.pollIntervalMs).toBe(15000);
  });

  it("returns a frozen object", () => {
    setRequiredVars();
    const config = loadConfig();
    expect(Object.isFrozen(config)).toBe(true);
  });
});
