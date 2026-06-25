import assert from 'assert';
import fs from 'fs/promises';
import { execSync } from 'child_process';
import { describe, it } from 'node:test';
import { rollbackToCheckpoint } from '../src/git-rollback.js';

describe('Git Rollback', () => {

  it('fails when commit hash is missing', () => {
    const result = rollbackToCheckpoint({ commitHash: '' });
    assert.strictEqual(result.success, false);
  });

  it('fails for invalid commit hash', () => {
    const result = rollbackToCheckpoint({
      commitHash: 'not-a-real-hash'
    });

    assert.strictEqual(result.success, false);
    assert.strictEqual(result.reason, 'git_error');
  });

  it('fails outside a git repository', async () => {
    const dir = './tests/.tmp/non-git';
    await fs.mkdir(dir, { recursive: true });

    const result = rollbackToCheckpoint({
      commitHash: '1234567',
      cwd: dir
    });

    assert.strictEqual(result.success, false);
    assert.strictEqual(result.reason, 'git_error');
  });

  it('successfully rolls back to a previous commit', async () => {
    const dir = './tests/.tmp/git-rollback';

    await fs.rm(dir, { recursive: true, force: true });
    await fs.mkdir(dir, { recursive: true });

    execSync('git init', { cwd: dir });
    execSync('git config user.email "test@example.com"', { cwd: dir });
    execSync('git config user.name "Test User"', { cwd: dir });

    await fs.writeFile(`${dir}/file.txt`, 'v1');
    execSync('git add .', { cwd: dir });
    execSync('git commit -m "v1"', { cwd: dir });

    const commitA = execSync('git rev-parse HEAD', { cwd: dir })
      .toString()
      .trim();

    await fs.writeFile(`${dir}/file.txt`, 'v2');
    execSync('git add .', { cwd: dir });
    execSync('git commit -m "v2"', { cwd: dir });

    const result = rollbackToCheckpoint({
      commitHash: commitA,
      cwd: dir
    });

    assert.strictEqual(result.success, true);

    const content = await fs.readFile(`${dir}/file.txt`, 'utf8');
    assert.strictEqual(content, 'v1');
  });

});
