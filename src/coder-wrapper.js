import { getLocalModelAssignments, getModelForRole } from './local-model-router.js';
import { generateCompletion } from './providers/ollama.js';

/**
 * Runs the coder model with local Ollama generation
 * @param {Object} config - Configuration object
 * @param {string} config.role - Model role (default: 'coder')
 * @param {Object} config.reducedContext - Reduced context for the task
 * @returns {Object}
 */
export async function runCoder({ role = 'coder', reducedContext }) {
  const { coderModel } = await getLocalModelAssignments();
  const selectedModel = coderModel || getModelForRole(role);

  const taskText =
    typeof reducedContext?.task === 'string'
      ? reducedContext.task
      : typeof reducedContext?.payload === 'string'
      ? reducedContext.payload
      : null;

  const prompt = [
    'You are a local code generation assistant.',
    `Role: ${role}`,
    taskText ? `Task: ${taskText}` : 'Task: <unspecified>',
    '',
    'Reduced task context:',
    JSON.stringify(reducedContext || {}, null, 2),
    '',
    'Generate the code needed to complete the task and return only the generated code.'
  ].join('\n');

  if (!selectedModel) {
    return {
      role,
      selectedModel: null,
      task: taskText,
      contextSize: reducedContext ? Object.keys(reducedContext).length : 0,
      status: 'error',
      generatedCode: null,
      error: 'No local coder model available.'
    };
  }

  const result = await generateCompletion({ model: selectedModel, prompt });

  if (!result.success) {
    return {
      role,
      selectedModel,
      task: taskText,
      contextSize: reducedContext ? Object.keys(reducedContext).length : 0,
      status: 'error',
      generatedCode: null,
      error: result.error || 'Ollama generation failed.'
    };
  }

  return {
    role,
    selectedModel,
    task: taskText,
    contextSize: reducedContext ? Object.keys(reducedContext).length : 0,
    status: 'success',
    generatedCode: result.output
  };
}
