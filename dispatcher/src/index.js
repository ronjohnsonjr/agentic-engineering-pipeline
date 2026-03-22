/**
 * Agentic dispatcher entrypoint.
 * Polls Linear for issues in the trigger state and dispatches Claude sessions.
 */

import { loadConfig } from "./config.js";
import { LinearService } from "./linearClient.js";
import { ClaudeRunner } from "./claudeRunner.js";
import { SessionManager } from "./sessionManager.js";

const config = (() => {
  try {
    return loadConfig();
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
})();

const linearService = new LinearService({ apiKey: config.linearApiKey });
const claudeRunner = new ClaudeRunner({
  anthropicApiKey: config.anthropicApiKey,
  githubToken: config.githubToken,
  githubRepo: config.githubRepo,
});
const sessionManager = new SessionManager({
  maxConcurrent: config.maxConcurrentSessions,
  linearService,
  claudeRunner,
  teamId: config.linearTeamId,
});

let isPolling = false;

async function poll() {
  if (isPolling) {
    console.warn("Previous poll still in progress, skipping this interval tick");
    return;
  }
  isPolling = true;
  try {
    const issues = await linearService.listIssuesByState(
      config.linearTeamId,
      config.linearTriggerStatus
    );
    for (const issue of issues) sessionManager.enqueue(issue);
    console.log(
      `Poll complete: ${issues.length} issues found, ${sessionManager.activeCount} active, ${sessionManager.queueLength} queued`
    );
  } catch (err) {
    console.error("[poll] Error fetching issues:", err.message);
  } finally {
    isPolling = false;
  }
}

const intervalId = setInterval(poll, config.pollIntervalMs);

console.log(
  `Dispatcher started — team: ${config.linearTeamId}, trigger: "${config.linearTriggerStatus}", interval: ${config.pollIntervalMs}ms, max: ${config.maxConcurrentSessions}`
);

poll();

let shuttingDown = false;

async function gracefulShutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  clearInterval(intervalId);
  console.log(`Received ${signal}. Waiting for active sessions to complete...`);
  const deadline = Date.now() + 15000;
  while (sessionManager.activeCount > 0 && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  if (sessionManager.activeCount > 0) {
    console.warn(`Timeout: ${sessionManager.activeCount} sessions still active. Exiting.`);
  } else {
    console.log("All sessions completed. Exiting.");
  }
  process.exit(0);
}

process.on("SIGINT", () => { void gracefulShutdown("SIGINT"); });
process.on("SIGTERM", () => { void gracefulShutdown("SIGTERM"); });

export { poll };
