import { describe, it, expect, jest, beforeEach } from "@jest/globals";
import { SessionManager } from "../src/sessionManager.js";

function makeLinearService(overrides = {}) {
  return {
    transitionIssue: jest.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

function makeClaudeRunner(result = { success: true, output: "done", stageEvents: [] }) {
  return {
    runSession: jest.fn().mockResolvedValue(result),
  };
}

function makeIssue(id = "issue-1") {
  return { id, identifier: `AGE-${id}`, title: `Issue ${id}`, description: "desc" };
}

describe("SessionManager", () => {
  let linearService;
  let claudeRunner;
  let manager;

  beforeEach(() => {
    linearService = makeLinearService();
    claudeRunner = makeClaudeRunner();
    manager = new SessionManager({
      maxConcurrent: 2,
      linearService,
      claudeRunner,
      teamId: "team-1",
    });
  });

  describe("enqueue under cap", () => {
    it("starts session immediately when under concurrency cap", () => {
      const issue = makeIssue("1");
      manager.enqueue(issue);
      expect(manager.activeCount).toBe(1);
      expect(manager.queueLength).toBe(0);
    });
  });

  describe("enqueue at cap", () => {
    it("queues issue when at concurrency cap", () => {
      // Fill up with slow sessions
      claudeRunner.runSession.mockImplementation(
        () => new Promise(() => {}) // never resolves
      );

      manager.enqueue(makeIssue("1"));
      manager.enqueue(makeIssue("2"));
      manager.enqueue(makeIssue("3")); // should queue

      expect(manager.activeCount).toBe(2);
      expect(manager.queueLength).toBe(1);
    });
  });

  describe("deduplication", () => {
    it("does not enqueue the same issue twice", () => {
      claudeRunner.runSession.mockImplementation(() => new Promise(() => {}));

      const issue = makeIssue("1");
      manager.enqueue(issue);
      manager.enqueue(issue); // duplicate
      manager.enqueue(issue); // duplicate

      expect(manager.activeCount).toBe(1);
      expect(manager.queueLength).toBe(0);
    });
  });

  describe("queue draining", () => {
    it("drains queue when a session completes", async () => {
      let resolveFirst;
      const firstDone = new Promise((res) => { resolveFirst = res; });

      claudeRunner.runSession
        .mockImplementationOnce(() => firstDone.then(() => ({ success: true, output: "", stageEvents: [] })))
        .mockResolvedValue({ success: true, output: "", stageEvents: [] });

      manager.enqueue(makeIssue("1")); // active
      manager.enqueue(makeIssue("2")); // active (cap is 2)
      manager.enqueue(makeIssue("3")); // queued

      expect(manager.activeCount).toBe(2);
      expect(manager.queueLength).toBe(1);

      resolveFirst();
      // Wait for the promise chain to process
      await new Promise((r) => setTimeout(r, 10));

      // After issue-1 completes, issue-3 should start
      expect(manager.queueLength).toBe(0);
    });
  });

  describe("Blocked on failure", () => {
    it("transitions to Blocked when runSession fails", async () => {
      claudeRunner.runSession.mockResolvedValue({
        success: false,
        output: "Fatal error occurred",
        stageEvents: [],
      });

      manager.enqueue(makeIssue("1"));
      // Wait for async processing
      await new Promise((r) => setTimeout(r, 10));

      const calls = linearService.transitionIssue.mock.calls;
      const blockedCall = calls.find((c) => c[2] === "Blocked");
      expect(blockedCall).toBeTruthy();
      expect(blockedCall[3].errorOutput).toBe("Fatal error occurred");
      expect(blockedCall[3].stage).toBe("implement");
    });
  });

  describe("stage event processing", () => {
    it("transitions to states mapped from stageEvents", async () => {
      claudeRunner.runSession.mockResolvedValue({
        success: true,
        output: "done",
        stageEvents: [
          { stage: "implement", status: "success" }, // -> In Review
          { stage: "review", status: "success" },    // -> Done
        ],
      });

      manager.enqueue(makeIssue("1"));
      await new Promise((r) => setTimeout(r, 10));

      const calls = linearService.transitionIssue.mock.calls;
      const states = calls.map((c) => c[2]);
      expect(states).toContain("In Review");
      expect(states).toContain("Done");
    });

    it("transitions to Done when success with no stageEvents", async () => {
      claudeRunner.runSession.mockResolvedValue({
        success: true,
        output: "done",
        stageEvents: [],
      });

      manager.enqueue(makeIssue("1"));
      await new Promise((r) => setTimeout(r, 10));

      const calls = linearService.transitionIssue.mock.calls;
      const states = calls.map((c) => c[2]);
      expect(states).toContain("Done");
    });
  });

  describe("activeCount and queueLength", () => {
    it("reports correct counts", () => {
      claudeRunner.runSession.mockImplementation(() => new Promise(() => {}));

      expect(manager.activeCount).toBe(0);
      expect(manager.queueLength).toBe(0);

      manager.enqueue(makeIssue("1"));
      expect(manager.activeCount).toBe(1);

      manager.enqueue(makeIssue("2"));
      expect(manager.activeCount).toBe(2);

      manager.enqueue(makeIssue("3"));
      expect(manager.queueLength).toBe(1);
    });
  });
});
