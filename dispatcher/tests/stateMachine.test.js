import { describe, it, expect } from "@jest/globals";
import {
  PIPELINE_STATES,
  BLOCKED_STATE,
  VALID_TRANSITIONS,
  AUTHORIZED_ACTOR,
  PIPELINE_STATE_MAP,
  InvalidTransitionError,
  validateTransition,
  validateActor,
  validateBlockedPayload,
  buildTransitionComment,
  mapPipelineStateToLinear,
} from "../src/stateMachine.js";

describe("PIPELINE_STATES", () => {
  it("has the correct order", () => {
    expect(PIPELINE_STATES).toEqual([
      "Backlog",
      "Ready for Dev",
      "Triage",
      "In Progress",
      "In Testing",
      "In Review",
      "Done",
    ]);
  });
});

describe("BLOCKED_STATE", () => {
  it("equals Blocked", () => {
    expect(BLOCKED_STATE).toBe("Blocked");
  });
});

describe("VALID_TRANSITIONS", () => {
  it("covers all pipeline states and Blocked", () => {
    const expected = [...PIPELINE_STATES, BLOCKED_STATE];
    for (const state of expected) {
      expect(VALID_TRANSITIONS).toHaveProperty(state);
    }
  });

  it("Done has no transitions", () => {
    expect(VALID_TRANSITIONS["Done"]).toEqual([]);
  });

  it("Blocked can transition to Triage and In Progress", () => {
    expect(VALID_TRANSITIONS["Blocked"]).toContain("Triage");
    expect(VALID_TRANSITIONS["Blocked"]).toContain("In Progress");
  });

  it("In Progress can move to In Testing and Blocked only", () => {
    const allowed = VALID_TRANSITIONS["In Progress"];
    expect(allowed).toContain("In Testing");
    expect(allowed).toContain("Blocked");
    expect(allowed).not.toContain("In Review");
    expect(allowed).not.toContain("Done");
  });
});

describe("validateActor", () => {
  it("allows orchestrator", () => {
    expect(() => validateActor("orchestrator")).not.toThrow();
  });

  it("rejects non-orchestrator actors", () => {
    expect(() => validateActor("human")).toThrow(/orchestrator/);
    expect(() => validateActor("bot")).toThrow(/orchestrator/);
    expect(() => validateActor("")).toThrow(/orchestrator/);
  });
});

describe("validateTransition", () => {
  it("allows valid transitions", () => {
    expect(() => validateTransition("In Progress", "In Testing")).not.toThrow();
    expect(() => validateTransition("In Testing", "In Review")).not.toThrow();
    expect(() => validateTransition("Blocked", "In Progress")).not.toThrow();
  });

  it("rejects invalid transitions", () => {
    expect(() => validateTransition("Done", "In Progress")).toThrow(
      InvalidTransitionError
    );
    expect(() => validateTransition("In Progress", "Backlog")).toThrow(
      InvalidTransitionError
    );
  });

  it("skips validation when fromState is null", () => {
    expect(() => validateTransition(null, "In Progress")).not.toThrow();
  });

  it("skips validation when fromState is undefined", () => {
    expect(() => validateTransition(undefined, "In Progress")).not.toThrow();
  });
});

describe("validateBlockedPayload", () => {
  it("passes for non-Blocked transitions without stage/errorOutput", () => {
    expect(() => validateBlockedPayload("In Progress", undefined, undefined)).not.toThrow();
  });

  it("throws if transitioning to Blocked without stage", () => {
    expect(() => validateBlockedPayload("Blocked", undefined, "some error")).toThrow(
      /stage/
    );
  });

  it("throws if transitioning to Blocked without errorOutput", () => {
    expect(() => validateBlockedPayload("Blocked", "implement", undefined)).toThrow(
      /errorOutput/
    );
  });

  it("passes for Blocked with both stage and errorOutput", () => {
    expect(() =>
      validateBlockedPayload("Blocked", "implement", "stack trace here")
    ).not.toThrow();
  });
});

describe("buildTransitionComment", () => {
  it("includes state, timestamp, and stage; omits attempt for non-Blocked attemptCount=1", () => {
    const comment = buildTransitionComment("In Progress", {
      stage: "plan",
      attemptCount: 1,
    });
    expect(comment).toContain("**Status → In Progress**");
    expect(comment).toContain("_(pipeline audit)_");
    expect(comment).toContain("- Stage: `plan`");
    expect(comment).not.toContain("- Attempt:");
    expect(comment).toMatch(/Timestamp:/);
  });

  it("includes attempt when attemptCount > 1 for non-Blocked transitions", () => {
    const comment = buildTransitionComment("In Testing", { stage: "test", attemptCount: 2 });
    expect(comment).toContain("- Attempt: 2");
  });

  it("omits stage when stage is falsy", () => {
    const comment = buildTransitionComment("In Progress", { attemptCount: 1 });
    expect(comment).not.toContain("- Stage:");
  });

  it("includes attempt for Blocked even when attemptCount=1", () => {
    const comment = buildTransitionComment("Blocked", {
      stage: "implement",
      errorOutput: "some error",
      attemptCount: 1,
    });
    expect(comment).toContain("- Attempt: 1");
  });

  it("includes diagnostic block for Blocked transitions", () => {
    const comment = buildTransitionComment("Blocked", {
      stage: "implement",
      errorOutput: "  error details  ",
      attemptCount: 2,
    });
    expect(comment).toContain("**Diagnostic:**");
    expect(comment).toContain("error details");
    expect(comment).toContain("```");
  });

  it("does not include diagnostic block for non-Blocked transitions", () => {
    const comment = buildTransitionComment("In Progress", {
      stage: "plan",
      errorOutput: "should not appear",
    });
    expect(comment).not.toContain("**Diagnostic:**");
    expect(comment).not.toContain("should not appear");
  });
});

describe("mapPipelineStateToLinear", () => {
  it("maps plan:success to In Progress", () => {
    expect(mapPipelineStateToLinear("plan", "success")).toBe("In Progress");
  });

  it("maps implement:success to In Review", () => {
    expect(mapPipelineStateToLinear("implement", "success")).toBe("In Review");
  });

  it("maps implement:failure to In Progress", () => {
    expect(mapPipelineStateToLinear("implement", "failure")).toBe("In Progress");
  });

  it("maps review:success to Done", () => {
    expect(mapPipelineStateToLinear("review", "success")).toBe("Done");
  });

  it("maps review:failure to In Progress", () => {
    expect(mapPipelineStateToLinear("review", "failure")).toBe("In Progress");
  });

  it("maps test:failure to In Progress", () => {
    expect(mapPipelineStateToLinear("test", "failure")).toBe("In Progress");
  });

  it("maps test:success to In Review", () => {
    expect(mapPipelineStateToLinear("test", "success")).toBe("In Review");
  });

  it("defaults to In Progress for unknown stage/status", () => {
    expect(mapPipelineStateToLinear("unknown", "blah")).toBe("In Progress");
  });

  it("is case-insensitive", () => {
    expect(mapPipelineStateToLinear("IMPLEMENT", "SUCCESS")).toBe("In Review");
    expect(mapPipelineStateToLinear("Review", "Failure")).toBe("In Progress");
  });
});
