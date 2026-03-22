/**
 * Linear API service wrapper using @linear/sdk.
 */

import { LinearClient } from "@linear/sdk";
import {
  validateActor,
  validateTransition,
  validateBlockedPayload,
  buildTransitionComment,
} from "./stateMachine.js";

export class LinearService {
  /**
   * @param {object} opts
   * @param {string} opts.apiKey
   */
  constructor({ apiKey }) {
    this._client = new LinearClient({ apiKey });
  }

  /**
   * Fetch a single issue by ID, including its state and team.
   * @param {string} issueId
   * @returns {Promise<object>}
   */
  async getIssue(issueId) {
    const issue = await this._client.issue(issueId);
    const state = await issue.state;
    const team = await issue.team;
    return {
      id: issue.id,
      identifier: issue.identifier,
      title: issue.title,
      description: issue.description,
      state: { id: state.id, name: state.name },
      team: { id: team.id, name: team.name },
    };
  }

  /**
   * Update the state of an issue.
   * @param {string} issueId
   * @param {string} stateId
   */
  async updateIssueState(issueId, stateId) {
    await this._client.issueUpdate(issueId, { stateId });
  }

  /**
   * Add a comment to an issue.
   * @param {string} issueId
   * @param {string} body
   */
  async addComment(issueId, body) {
    await this._client.commentCreate({ issueId, body });
  }

  /**
   * Get all workflow states for a team.
   * @param {string} teamId
   * @returns {Promise<Array<{id: string, name: string}>>}
   */
  async getTeamStates(teamId) {
    const team = await this._client.team(teamId);
    const states = await team.states();
    return states.nodes.map((s) => ({ id: s.id, name: s.name }));
  }

  /**
   * List issues for a team filtered by state name.
   * @param {string} teamId
   * @param {string} stateName
   * @returns {Promise<Array<object>>}
   */
  async listIssuesByState(teamId, stateName) {
    const result = await this._client.issues({
      filter: {
        team: { id: { eq: teamId } },
        state: { name: { eq: stateName } },
      },
    });
    return result.nodes.map((issue) => ({
      id: issue.id,
      identifier: issue.identifier,
      title: issue.title,
      description: issue.description,
    }));
  }

  /**
   * Resolve a state name to a Linear state ID for a given team.
   * @param {string} teamId
   * @param {string} stateName
   * @returns {Promise<string>} state ID
   * @throws {Error} if state name not found
   */
  async resolveStateId(teamId, stateName) {
    const states = await this.getTeamStates(teamId);
    const match = states.find(
      (s) => s.name.toLowerCase() === stateName.toLowerCase()
    );
    if (!match) {
      const available = states.map((s) => s.name);
      throw new Error(
        `State '${stateName}' not found in team states. Available: ${JSON.stringify(available)}`
      );
    }
    return match.id;
  }

  /**
   * Transition an issue to a new state with validation and audit comment.
   * @param {string} issueId
   * @param {string} teamId
   * @param {string} toState
   * @param {object} opts
   * @param {string} [opts.stage]
   * @param {string} [opts.errorOutput]
   * @param {number} [opts.attemptCount=1]
   * @param {string} opts.actor
   */
  async transitionIssue(issueId, teamId, toState, { stage, errorOutput, attemptCount = 1, actor }) {
    validateActor(actor);
    const issue = await this.getIssue(issueId);
    const fromState = issue.state?.name;
    validateTransition(fromState, toState);
    validateBlockedPayload(toState, stage, errorOutput);
    const stateId = await this.resolveStateId(teamId, toState);
    await this.updateIssueState(issueId, stateId);
    const comment = buildTransitionComment(toState, { stage, errorOutput, attemptCount });
    await this.addComment(issueId, comment);
  }
}
