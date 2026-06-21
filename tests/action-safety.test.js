import assert from 'assert';
import { describe, it } from 'node:test';
import { validateActionSafety } from '../src/action-safety.js';

const projectRoot = new URL('../', import.meta.url).pathname;

describe('Action Safety Layer', () => {
  it('should pass valid actions', () => {
    const result = validateActionSafety([
      { type: 'create_file', path: 'src/example.js', content: 'console.log("hi");' }
    ], { projectRoot });

    assert.strictEqual(result.valid, true);
    assert.deepStrictEqual(result.issues, []);
  });

  it('should fail invalid actions with unsafe paths', () => {
    const result = validateActionSafety([
      { type: 'create_file', path: '../secret.txt', content: 'hidden' }
    ], { projectRoot });

    assert.strictEqual(result.valid, false);
    assert.ok(result.issues.length > 0);
    assert.ok(result.issues[0].includes('outside sandbox'));
  });
});
