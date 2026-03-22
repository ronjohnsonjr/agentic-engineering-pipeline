/**
 * Agentic dispatcher entrypoint.
 * Polls Linear for issues in the trigger state and dispatches Claude sessions.
 */

import { loadConfig } from "./config.js";
import { LinearService } from "./linearClient.js";
import { GitHubService } from "./githubClient.js";
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
const githubService = new GitHubService({ token: config.githubToken, repo: config.githubRepo });
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

async function poll() {
  const issues = await linearService.listIssuesByState(
    config.linearTeamId,
    config.linearTriggerStatus
  );
  for (const issue of issues) sessionManager.enqueue(issue);
  console.log(
    `Poll complete: ${issues.length} issues found, ${sessionManager.activeCount} active, ${sessionManager.queueLength} queued`
  );
}

const intervalId = setInterval(poll, config.pollIntervalMs);
poll();

console.log(
  `Dispatcher started — team: ${config.linearTeamId}, trigger: "${config.linearTriggerStatus}", interval: ${config.pollIntervalMs}ms, max: ${config.maxConcurrentSessions}`
);

process.on("SIGINT", () => {
  clearInterval(intervalId);
  console.log("Shutting down");
  process.exit(0);
});
process.on("SIGTERM", () => {
  clearInterval(intervalId);
  console.log("Shutting down");
  process.exit(0);
});

export { poll };
