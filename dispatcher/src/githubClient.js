/**
 * GitHub API service wrapper using @octokit/rest.
 */

import { Octokit } from "@octokit/rest";

export class GitHubService {
  /**
   * @param {object} opts
   * @param {string} opts.token - GitHub personal access token
   * @param {string} opts.repo - "owner/repo" format
   */
  constructor({ token, repo }) {
    const parts = repo.split("/");
    if (parts.length !== 2 || !parts[0] || !parts[1]) {
      throw new Error(`Invalid repo format: "${repo}". Expected "owner/repo".`);
    }
    this._owner = parts[0];
    this._repo = parts[1];
    this._octokit = new Octokit({ auth: token });
  }

  /**
   * Get basic repository information.
   * @returns {Promise<{defaultBranch: string, description: string}>}
   */
  async getRepoInfo() {
    const { data } = await this._octokit.repos.get({
      owner: this._owner,
      repo: this._repo,
    });
    return {
      defaultBranch: data.default_branch,
      description: data.description,
    };
  }
}
