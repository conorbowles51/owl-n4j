/**
 * Build Name Generator
 *
 * Generates a unique, funny two-word name for each build
 * based on the git commit hash. Deterministic — same commit
 * always produces the same name.
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

export function generateBuildName() {
  let commitHash = 'dev';
  let commitShort = 'dev';
  let timestamp = new Date().toISOString();

  try {
    commitHash = execSync('git rev-parse HEAD', { encoding: 'utf-8' }).trim();
    commitShort = commitHash.substring(0, 7);
    timestamp = execSync('git log -1 --format=%cI', { encoding: 'utf-8' }).trim();
  } catch {
    // Not in a git repo — use timestamp-based fallback
    commitHash = Date.now().toString(16);
    commitShort = commitHash.substring(0, 7);
  }

  // Deterministic selection from commit hash
  const hashNum = parseInt(commitHash.substring(0, 8), 16);
  const adj = adjectives[hashNum % adjectives.length];
  const noun = nouns[Math.floor(hashNum / adjectives.length) % nouns.length];

  return {
    name: `${adj}-${noun}`,
    displayName: `${adj.charAt(0).toUpperCase() + adj.slice(1)} ${noun.charAt(0).toUpperCase() + noun.slice(1)}`,
    commit: commitShort,
    timestamp,
    full: `${adj}-${noun} (${commitShort})`,
  };
}
