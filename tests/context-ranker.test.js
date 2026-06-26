import assert from 'assert';
import { rankRelevantFiles } from '../src/context/context-ranker.js';

function arraysEqual(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

async function runTests() {
  console.log('Testing context ranker...');

  // Test: empty candidate list
  let res = rankRelevantFiles('update utils', []);
  assert.deepStrictEqual(res, [], 'Empty candidate list should return empty array');
  console.log('✓ empty candidate list');

  // Test: exact filename match
  const candidates1 = ['src/utils.js', 'src/helpers.js', 'docs/utils.md'];
  res = rankRelevantFiles('Please update utils.js', candidates1);
  assert.strictEqual(res[0], 'src/utils.js', 'Exact filename match should rank first');
  console.log('✓ exact filename match');

  // Test: directory match
  const candidates2 = ['src/auth/auth.ts', 'src/auth/login.ts', 'src/other/file.js'];
  res = rankRelevantFiles('Fix something in auth', candidates2);
  // both auth files should come before the other file
  assert.ok(res.indexOf('src/auth/auth.ts') < res.indexOf('src/other/file.js'));
  assert.ok(res.indexOf('src/auth/login.ts') < res.indexOf('src/other/file.js'));
  console.log('✓ directory match');

  // Test: multiple candidates scoring
  const candidates3 = ['src/feature/foo.js', 'lib/foo.js', 'src/feature/bar.js', 'README.md'];
  res = rankRelevantFiles('update feature foo', candidates3);
  // expect 'src/feature/foo.js' highest, then 'src/feature/bar.js' or 'lib/foo.js'
  assert.strictEqual(res[0], 'src/feature/foo.js', 'Best match should be src/feature/foo.js');
  console.log('✓ multiple candidates ordering');

  // Test: stable ordering when scores tie
  const candidates4 = ['tools/a.txt', 'tools/b.txt', 'other/c.txt'];
  // no tokens match, none under src/, scores should tie -> preserve input order
  res = rankRelevantFiles('unrelated query', candidates4);
  assert.ok(arraysEqual(res, candidates4), 'Stable ordering should preserve input order when scores tie');
  console.log('✓ stable ordering on ties');

  console.log('\nAll context-ranker tests passed.');
}

runTests().catch((err) => {
  console.error('Test failed:', err && err.message ? err.message : err);
  process.exit(1);
});
