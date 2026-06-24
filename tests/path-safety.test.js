import assert from 'assert';
import { describe, it } from 'node:test';
import path from 'path';
import { validateProjectPath } from '../src/path-safety.js';

const projectRoot = new URL('../', import.meta.url).pathname;

describe('Path Safety - validateProjectPath', () => {
  it('allows simple relative paths', () => {
    const res = validateProjectPath(projectRoot, 'src/index.js');
    assert.ok(res.startsWith(path.resolve(projectRoot)));
  });

  it('allows ./ relative paths', () => {
    const res = validateProjectPath(projectRoot, './src/index.js');
    assert.ok(res.startsWith(path.resolve(projectRoot)));
  });

  it('allows nested paths inside project', () => {
    const res = validateProjectPath(projectRoot, 'src/sub/dir/file.txt');
    assert.ok(res.startsWith(path.resolve(projectRoot)));
  });

  it('blocks parent traversal escapes with ../', () => {
    assert.throws(() => validateProjectPath(projectRoot, '../hack.txt'));
  });

  it('blocks deep parent traversal escapes', () => {
    assert.throws(() => validateProjectPath(projectRoot, '../../etc/passwd'));
  });

  it('blocks absolute paths outside project root', () => {
    const absOutside = path.resolve(path.parse(projectRoot).root, 'outside.txt');
    assert.throws(() => validateProjectPath(projectRoot, absOutside));
  });

  it('handles empty target path by resolving to project root', () => {
    const res = validateProjectPath(projectRoot, '');
    assert.strictEqual(res, path.resolve(projectRoot));
  });
});
