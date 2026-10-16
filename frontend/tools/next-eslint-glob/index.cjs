// Next loads this package synchronously with require().
// eslint-disable-next-line @typescript-eslint/no-require-imports
const tinyglobby = require("tinyglobby");

// Next's get-root-dirs calls globSync(pattern, { onlyDirectories: true }).
// Fast-glob returns a literal directory itself; tinyglobby otherwise includes
// its descendants. Preserve that behavior for literal paths and brace lists.
exports.globSync = (patterns, options) =>
  tinyglobby.globSync(patterns, { ...options, expandDirectories: false });
