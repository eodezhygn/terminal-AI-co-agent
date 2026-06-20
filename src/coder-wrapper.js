import { getLocalModelAssignments, getModelForRole } from './local-model-router.js';
import { generateCompletion } from './providers/ollama.js';

const VALID_ACTION_TYPES = new Set([
  'create_file',
  'edit_file',
  'append_file',
  'create_folder',
  'read_file'
]);

function tryParseJsonCandidate(text) {
  if (typeof text !== 'string' || !text.trim()) {
    return null;
  }

  const trimmed = text.trim();
  const firstBrace = trimmed.indexOf('{');
  const firstBracket = trimmed.indexOf('[');
  const startCandidates = [firstBrace, firstBracket].filter((index) => index >= 0);
  if (startCandidates.length === 0) {
    return null;
  }

  const start = Math.min(...startCandidates);
  const lastBrace = trimmed.lastIndexOf('}');
  const lastBracket = trimmed.lastIndexOf(']');
  const end = Math.max(lastBrace, lastBracket);
  if (end <= start) {
    return null;
  }

  const candidate = trimmed.slice(start, end + 1);
  try {
    return JSON.parse(candidate);
  } catch {
    return null;
  }
}

function normalizeAction(action) {
  if (!action || typeof action !== 'object') {
    return null;
  }

  const type = typeof action.type === 'string' ? action.type.trim() : '';
  const path = typeof action.path === 'string' ? action.path.trim() : '';

  if (!VALID_ACTION_TYPES.has(type) || !path) {
    return null;
  }

  const normalized = { type, path };

  if (typeof action.content === 'string') {
    normalized.content = action.content;
  }

  if (typeof action.taskDescription === 'string') {
    normalized.taskDescription = action.taskDescription;
  }

  return normalized;
}

/**
 * Extract best-effort filesystem actions from model output.
 * generatedCode remains the primary guaranteed output.
 * Actions are optional and should not block the main result.
 *
 * @param {string} output
 * @returns {Array}
 */
export function extractActionsFromOutput(output) {
  if (typeof output !== 'string' || !output.trim()) {
    return [];
  }

  const parsed = tryParseJsonCandidate(output);
  const candidates = [];

  if (Array.isArray(parsed)) {
    candidates.push(...parsed);
  } else if (parsed && typeof parsed === 'object') {
    if (Array.isArray(parsed.actions)) {
      candidates.push(...parsed.actions);
    } else {
      candidates.push(parsed);
    }
  }

  return candidates.map(normalizeAction).filter(Boolean);
}

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
      actions: [],
      error: result.error || 'Ollama generation failed.'
    };
  }

  const output = String(result.stdout || result.output || '').trim();
  return {
    role,
    selectedModel,
    task: taskText,
    contextSize: reducedContext ? Object.keys(reducedContext).length : 0,
    status: 'success',
    generatedCode: output,
    actions: extractActionsFromOutput(output)
  };
}
