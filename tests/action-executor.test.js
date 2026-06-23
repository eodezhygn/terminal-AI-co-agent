import assert from 'assert';
import fs from 'fs/promises';
import { executeActions } from '../src/executor/action-executor.js';

const tempDir = './tests/.tmp-action-executor';

async function cleanup() {
  await fs.rm(tempDir, { recursive: true, force: true });
}

async function runTests() {
  await cleanup();
  await fs.mkdir(tempDir, { recursive: true });

  const createAction = {
    type: 'create_file',
    path: `${tempDir}/create-file.txt`,
    content: 'hello create'
  };

  const createResult = await executeActions([createAction]);
  assert.strictEqual(createResult.success, true);
  assert.strictEqual(createResult.results.length, 1);
  assert.strictEqual(createResult.results[0].action, 'create_file');
  assert.strictEqual(createResult.results[0].path, createAction.path);
  assert.strictEqual(createResult.results[0].success, true);

  const createdContent = await fs.readFile(createAction.path, 'utf8');
  assert.strictEqual(createdContent, 'hello create');

  const editAction = {
    type: 'edit_file',
    path: createAction.path,
    content: 'updated content'
  };

  const editResult = await executeActions([editAction]);
  assert.strictEqual(editResult.success, true);
  assert.strictEqual(editResult.results[0].success, true);
  const editedContent = await fs.readFile(editAction.path, 'utf8');
  assert.strictEqual(editedContent, 'updated content');

  const deleteAction = {
    type: 'delete_file',
    path: editAction.path
  };

  const deleteResult = await executeActions([deleteAction]);
  assert.strictEqual(deleteResult.success, true);
  assert.strictEqual(deleteResult.results[0].success, true);

  let fileExists = true;
  try {
    await fs.access(deleteAction.path);
  } catch {
    fileExists = false;
  }
  assert.strictEqual(fileExists, false);

  const dryRunAction = {
    type: 'create_file',
    path: `${tempDir}/dry-run.txt`,
    content: 'dry run'
  };

  const dryRunResult = await executeActions([dryRunAction], { dryRun: true });
  assert.strictEqual(dryRunResult.success, true);
  assert.strictEqual(dryRunResult.results[0].simulated, true);
  assert.strictEqual(dryRunResult.results[0].success, true);

  let dryRunExists = true;
  try {
    await fs.access(dryRunAction.path);
  } catch {
    dryRunExists = false;
  }
  assert.strictEqual(dryRunExists, false);

  const missingEdit = {
    type: 'edit_file',
    path: `${tempDir}/missing.txt`,
    content: 'nothing'
  };
  const missingResult = await executeActions([missingEdit]);
  assert.strictEqual(missingResult.success, false);
  assert.strictEqual(missingResult.results[0].success, false);
  assert.strictEqual(missingResult.results[0].error, 'File does not exist');

  const invalidAction = {
    type: 'unsupported_action',
    path: `${tempDir}/invalid.txt`
  };
  const invalidResult = await executeActions([invalidAction]);
  assert.strictEqual(invalidResult.success, false);
  assert.strictEqual(invalidResult.results[0].success, false);
  assert.ok(invalidResult.results[0].error.includes('Unsupported action type'));

const blockedEnv = await executeActions([
  {
    type: 'create_file',
    path: '.env',
    content: 'SECRET=123'
  }
]);

assert.strictEqual(blockedEnv.success, false);
assert.strictEqual(
  blockedEnv.results[0].success,
  false
);

const blockedGit = await executeActions([
  {
    type: 'create_file',
    path: '.git/config',
    content: 'bad'
  }
]);

assert.strictEqual(blockedGit.success, false);

const blockedTraversal =
  await executeActions([
    {
      type: 'create_file',
      path: '../outside.txt',
      content: 'bad'
    }
  ]);

assert.strictEqual(
  blockedTraversal.success,
  false
);

const blockedNodeModules =
  await executeActions([
    {
      type: 'create_file',
      path: 'node_modules/test.js',
      content: 'bad'
    }
  ]);

assert.strictEqual(
  blockedNodeModules.success,
  false
);

  await cleanup();
  console.log('Action executor tests passed.');
}

runTests().catch((error) => {
  console.error(error);
  process.exit(1);
});
