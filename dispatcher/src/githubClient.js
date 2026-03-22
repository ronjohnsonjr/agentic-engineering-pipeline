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
    const [owner, repoName] = repo.split("/");
    this._owner = owner;
    this._repo = repoName;
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
