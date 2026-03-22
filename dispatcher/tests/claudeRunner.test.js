import { describe, it, expect, jest, beforeEach } from "@jest/globals";

// Mock @anthropic-ai/claude-code before importing ClaudeRunner
async function* makeAsyncGen(messages) {
  for (const msg of messages) {
    yield msg;
  }
}

const mockQuery = jest.fn();

jest.unstable_mockModule("../src/vendor/claude-code-stub.js", () => ({
  query: mockQuery,
}));

const { ClaudeRunner } = await import("../src/claudeRunner.js");

describe("ClaudeRunner", () => {
  let runner;

  beforeEach(() => {
    jest.clearAllMocks();
    runner = new ClaudeRunner({
      anthropicApiKey: "test-api-key",
      githubToken: "gh-token",
      githubRepo: "owner/repo",
    });
  });

  const testIssue = {
    id: "issue-1",
    identifier: "AGE-42",
    title: "Fix the thing",
    description: "The thing needs fixing.",
  };

  describe("runSession success", () => {
    it("returns success with output when query resolves", async () => {
      mockQuery.mockReturnValue(
        makeAsyncGen([{ type: "result", result: "I completed the task.\nSTAGE:implement:success\n" }])
      );

      const result = await runner.runSession(testIssue);
      expect(result.success).toBe(true);
      expect(result.output).toContain("I completed the task.");
      expect(result.stageEvents).toHaveLength(1);
      expect(result.stageEvents[0]).toEqual({ stage: "implement", status: "success" });
    });

    it("extracts multiple stage events", async () => {
      const output = "Working...\nSTAGE:plan:success\nDoing more...\nSTAGE:implement:success\nReviewing...\nSTAGE:review:success\n";
      mockQuery.mockReturnValue(makeAsyncGen([{ type: "result", result: output }]));

      const result = await runner.runSession(testIssue);
      expect(result.success).toBe(true);
      expect(result.stageEvents).toHaveLength(3);
      expect(result.stageEvents[0]).toEqual({ stage: "plan", status: "success" });
      expect(result.stageEvents[1]).toEqual({ stage: "implement", status: "success" });
      expect(result.stageEvents[2]).toEqual({ stage: "review", status: "success" });
    });

    it("returns empty stageEvents when no markers present", async () => {
      mockQuery.mockReturnValue(makeAsyncGen([{ type: "result", result: "Done, no markers." }]));

      const result = await runner.runSession(testIssue);
      expect(result.success).toBe(true);
      expect(result.stageEvents).toHaveLength(0);
    });
  });

  describe("runSession failure", () => {
    it("returns failure with error message when query throws", async () => {
      mockQuery.mockImplementation(() => {
        throw new Error("API rate limit exceeded");
      });

      const result = await runner.runSession(testIssue);
      expect(result.success).toBe(false);
      expect(result.output).toBe("API rate limit exceeded");
      expect(result.stageEvents).toHaveLength(0);
    });

    it("handles async generator that throws", async () => {
      async function* throwingGen() {
        yield { type: "result", result: "partial" };
        throw new Error("network error");
      }
      mockQuery.mockReturnValue(throwingGen());

      const result = await runner.runSession(testIssue);
      expect(result.success).toBe(false);
      expect(result.output).toContain("network error");
    });
  });

  describe("stage event extraction", () => {
    it("extracts failure events", async () => {
      mockQuery.mockReturnValue(
        makeAsyncGen([{ type: "result", result: "STAGE:test:failure\n" }])
      );

      const result = await runner.runSession(testIssue);
      expect(result.stageEvents[0]).toEqual({ stage: "test", status: "failure" });
    });

    it("ignores malformed STAGE markers", async () => {
      mockQuery.mockReturnValue(
        makeAsyncGen([{ type: "result", result: "STAGE:invalid\nSTAGE::success\nSTAGE:plan:success\n" }])
      );

      const result = await runner.runSession(testIssue);
      expect(result.stageEvents).toHaveLength(1);
      expect(result.stageEvents[0]).toEqual({ stage: "plan", status: "success" });
    });
  });
});
