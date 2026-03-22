/**
 * Stub for @anthropic-ai/claude-code SDK interface.
 * The published @anthropic-ai/claude-code package is a CLI binary with no
 * importable JS entry point. This stub provides the query() interface that
 * claudeRunner.js depends on so that:
 *   1. Jest tests can mock it via moduleNameMapper.
 *   2. The module graph resolves cleanly in test environments.
 *
 * In a real deployment this file would be replaced by the actual SDK once
 * Anthropic publishes a programmatic API package.
 */

/**
 * @param {object} opts
 * @param {string} opts.prompt
 * @param {object} [opts.options]
 * @returns {AsyncGenerator}
 */
export async function* query({ prompt, options = {} }) {
  throw new Error(
    "query() stub called — replace with real @anthropic-ai/claude-code SDK."
  );
}
