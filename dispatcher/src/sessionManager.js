/**
 * Session manager — limits concurrent Claude sessions and serialises the queue.
 */

import { mapPipelineStateToLinear } from "./stateMachine.js";

export class SessionManager {
  /**
   * @param {object} opts
   * @param {number} opts.maxConcurrent
   * @param {object} opts.linearService
   * @param {object} opts.claudeRunner
   * @param {string} opts.teamId
   */
  constructor({ maxConcurrent, linearService, claudeRunner, teamId }) {
    this._maxConcurrent = maxConcurrent;
    this._linearService = linearService;
    this._claudeRunner = claudeRunner;
    this._teamId = teamId;
    this._active = new Map();
    this._queue = [];
    this._seen = new Set();
  }

  /**
   * Enqueue an issue for processing. Deduplicates by issue ID.
   * @param {object} issue
   */
  enqueue(issue) {
    if (this._seen.has(issue.id)) return;
    this._seen.add(issue.id);
    if (this._active.size < this._maxConcurrent) {
      this._startSession(issue);
    } else {
      this._queue.push(issue);
    }
  }

  /**
   * Start a Claude session for the given issue.
   * @param {object} issue
   */
  _startSession(issue) {
    const promise = (async () => {
      try {
        await this._linearService.transitionIssue(
          issue.id,
          this._teamId,
          "In Progress",
          { stage: "start", actor: "orchestrator", attemptCount: 1 }
        );
      } catch (err) {
        console.log(
          `[SessionManager] Could not transition ${issue.id} to In Progress (may already be there): ${err.message}`
        );
      }

      const result = await this._claudeRunner.runSession(issue);

      for (const stageEvent of result.stageEvents) {
        const targetState = mapPipelineStateToLinear(stageEvent.stage, stageEvent.status);
        try {
          await this._linearService.transitionIssue(
            issue.id,
            this._teamId,
            targetState,
            { stage: stageEvent.stage, actor: "orchestrator", attemptCount: 1 }
          );
        } catch (err) {
          console.error(
            `[SessionManager] Failed to transition ${issue.id} to ${targetState}: ${err.message}`
          );
        }
      }

      if (result.success && result.stageEvents.length === 0) {
        try {
          await this._linearService.transitionIssue(
            issue.id,
            this._teamId,
            "Done",
            { stage: "complete", actor: "orchestrator", attemptCount: 1 }
          );
        } catch (err) {
          console.error(
            `[SessionManager] Failed to transition ${issue.id} to Done: ${err.message}`
          );
        }
      }

      if (!result.success) {
        try {
          await this._linearService.transitionIssue(
            issue.id,
            this._teamId,
            "Blocked",
            {
              stage: "implement",
              errorOutput: result.output,
              actor: "orchestrator",
              attemptCount: 1,
            }
          );
        } catch (err) {
          console.error(
            `[SessionManager] Failed to transition ${issue.id} to Blocked: ${err.message}`
          );
        }
      }
    })();

    promise.finally(() => {
      this._active.delete(issue.id);
      this._seen.delete(issue.id);
      this._drainQueue();
    });

    this._active.set(issue.id, promise);
  }

  /**
   * Drain the queue, starting sessions up to the concurrency limit.
   */
  _drainQueue() {
    while (this._active.size < this._maxConcurrent && this._queue.length > 0) {
      const next = this._queue.shift();
      this._startSession(next);
    }
  }

  /** @returns {number} */
  get activeCount() {
    return this._active.size;
  }

  /** @returns {number} */
  get queueLength() {
    return this._queue.length;
  }
}
