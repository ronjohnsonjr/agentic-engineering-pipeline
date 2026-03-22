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

  return Object.freeze({
    anthropicApiKey: process.env.ANTHROPIC_API_KEY,
    linearApiKey: process.env.LINEAR_API_KEY,
    linearTeamId: process.env.LINEAR_TEAM_ID,
    githubToken: process.env.GITHUB_TOKEN,
    githubRepo: process.env.GITHUB_REPO,
    pollIntervalMs: Number(process.env.POLL_INTERVAL_MS ?? 30000),
    maxConcurrentSessions: Number(process.env.MAX_CONCURRENT_SESSIONS ?? 3),
    linearTriggerStatus: process.env.LINEAR_TRIGGER_STATUS ?? "In Progress",
  });
}
