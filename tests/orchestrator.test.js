import assert from 'assert';
import { describe, it } from 'node:test';
import { orchestrate } from '../src/orchestrator.js';

const projectRoot = new URL('../', import.meta.url).pathname;

describe('Deterministic Orchestrator Pipeline', () => {
  it('should classify planning tasks with planner role and no generated code', async () => {
    const result = await orchestrate({
      taskDescription: 'Design architecture for field operations app',
      projectRoot
    });

    assert.strictEqual(result.intent.name, 'planning', 'Intent should be planning');
    assert.strictEqual(result.intent.role.name, 'planner', 'Role should be planner');
    assert.strictEqual(
  result.intent.name,
  'planning'
);

assert.strictEqual(
  result.intent.role.name,
  'planner'
);

  });

  it('should classify implementation tasks with coder role and coder model selected', async () => {
    const result = await orchestrate({
      taskDescription: 'Create login API endpoint',
      projectRoot
    });

    assert.strictEqual(result.intent.name, 'implementation', 'Intent should be implementation');
    assert.strictEqual(result.intent.role.name, 'coder', 'Role should be coder');
    assert.strictEqual(result.intent.role.coderResult.selectedModel, 'qwen2.5-coder:1.5b', 'Selected model should be qwen2.5-coder:1.5b');
  });

  it('should select planner role for filesystem tasks', async () => {
    const result = await orchestrate({
      taskDescription: 'Create a folder named demo-test',
      projectRoot
    });

    assert.strictEqual(result.intent.name, 'filesystem', 'Intent should be filesystem');
    assert.strictEqual(result.intent.role.name, 'planner', 'Role should be planner for filesystem intent');
  });

  it('should prefer AI-generated actions when provided', async () => {
    const result = await orchestrate({
      taskDescription: 'Create example file',
      projectRoot,
      runCoderFn: async () => ({
        role: 'coder',
        selectedModel: 'qwen2.5-coder:1.5b',
        task: 'Create example file',
        contextSize: 0,
        status: 'success',
        generatedCode: 'console.log("hi");',
        actions: [
          { type: 'create_file', path: 'example.txt', content: 'hi' }
        ]
      })
    });

    assert.strictEqual(result.coder.actions.length, 1, 'Should preserve AI-generated actions');
    assert.strictEqual(result.actions.length, 1, 'Orchestrator should prefer AI actions');
    assert.strictEqual(result.actions[0].path, 'example.txt');
  });

  it('should fall back to generatedCode when actions are absent', async () => {
    const result = await orchestrate({
      taskDescription: 'Write fallback file',
      projectRoot,
      runCoderFn: async () => ({
        role: 'coder',
        selectedModel: 'qwen2.5-coder:1.5b',
        task: 'Write fallback file',
        contextSize: 0,
        status: 'success',
        generatedCode: 'console.log("fallback");',
        actions: []
      })
    });

    assert.strictEqual(result.actions.length, 1, 'Fallback should produce one create_file action');
    assert.strictEqual(result.actions[0].path, 'generated_code.txt');
    assert.strictEqual(result.generatedCode, 'console.log("fallback");');
  });

  it('should not execute actions when executeActions is false', async () => {
    let executorCalled = false;
    const result = await orchestrate({
      taskDescription: 'Create example file',
      projectRoot,
      executeActions: false,
      runCoderFn: async () => ({
        role: 'coder',
        selectedModel: 'qwen2.5-coder:1.5b',
        task: 'Create example file',
        contextSize: 0,
        status: 'success',
        generatedCode: 'console.log("hi");',
        actions: [
          { type: 'create_file', path: 'example.txt', content: 'hi' }
        ]
      }),
      executorFn: async () => {
        executorCalled = true;
        return { results: [] };
      }
    });

    assert.strictEqual(executorCalled, false, 'Executor should not be called when executeActions is false');
    assert.strictEqual(result.actions.length, 1, 'Actions should still be returned');
    assert.strictEqual(result.execution, undefined, 'Execution result should not be present');
  });

  it('should execute validated actions when executeActions is true', async () => {
    let receivedActions = null;
    const executionResponse = { createdFiles: ['example.txt'], failed: [] };

    const result = await orchestrate({
      taskDescription: 'Create example file',
      projectRoot,
      executeActions: true,
      runCoderFn: async () => ({
        role: 'coder',
        selectedModel: 'qwen2.5-coder:1.5b',
        task: 'Create example file',
        contextSize: 0,
        status: 'success',
        generatedCode: 'console.log("hi");',
        actions: [
          { type: 'create_file', path: 'example.txt', content: 'hi' }
        ]
      }),
      executorFn: async (actions) => {
        receivedActions = actions;
        return executionResponse;
      }
    });

    assert.strictEqual(Array.isArray(receivedActions), true, 'Executor should receive an actions array');
    assert.strictEqual(receivedActions.length, 1, 'Executor should receive the validated actions');
    assert.strictEqual(result.execution?.success, true, 'Execution should report success');
    assert.strictEqual(result.execution?.results, executionResponse, 'Execution results should be returned');
  });

  it('should not execute when actions are invalid even if executeActions is true', async () => {
    let executorCalled = false;

    const result = await orchestrate({
      taskDescription: 'Write fallback file',
      projectRoot,
      executeActions: true,
      runCoderFn: async () => ({
        role: 'coder',
        selectedModel: 'qwen2.5-coder:1.5b',
        task: 'Write fallback file',
        contextSize: 0,
        status: 'success',
        generatedCode: 'console.log("fallback");',
        actions: []
      }),
      executorFn: async () => {
        executorCalled = true;
        return { createdFiles: [], failed: [] };
      }
    });

    assert.strictEqual(executorCalled, false, 'Executor should not be called when actions are invalid');
    assert.strictEqual(result.execution, undefined, 'Execution result should not be present for invalid actions');
  });

  it('should return dry-run preview without calling executor', async () => {
    let executorCalled = false;

    const result = await orchestrate({
      taskDescription: 'Create example file',
      projectRoot,
      executeActions: true,
      dryRun: true,
      runCoderFn: async () => ({
        role: 'coder',
        selectedModel: 'qwen2.5-coder:1.5b',
        task: 'Create example file',
        contextSize: 0,
        status: 'success',
        generatedCode: 'console.log("hi");',
        actions: [
          { type: 'create_file', path: 'example.txt', content: 'hi' }
        ]
      }),
      executorFn: async () => {
        executorCalled = true;
        return { createdFiles: ['example.txt'], failed: [] };
      }
    });

    assert.strictEqual(executorCalled, false, 'Executor should not be called in dry run mode');
    assert.strictEqual(result.execution?.mode, 'dry-run', 'Execution mode should be dry-run');
    assert.strictEqual(result.execution?.success, true, 'Dry run should succeed for safe actions');
    assert.deepStrictEqual(result.execution?.actions, [
      { type: 'create_file', path: 'example.txt', content: 'hi' }
    ]);
  });

  it('should block unsafe action paths during execution', async () => {
    let executorCalled = false;

    const result = await orchestrate({
      taskDescription: 'Create secret file',
      projectRoot,
      executeActions: true,
      runCoderFn: async () => ({
        role: 'coder',
        selectedModel: 'qwen2.5-coder:1.5b',
        task: 'Create secret file',
        contextSize: 0,
        status: 'success',
        generatedCode: 'console.log("secret");',
        actions: [
          { type: 'create_file', path: '../secret.txt', content: 'top secret' }
        ]
      }),
      executorFn: async () => {
        executorCalled = true;
        return { createdFiles: ['../secret.txt'], failed: [] };
      }
    });

    assert.strictEqual(executorCalled, false, 'Executor should not be called for unsafe actions');
    assert.strictEqual(result.execution?.success, false, 'Execution should report failure for unsafe actions');
    assert.ok(Array.isArray(result.execution?.issues), 'Execution issues should be returned');
    assert.ok(result.execution.issues.some((issue) => issue.includes('outside sandbox') || issue.includes('parent directory traversal')));
  });
});
