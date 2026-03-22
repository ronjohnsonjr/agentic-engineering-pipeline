import { describe, it, expect, jest, beforeEach } from "@jest/globals";

// Mock @octokit/rest before importing GitHubService
const mockReposGet = jest.fn();

const mockOctokit = {
  repos: {
    get: mockReposGet,
  },
};

jest.unstable_mockModule("@octokit/rest", () => ({
  Octokit: jest.fn().mockImplementation(() => mockOctokit),
}));

const { GitHubService } = await import("../src/githubClient.js");

describe("GitHubService constructor", () => {
  it("parses 'owner/repo' string correctly", () => {
    const service = new GitHubService({ token: "tok", repo: "acme/my-repo" });
    expect(service._owner).toBe("acme");
    expect(service._repo).toBe("my-repo");
  });

  it("sets _owner to the part before '/' and _repo to the part after", () => {
    const service = new GitHubService({ token: "tok", repo: "org/project" });
    expect(service._owner).toBe("org");
    expect(service._repo).toBe("project");
  });

  it("throws on malformed repo string with no '/'", () => {
    expect(() => new GitHubService({ token: "tok", repo: "noslash" })).toThrow(
      'Invalid repo format: "noslash". Expected "owner/repo".'
    );
  });
});

describe("GitHubService.getRepoInfo", () => {
  let service;

  beforeEach(() => {
    jest.clearAllMocks();
    service = new GitHubService({ token: "tok", repo: "acme/my-repo" });
  });

  it("calls octokit.repos.get with correct owner and repo", async () => {
    mockReposGet.mockResolvedValue({
      data: { default_branch: "main", description: "A repo" },
    });

    await service.getRepoInfo();

    expect(mockReposGet).toHaveBeenCalledWith({
      owner: "acme",
      repo: "my-repo",
    });
  });

  it("returns defaultBranch and description from API response", async () => {
    mockReposGet.mockResolvedValue({
      data: { default_branch: "main", description: "A test repo" },
    });

    const result = await service.getRepoInfo();

    expect(result).toEqual({
      defaultBranch: "main",
      description: "A test repo",
    });
  });

  it("rejects with error when the API call fails", async () => {
    const apiError = new Error("API rate limit exceeded");
    mockReposGet.mockRejectedValue(apiError);

    await expect(service.getRepoInfo()).rejects.toThrow("API rate limit exceeded");
  });
});
