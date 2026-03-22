/**
 * Deterministic Linear status state machine for the agentic pipeline.
 * Port of src/integrations/linear/state_machine.py and mapper.py.
 */

export const PIPELINE_STATES = [
  "Backlog",
  "Ready for Dev",
  "Triage",
  "In Progress",
  "In Testing",
  "In Review",
  "Done",
];

export const BLOCKED_STATE = "Blocked";

export const VALID_TRANSITIONS = {
  "Backlog":       ["Ready for Dev", "Blocked"],
  "Ready for Dev": ["Triage", "Blocked"],
  "Triage":        ["In Progress", "Blocked"],
  "In Progress":   ["In Testing", "Blocked"],
  "In Testing":    ["In Review", "In Progress", "Blocked"],
  "In Review":     ["Done", "In Testing", "Blocked"],
  "Done":          [],
  "Blocked":       ["Triage", "In Progress"],
};

export const AUTHORIZED_ACTOR = "orchestrator";

export const PIPELINE_STATE_MAP = {
  "plan:success": "In Progress",
  "implement:success": "In Review",
  "implement:failure": "In Progress",
  "review:success": "Done",
  "review:failure": "In Progress",
  "test:failure": "In Progress",
  "test:success": "In Review",
};

export class InvalidTransitionError extends Error {
  constructor(message) {
    super(message);
    this.name = "InvalidTransitionError";
  }
}

/**
 * Validate that a transition from fromState to toState is permitted.
 * If fromState is null/undefined, skip validation.
 * @param {string|null|undefined} fromState
 * @param {string} toState
 * @throws {InvalidTransitionError}
 */
export function validateTransition(fromState, toState) {
  if (fromState == null) return;
  const allowed = VALID_TRANSITIONS[fromState] ?? [];
  if (!allowed.includes(toState)) {
    throw new InvalidTransitionError(
      `Transition '${fromState}' → '${toState}' is not permitted. Allowed from '${fromState}': ${JSON.stringify(allowed)}`
    );
  }
}

/**
 * Validate that the actor is the authorized orchestrator.
 * @param {string} actor
 * @throws {Error}
 */
export function validateActor(actor) {
  if (actor !== AUTHORIZED_ACTOR) {
    throw new Error(
      `Only '${AUTHORIZED_ACTOR}' may transition Linear states; got '${actor}'.`
    );
  }
}

/**
 * Validate that Blocked transitions include the required diagnostic payload.
 * @param {string} toState
 * @param {string|undefined} stage
 * @param {string|undefined} errorOutput
 * @throws {Error}
 */
export function validateBlockedPayload(toState, stage, errorOutput) {
  if (toState === BLOCKED_STATE) {
    if (!stage) {
      throw new Error("'stage' is required when transitioning to Blocked.");
    }
    if (!errorOutput) {
      throw new Error(
        "'errorOutput' is required when transitioning to Blocked."
      );
    }
  }
}

/**
 * Build the audit comment posted to Linear on each state change.
 * @param {string} toState
 * @param {object} opts
 * @param {string} [opts.stage]
 * @param {string} [opts.errorOutput]
 * @param {number} [opts.attemptCount=1]
 * @returns {string}
 */
export function buildTransitionComment(toState, { stage, errorOutput, attemptCount = 1 } = {}) {
  const ts = new Date().toISOString();
  let comment = `**Status → ${toState}** _(pipeline audit)_\n- Timestamp: \`${ts}\``;
  if (stage) comment += `\n- Stage: \`${stage}\``;
  if (toState === BLOCKED_STATE || attemptCount > 1) comment += `\n- Attempt: ${attemptCount}`;
  if (toState === BLOCKED_STATE && errorOutput) {
    comment += `\n\n**Diagnostic:**\n\`\`\`\n${errorOutput.trim()}\n\`\`\``;
  }
  return comment;
}

/**
 * Map a pipeline stage + status to a Linear workflow state name.
 * @param {string} stage
 * @param {string} status
 * @returns {string}
 */
export function mapPipelineStateToLinear(stage, status) {
  const key = `${stage.toLowerCase()}:${status.toLowerCase()}`;
  return PIPELINE_STATE_MAP[key] ?? "In Progress";
}
