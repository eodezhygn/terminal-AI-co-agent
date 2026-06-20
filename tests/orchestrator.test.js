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
    assert.strictEqual(result.intent.role.coderResult.generatedCode, null, 'Generated code should be null for deterministic stub');
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
});
