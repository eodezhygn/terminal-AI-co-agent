import assert from 'assert';
import { describe, it } from 'node:test';
import { extractActionsFromOutput } from '../src/coder-wrapper.js';
import { validateGeneratedCode } from '../src/validator.js';

describe('Coder wrapper and generated code validation', () => {
  it('should extract actions from best-effort JSON output', () => {
    const output = `Some explanatory text\n{\n  "actions": [\n    {"type": "create_file", "path": "example.txt", "content": "Hello world"}\n  ]\n}\n`;
    const actions = extractActionsFromOutput(output);
    assert.deepStrictEqual(actions, [
      {
        type: 'create_file',
        path: 'example.txt',
        content: 'Hello world'
      }
    ]);
  });

  it('should validate generatedCode-only results as valid', () => {
    const validation = validateGeneratedCode({
      status: 'success',
      generatedCode: 'function sayHello() { console.log("ok"); }'
    });

    assert.strictEqual(validation.valid, true);
    assert.strictEqual(validation.issues.length, 0);
  });

  it('should validate actions-only results as valid', () => {
    const validation = validateGeneratedCode({
      status: 'success',
      actions: [
        { type: 'create_file', path: 'hello.txt', content: 'hello' }
      ]
    });

    assert.strictEqual(validation.valid, true);
    assert.strictEqual(validation.issues.length, 0);
  });

  it('should extract actions from fenced JSON output and preserve generatedCode fallback', () => {
    const output = 'Please complete the task:\n```json\n{\n  "actions": [\n    {"type": "create_file", "path": "example.txt", "content": "Hello world"}\n  ],\n  "generatedCode": "console.log(\\"hi\\");"\n}\n```\nThank you.';
    const actions = extractActionsFromOutput(output);

    assert.deepStrictEqual(actions, [
      {
        type: 'create_file',
        path: 'example.txt',
        content: 'Hello world'
      }
    ]);
  });
});
