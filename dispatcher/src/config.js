/**
 * Configuration loader for the agentic dispatcher.
 * This is the ONLY file that reads process.env.
 */

const REQUIRED_VARS = [
  "ANTHROPIC_API_KEY",
  "LINEAR_API_KEY",
  "LINEAR_TEAM_ID",
  "GITHUB_TOKEN",
  "GITHUB_REPO",
];

/**
 * Load and validate configuration from environment variables.
 * @returns {Readonly<object>} Frozen configuration object.
 * @throws {Error} If any required environment variable is missing.
 */
export function loadConfig() {
  const missing = REQUIRED_VARS.filter((v) => !process.env[v]);
  if (missing.length > 0) {
    throw new Error(
      `Missing required environment variables: ${missing.join(", ")}`
    );
  }

  const pollIntervalRaw = process.env.POLL_INTERVAL_MS;
  const pollIntervalMs =
    pollIntervalRaw == null || pollIntervalRaw === ""
      ? 30000
      : Number(pollIntervalRaw);
  if (!Number.isFinite(pollIntervalMs) || !Number.isInteger(pollIntervalMs) || pollIntervalMs <= 0) {
    throw new Error(
      `Invalid POLL_INTERVAL_MS value: "${pollIntervalRaw}". Must be a positive integer (milliseconds).`
    );
  }

  const maxConcurrentRaw = process.env.MAX_CONCURRENT_SESSIONS;
  const maxConcurrentSessions =
    maxConcurrentRaw == null || maxConcurrentRaw === ""
      ? 3
      : Number(maxConcurrentRaw);
  if (!Number.isFinite(maxConcurrentSessions) || !Number.isInteger(maxConcurrentSessions) || maxConcurrentSessions <= 0) {
    throw new Error(
      `Invalid MAX_CONCURRENT_SESSIONS value: "${maxConcurrentRaw}". Must be a positive integer.`
    );
  }

  return Object.freeze({
    anthropicApiKey: process.env.ANTHROPIC_API_KEY,
    linearApiKey: process.env.LINEAR_API_KEY,
    linearTeamId: process.env.LINEAR_TEAM_ID,
    githubToken: process.env.GITHUB_TOKEN,
    githubRepo: process.env.GITHUB_REPO,
    pollIntervalMs,
    maxConcurrentSessions,
    linearTriggerStatus: process.env.LINEAR_TRIGGER_STATUS ?? "In Progress",
  });
}
