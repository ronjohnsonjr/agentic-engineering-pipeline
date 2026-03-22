/**
 * Claude session runner using @anthropic-ai/claude-code.
 */

import { query } from "./vendor/claude-code-stub.js";

export class ClaudeRunner {
  /**
   * @param {object} opts
   * @param {string} opts.anthropicApiKey
   * @param {string} opts.githubToken
   * @param {string} opts.githubRepo
   */
  constructor({ anthropicApiKey, githubToken, githubRepo }) {
    this._anthropicApiKey = anthropicApiKey;
    this._githubToken = githubToken;
    this._githubRepo = githubRepo;
  }

  /**
   * Run a full Claude session for the given Linear issue.
   * @param {object} issue
   * @returns {Promise<{success: boolean, output: string, stageEvents: Array<{stage: string, status: string}>}>}
   */
  async runSession(issue) {
    const prompt = `You are an agentic engineering pipeline orchestrator. Work on the following Linear issue end-to-end.

## Issue
**ID**: ${issue.identifier}
**Title**: ${issue.title}
**Description**: ${issue.description || "No description provided."}

## Instructions
Work through the issue completely. At each pipeline stage transition, emit a marker on its own line:
STAGE:<stage>:<status>
Where stage is one of: clarify, research, plan, implement, test, review
And status is: success or failure`;

    try {
      const messages = query({ prompt, options: {} });
      let fullOutput = "";

      for await (const message of messages) {
        if (message?.type === "result" && message?.result) {
          fullOutput += message.result;
        } else if (typeof message === "string") {
          fullOutput += message;
        }
      }

      const stageEvents = [];
      let match;
      const re = /^STAGE:(\w+):(success|failure)$/gm;
      while ((match = re.exec(fullOutput)) !== null) {
        stageEvents.push({ stage: match[1], status: match[2] });
      }

      return { success: true, output: fullOutput, stageEvents };
    } catch (err) {
      return { success: false, output: err.message, stageEvents: [] };
    }
  }
}
