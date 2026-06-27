import assert from 'assert';
import fs from 'fs/promises';
import { readFile, writeFile, createFolder } from '../src/fs.js';
import { execShell } from '../src/terminal.js';
import { retryOperation } from '../src/retry.js';
import { compressText, findRelevantFiles } from '../src/context.js';
import { debugShell, analyzeShellFailure } from '../src/debug.js';
import { Planner } from '../src/planner.js';
import { AgentManager } from '../src/agent-manager.js';
import { LongRunningTaskManager } from '../src/longRunning.js';
import { embedText } from '../src/embeddings.js';
import { createGitCheckpoint } from '../src/git-checkpoint.js';
import geminiProvider from '../src/providers/gemini.js';
import openrouterProvider from '../src/providers/openrouter.js';
import { chooseProviderAndModel, selectTaskModel } from '../src/providers/index.js';

function restoreEnv(snapshot) {
  for (const key of Object.keys(process.env)) {
    if (!(key in snapshot)) {
      delete process.env[key];
    }
  }
  for (const [key, value] of Object.entries(snapshot)) {
    process.env[key] = value;
  }
}

async function runTests() {
  const tempDir = './tests/.tmp';
  const filePath = `${tempDir}/sample.txt`;
  await fs.rm(tempDir, { recursive: true, force: true });
  await createFolder(tempDir);

  await writeFile(filePath, 'hello');
  const content = await readFile(filePath);
  assert.strictEqual(content, 'hello');

  const result = await execShell('echo test');
  assert.strictEqual(result.stdout.trim(), 'test');

  const gitCheckpointDir = `${tempDir}/git-checkpoint`;
  await fs.mkdir(gitCheckpointDir, { recursive: true });
  await execShell('git init', { cwd: gitCheckpointDir });
  await execShell('git config user.email "test@example.com"', { cwd: gitCheckpointDir });
  await execShell('git config user.name "Test User"', { cwd: gitCheckpointDir });
  await fs.writeFile(`${gitCheckpointDir}/checkpoint.txt`, 'checkpoint test');

  const checkpointResult = createGitCheckpoint({ message: 'checkpoint: test', cwd: gitCheckpointDir });
  assert.strictEqual(checkpointResult.success, true, `Checkpoint result failed: ${JSON.stringify(checkpointResult)}`);
  assert.strictEqual(typeof checkpointResult.commitHash, 'string');
  assert.strictEqual(checkpointResult.commitHash.length, 40);

  const noChangeResult = createGitCheckpoint({ message: 'checkpoint: test', cwd: gitCheckpointDir });
  assert.strictEqual(noChangeResult.success, false, `Expected no_changes result but got: ${JSON.stringify(noChangeResult)}`);
  assert.strictEqual(noChangeResult.reason, 'no_changes');

  const nonGitDir = `${tempDir}/not-a-git-repo`;
  await fs.mkdir(nonGitDir, { recursive: true });
  const noRepoResult = createGitCheckpoint({ message: 'checkpoint: fail', cwd: nonGitDir });
  assert.strictEqual(noRepoResult.success, false);
  assert.strictEqual(noRepoResult.reason, 'git_error');

  const retryResult = await retryOperation(() => Promise.resolve('ok'), { retries: 1 });
  assert.strictEqual(retryResult, 'ok');

  const compressed = compressText('a'.repeat(2000), 100);
  assert.ok(compressed.length <= 110);

  const files = await findRelevantFiles('.', 'README', { maxFiles: 5, searchLimit: 50 });
  assert.ok(Array.isArray(files));

  const debugResult = await debugShell('echo debug-test', { retries: 1, ai: false });
  assert.strictEqual(debugResult.success, true);
  assert.strictEqual(debugResult.result.stdout.trim(), 'debug-test');
  assert.strictEqual(analyzeShellFailure('false', { code: 1, stdout: '', stderr: 'command failed' }).includes('exited with code'), true);

  const planner = new Planner({ agents: [] });
  const plan = planner.createPlan('Write README and add CLI commands');
  assert.ok(plan.steps.length >= 1);
  assert.strictEqual(
    planner.classifyIntent('Build a React login page').intent,
    'implementation'
  );
  assert.strictEqual(
    planner.classifyIntent('Build a login page', { framework: 'react' }).intent,
    'implementation'
  );

  const manager = new AgentManager();
  const longRunning = new LongRunningTaskManager();
  const outputId = longRunning.createTask('noop', async () => 'ok');
  const task = longRunning.getTask(outputId);
  assert.strictEqual(task.name, 'noop');

  const originalEnv = { ...process.env };
  try {
    delete process.env.OPENAI_API_KEY;
    delete process.env.OPENROUTER_API_KEY;
    delete process.env.GEMINI_API_KEY;
    delete process.env.DEFAULT_PROVIDER;
    delete process.env.AI_MODEL;
    delete process.env.DEFAULT_MODEL;
    delete process.env.FALLBACK_MODEL;
    delete process.env.PLANNING_MODEL;
    delete process.env.CODING_MODEL;
    delete process.env.DEBUG_MODEL;

    process.env.OPENROUTER_API_KEY = 'openrouter-test';
    process.env.GEMINI_API_KEY = 'gemini-test';

    const debugSelection = chooseProviderAndModel({ prompt: 'debug this error' });
    assert.strictEqual(debugSelection.model, 'deepseek/deepseek-v4-fast');
    assert.strictEqual(debugSelection.provider.name, 'openrouter');

    const summarySelection = chooseProviderAndModel({ prompt: 'summarize repo' });
    assert.strictEqual(summarySelection.provider.name, 'gemini');
    assert.strictEqual(summarySelection.model, 'gemini-2.5-flash');

    const routeModel = selectTaskModel('build api endpoint');
    assert.strictEqual(routeModel, 'qwen/qwen3-coder-480b-a35b-instruct');

    const originalFetch = globalThis.fetch;
    try {
      let geminiRequest;
      globalThis.fetch = async (url, options) => {
        geminiRequest = { url, options };
        return {
          ok: true,
         json: async () => ({
  candidates: [
    {
      content: {
        parts: [
          {
            text: 'Gemini reply'
          }
        ]
      }
    }
  ]
})
        };
      };

      const geminiText = await geminiProvider.createCompletion({ prompt: 'test gemini', model: 'gemini-2.5-flash', maxTokens: 10 });
      assert.strictEqual(geminiText, 'Gemini reply');
      assert.ok(
  geminiRequest.url.includes('generateContent?key=')
);

      let openrouterRequest;
      globalThis.fetch = async (url, options) => {
        openrouterRequest = { url, options };
        return {
          ok: true,
          json: async () => ({ choices: [{ message: { content: 'OpenRouter reply' } }] })
        };
      };

      process.env.OPENROUTER_API_KEY = 'openrouter-test';
      const openrouterText = await openrouterProvider.createCompletion({ prompt: 'test openrouter', model: 'qwen/qwen3-next-80b-a3b-instruct', maxTokens: 10 });
      assert.strictEqual(openrouterText, 'OpenRouter reply');
      assert.ok(openrouterRequest.url.includes('/chat/completions'));

      globalThis.fetch = async () => ({
        ok: true,
        json: async () => ({
          choices: [{
            message: {
              content: [{ type: 'text', text: 'OpenRouter reply from array' }]
            }
          }]
        })
      });
      const openrouterArrayText = await openrouterProvider.createCompletion({ prompt: 'test openrouter array', model: 'qwen/qwen3-next-80b-a3b-instruct', maxTokens: 10 });
      assert.strictEqual(openrouterArrayText, 'OpenRouter reply from array');

      globalThis.fetch = async () => ({
        ok: true,
        json: async () => ({ choices: [{ text: 'OpenRouter reply fallback text' }] })
      });
      const openrouterTextFallback = await openrouterProvider.createCompletion({ prompt: 'test openrouter text fallback', model: 'qwen/qwen3-next-80b-a3b-instruct', maxTokens: 10 });
      assert.strictEqual(openrouterTextFallback, 'OpenRouter reply fallback text');

      globalThis.fetch = async () => ({
        ok: true,
        json: async () => ({ choices: [{ message: { text: 'OpenRouter reply assistant field' } }] })
      });
      const openrouterAssistantFieldText = await openrouterProvider.createCompletion({ prompt: 'test openrouter assistant field', model: 'qwen/qwen3-next-80b-a3b-instruct', maxTokens: 10 });
      assert.strictEqual(openrouterAssistantFieldText, 'OpenRouter reply assistant field');

      globalThis.fetch = async () => ({
        ok: false,
        status: 429,
        statusText: 'Too Many Requests',
        text: async () => JSON.stringify({
          error: {
            message: 'Provider returned error',
            code: 429,
            metadata: {
              raw: 'model is temporarily rate-limited upstream',
              retry_after_seconds: 30
            }
          }
        }),
        json: async () => ({})
      });

      try {
        await openrouterProvider.createCompletion({ prompt: 'test openrouter', model: 'qwen/qwen3-next-80b-a3b-instruct:free', maxTokens: 10 });
        assert.fail('Expected OpenRouter rate limit error');
      } catch (error) {
        assert.ok(error.message.includes('OpenRouter rate limit reached for qwen/qwen3-next-80b-a3b-instruct:free'));
        assert.ok(error.message.includes('Retry after 30 seconds'));
        assert.ok(error.message.includes('Try another model or retry shortly'));
      }
    } finally {
      globalThis.fetch = originalFetch;
    }

    delete process.env.OPENROUTER_API_KEY;
    delete process.env.GEMINI_API_KEY;
    delete process.env.OPENAI_API_KEY;

    process.env.OPENROUTER_API_KEY = 'openrouter-test';
    const selection = chooseProviderAndModel({ prompt: 'hello' });
    assert.ok(selection.provider);
  } finally {
    restoreEnv(originalEnv);
  }

  // Dotenv integration test
  await fs.mkdir(`${tempDir}/dotenv-test`, { recursive: true });
  await fs.writeFile(`${tempDir}/dotenv-test/.env`, 'DOTENV_TEST=loaded');
  const dotenvResult = await execShell('node --input-type=module -e "import \'dotenv/config\'; console.log(process.env.DOTENV_TEST)"', {
    cwd: `${tempDir}/dotenv-test`
  });
  assert.strictEqual(dotenvResult.stdout.trim(), 'loaded');

  const embedding = await embedText('test');
  assert.ok(Array.isArray(embedding));

  await fs.rm(tempDir, { recursive: true, force: true });
  await import("./patch-engine.test.js");
  console.log('All tests passed.');
}

runTests().catch((error) => {
  console.error(error);
  process.exit(1);
});
