/**
 * Build identity and name. The name is a two-word label derived from the build id; the same build always gets the
 * same name.
 */
import { execSync } from 'child_process';

const adjectives = [
  'fuzzy', 'sneaky', 'wobbly', 'grumpy', 'cosmic', 'dizzy', 'spicy',
  'chunky', 'crispy', 'frosty', 'gloopy', 'jolly', 'lumpy', 'nutty',
  'peppy', 'quirky', 'rusty', 'salty', 'tangy', 'zappy', 'bouncy',
  'crunchy', 'funky', 'gusty', 'itchy', 'lanky', 'mushy', 'plucky',
  'snazzy', 'wacky', 'breezy', 'dapper', 'flashy', 'groovy', 'hasty',
  'janky', 'kooky', 'moody', 'nerdy', 'perky', 'sassy', 'turbo',
  'wonky', 'zippy', 'toasty', 'cheeky', 'sleepy', 'rowdy', 'mighty',
  'bubbly',
];

const nouns = [
  'penguin', 'waffle', 'badger', 'noodle', 'walrus', 'turnip', 'goblin',
  'muffin', 'ferret', 'pickle', 'donkey', 'biscuit', 'narwhal', 'pretzel',
  'wombat', 'taco', 'yeti', 'parrot', 'dumpling', 'otter', 'cactus',
  'nugget', 'llama', 'pancake', 'gopher', 'truffle', 'moose', 'pigeon',
  'rascal', 'sprout', 'falcon', 'crumpet', 'hamster', 'kabob', 'lemur',
  'macaron', 'pelican', 'quiche', 'raccoon', 'strudel', 'toucan',
  'unicorn', 'vulture', 'weasel', 'yak', 'alpaca', 'beetle', 'chinchilla',
  'dingo', 'echidna',
];

/**
 * The identity of a frontend build: what the bundle was built from, not which repository commit carried it.
 * deploy.sh passes LOUPE_BUILD_ID (a hash of the frontend tree, its VITE_* settings and the node version), so a
 * release that changes only the backend serves the same build, keeps every file name and shows no reload banner.
 * Outside a release it falls back to the git tree id of frontend_v2 (committed state), then to 'dev'.
 */
export function generateBuildId() {
  if (process.env.LOUPE_BUILD_ID) return process.env.LOUPE_BUILD_ID.trim();
  try {
    return execSync('git rev-parse HEAD:frontend_v2', { encoding: 'utf-8' }).trim();
  } catch {
    return 'dev';
  }
}

/** A readable two-word name for a build id (deterministic). */
export function buildDisplayName(buildId) {
  const hashNum = parseInt(buildId.substring(0, 8), 16) || 0;
  const adj = adjectives[hashNum % adjectives.length];
  const noun = nouns[Math.floor(hashNum / adjectives.length) % nouns.length];
  return `${adj.charAt(0).toUpperCase() + adj.slice(1)} ${noun.charAt(0).toUpperCase() + noun.slice(1)}`;
}
