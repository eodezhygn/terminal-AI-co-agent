import assert from 'assert';
import { describe, it } from 'node:test';
import { validateSandboxPath } from '../src/sandbox-validator.js';

const projectRoot = new URL('../', import.meta.url).pathname;

describe('Sandbox Validator', () => {
  it('should allow valid project-local paths', () => {
    const validPaths = [
      'src/index.js',
      'backend/auth/login.ts',
      'tests/orchestrator.test.js',
      'docs/architecture.md',
      'README.md'
    ];

    validPaths.forEach((filePath) => {
      const result = validateSandboxPath(filePath, { projectRoot });
      assert.strictEqual(result.valid, true, `Expected ${filePath} to be allowed`);
      assert.deepStrictEqual(result.issues, []);
    });
  });

  it('should block parent directory traversal paths', () => {
    const result = validateSandboxPath('../secret.txt', { projectRoot });
    assert.strictEqual(result.valid, false);
    assert.ok(result.issues.some((issue) => issue.includes('outside sandbox') || issue.includes('parent directory traversal')));
  });

  it('should block .git paths', () => {
    const result = validateSandboxPath('.git/config', { projectRoot });
    assert.strictEqual(result.valid, false);
    assert.ok(result.issues.some((issue) => issue.includes('.git')));
  });

  it('should block .env paths', () => {
    const result = validateSandboxPath('.env', { projectRoot });
    assert.strictEqual(result.valid, false);
    assert.ok(result.issues.some((issue) => issue.includes('.env')));
  });

  it('should block node_modules paths', () => {
    const result = validateSandboxPath('node_modules/module/index.js', { projectRoot });
    assert.strictEqual(result.valid, false);
    assert.ok(result.issues.some((issue) => issue.includes('node_modules')));
  });

  it('should block home directory references', () => {
    const result = validateSandboxPath('~/secrets.txt', { projectRoot });
    assert.strictEqual(result.valid, false);
    assert.ok(result.issues.some((issue) => issue.includes('home directory')));
  });
});
