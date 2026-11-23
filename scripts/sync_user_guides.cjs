// The area guides, the phone guide and the glossary are written in docs/user-guide/ and served from frontend_v2/public/docs/.
// Run from the repository root after editing them: node scripts/sync_user_guides.cjs
// With --check it only reports copies that differ (the frontend test user-guide-copies.test.ts does the same).
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const src = path.join(root, 'docs/user-guide');
const out = path.join(root, 'frontend_v2/public/docs');
const pairs = [['glossary.md', 'glossary.md'], ['phone-user-guide.md', 'phone-guide/phone-user-guide.md'], ...fs.readdirSync(path.join(src, 'guides'))
  .filter((f) => f.endsWith('.md')).map((f) => [`guides/${f}`, `guides/${f}`])];
const check = process.argv.includes('--check');
let differ = 0;
for (const [from, to] of pairs) {
  const text = fs.readFileSync(path.join(src, from), 'utf8');
  if (text.includes('—')) throw Error(`${from} contains an em dash.`);
  const target = path.join(out, to);
  const same = fs.existsSync(target) && fs.readFileSync(target, 'utf8') === text;
  if (same) continue;
  differ++;
  if (check) console.log(`differs: docs/user-guide/${from} -> frontend_v2/public/docs/${to}`);
  else { fs.mkdirSync(path.dirname(target), { recursive: true }); fs.writeFileSync(target, text); console.log(`copied ${from}`); }
}
if (check && differ) process.exit(1);
