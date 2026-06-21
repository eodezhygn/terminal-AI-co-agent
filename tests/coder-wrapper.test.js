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

  it('should extract actions when generatedCode is malformed JavaScript template literal inside fenced JSON', () => {
    const output = 'Some output text\n```json\n{\n  "actions": [\n    {\n      "type": "create_folder",\n      "path": "src/agents"\n    }\n  ],\n  "generatedCode": `...`\n}\n```\n';

    const actions = extractActionsFromOutput(output);
    assert.strictEqual(actions.length > 0, true);
    assert.deepStrictEqual(actions, [
      {
        type: 'create_folder',
        path: 'src/agents'
      }
    ]);
  });

  it('should extract actions when the model returns malformed JSON with generatedCode template literals', () => {
    const output = '{\n      "actions": [\n            {\n                      "type": "create_folder",\n                            "path": "src"\n            },\n                {\n                          "type": "create_file",\n                                "path": "src/App.js",\n                                      "content": "..."\n                }\n      ],\n        "generatedCode": `\n        const React = require(\'react\');\n        ...\n        `\n}\n';

    const actions = extractActionsFromOutput(output);
    assert.strictEqual(actions.length > 0, true);
    assert.deepStrictEqual(actions, [
      {
        type: 'create_folder',
        path: 'src'
      },
      {
        type: 'create_file',
        path: 'src/App.js',
        content: '...'
      }
    ]);
  });
});
