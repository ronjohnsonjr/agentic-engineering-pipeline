import { describe, it, expect, jest, beforeEach } from "@jest/globals";

// Mock @linear/sdk before importing LinearService
const mockIssueUpdate = jest.fn();
const mockCommentCreate = jest.fn();

const mockStateNode = { id: "state-1", name: "In Progress" };
const mockTeamNode = { id: "team-1", name: "Team Alpha" };
const mockIssueData = {
  id: "issue-abc",
  identifier: "AGE-1",
  title: "Test issue",
  description: "A test issue",
  state: Promise.resolve(mockStateNode),
  team: Promise.resolve(mockTeamNode),
};

const mockStatesResult = {
  nodes: [
    { id: "state-1", name: "In Progress" },
    { id: "state-2", name: "Done" },
    { id: "state-3", name: "Blocked" },
    { id: "state-4", name: "In Testing" },
    { id: "state-5", name: "In Review" },
  ],
};

const mockTeamData = {
  states: jest.fn().mockResolvedValue(mockStatesResult),
};

const mockIssuesResult = {
  nodes: [
    { id: "issue-abc", identifier: "AGE-1", title: "Test issue", description: "desc" },
  ],
};

const mockLinearClient = {
  issue: jest.fn().mockResolvedValue(mockIssueData),
  issueUpdate: mockIssueUpdate,
  commentCreate: mockCommentCreate,
  team: jest.fn().mockResolvedValue(mockTeamData),
  issues: jest.fn().mockResolvedValue(mockIssuesResult),
};

jest.unstable_mockModule("@linear/sdk", () => ({
  LinearClient: jest.fn().mockImplementation(() => mockLinearClient),
}));

const { LinearService } = await import("../src/linearClient.js");

describe("LinearService", () => {
  let service;

  beforeEach(() => {
    jest.clearAllMocks();
    mockTeamData.states.mockResolvedValue(mockStatesResult);
    mockLinearClient.issue.mockResolvedValue(mockIssueData);
    mockLinearClient.issues.mockResolvedValue(mockIssuesResult);
    mockLinearClient.team.mockResolvedValue(mockTeamData);
    service = new LinearService({ apiKey: "test-key" });
  });

  describe("getIssue", () => {
    it("returns normalized issue shape", async () => {
      const result = await service.getIssue("issue-abc");
      expect(result).toEqual({
        id: "issue-abc",
        identifier: "AGE-1",
        title: "Test issue",
        description: "A test issue",
        state: { id: "state-1", name: "In Progress" },
        team: { id: "team-1", name: "Team Alpha" },
      });
    });
  });

  describe("updateIssueState", () => {
    it("calls issueUpdate with correct params", async () => {
      mockIssueUpdate.mockResolvedValue({});
      await service.updateIssueState("issue-abc", "state-2");
      expect(mockIssueUpdate).toHaveBeenCalledWith("issue-abc", { stateId: "state-2" });
    });
  });

  describe("addComment", () => {
    it("calls commentCreate with correct params", async () => {
      mockCommentCreate.mockResolvedValue({});
      await service.addComment("issue-abc", "Hello world");
      expect(mockCommentCreate).toHaveBeenCalledWith({
        issueId: "issue-abc",
        body: "Hello world",
      });
    });
  });

  describe("getTeamStates", () => {
    it("returns array of id/name pairs", async () => {
      const states = await service.getTeamStates("team-1");
      expect(states).toEqual([
        { id: "state-1", name: "In Progress" },
        { id: "state-2", name: "Done" },
        { id: "state-3", name: "Blocked" },
        { id: "state-4", name: "In Testing" },
        { id: "state-5", name: "In Review" },
      ]);
    });
  });

  describe("listIssuesByState", () => {
    it("returns normalized issue list", async () => {
      const issues = await service.listIssuesByState("team-1", "In Progress");
      expect(issues).toEqual([
        { id: "issue-abc", identifier: "AGE-1", title: "Test issue", description: "desc" },
      ]);
      expect(mockLinearClient.issues).toHaveBeenCalledWith({
        filter: {
          team: { id: { eq: "team-1" } },
          state: { name: { eq: "In Progress" } },
        },
      });
    });
  });

  describe("resolveStateId", () => {
    it("returns the id for a matching state name", async () => {
      const id = await service.resolveStateId("team-1", "Done");
      expect(id).toBe("state-2");
    });

    it("is case-insensitive", async () => {
      const id = await service.resolveStateId("team-1", "done");
      expect(id).toBe("state-2");
    });

    it("throws when state not found, listing available", async () => {
      await expect(service.resolveStateId("team-1", "NonExistent")).rejects.toThrow(
        /NonExistent/
      );
    });
  });

  describe("transitionIssue", () => {
    it("validates actor and rejects non-orchestrator", async () => {
      await expect(
        service.transitionIssue("issue-abc", "team-1", "Done", {
          stage: "review",
          actor: "human",
        })
      ).rejects.toThrow(/orchestrator/);
    });

    it("validates transition and rejects invalid moves", async () => {
      // In Progress -> Backlog is not valid
      const issueInProgress = {
        ...mockIssueData,
        state: Promise.resolve({ id: "state-1", name: "In Progress" }),
        team: Promise.resolve(mockTeamNode),
      };
      mockLinearClient.issue.mockResolvedValue(issueInProgress);

      await expect(
        service.transitionIssue("issue-abc", "team-1", "Backlog", {
          stage: "plan",
          actor: "orchestrator",
        })
      ).rejects.toThrow(/not permitted/);
    });

    it("calls updateIssueState and addComment on valid transition", async () => {
      mockIssueUpdate.mockResolvedValue({});
      mockCommentCreate.mockResolvedValue({});

      await service.transitionIssue("issue-abc", "team-1", "In Testing", {
        stage: "implement",
        actor: "orchestrator",
        attemptCount: 1,
      });

      expect(mockIssueUpdate).toHaveBeenCalledWith("issue-abc", { stateId: "state-4" });
      expect(mockCommentCreate).toHaveBeenCalled();
    });

    it("requires stage and errorOutput for Blocked transitions", async () => {
      await expect(
        service.transitionIssue("issue-abc", "team-1", "Blocked", {
          actor: "orchestrator",
          stage: "implement",
          // no errorOutput
        })
      ).rejects.toThrow(/errorOutput/);
    });
  });
});
