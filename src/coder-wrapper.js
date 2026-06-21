import { getLocalModelAssignments, getModelForRole } from './local-model-router.js';
import { generateCompletion } from './providers/ollama.js';

const VALID_ACTION_TYPES = new Set([
  'create_file',
  'edit_file',
  'append_file',
  'create_folder',
  'read_file'
]);

function extractBalancedJson(text, start) {
  const opening = text[start];
  const closing = opening === '{' ? '}' : ']';
  let depth = 0;
  let inString = false;
  let stringDelimiter = null;
  let escape = false;

  for (let index = start; index < text.length; index += 1) {
    const char = text[index];

    if (inString) {
      if (escape) {
        escape = false;
        continue;
      }
      if (char === '\\') {
        escape = true;
        continue;
      }
      if (char === stringDelimiter) {
        inString = false;
        stringDelimiter = null;
      }
      continue;
    }

    if (char === '"' || char === "'" || char === '`') {
      inString = true;
      stringDelimiter = char;
      continue;
    }

    if (char === opening) {
      depth += 1;
      continue;
    }

    if (char === closing) {
      depth -= 1;
      if (depth === 0) {
        return text.slice(start, index + 1);
      }
    }
  }

  return null;
}

function tryParseJsonCandidate(text) {
  if (typeof text !== 'string' || !text.trim()) {
    return null;
  }

  const candidates = [];
  const fencedRegex = /```(?:json)?\s*([\s\S]*?)\s*```/gi;
  let match;

  while ((match = fencedRegex.exec(text)) !== null) {
    candidates.push(match[1].trim());
  }

  if (candidates.length === 0) {
    const trimmed = text.trim();
    for (let index = 0; index < trimmed.length; index += 1) {
      const char = trimmed[index];
      if (char === '{' || char === '[') {
        const candidate = extractBalancedJson(trimmed, index);
        if (candidate) {
          candidates.push(candidate);
          break;
        }
      }
    }
  }

  for (const candidate of candidates) {
    try {
      return JSON.parse(candidate);
    } catch {
      continue;
    }
  }

  return null;
}

function tryParseActionsArray(text) {
  if (typeof text !== 'string' || !text.trim()) {
    return null;
  }

  const fencedRegex = /```(?:json)?\s*([\s\S]*?)\s*```/gi;
  let match;
  const candidates = [];

  while ((match = fencedRegex.exec(text)) !== null) {
    candidates.push(match[1].trim());
  }

  if (candidates.length === 0) {
    candidates.push(text);
  }

  for (const candidate of candidates) {
    const actionsKey = /"actions"\s*:\s*/i.exec(candidate);
    if (!actionsKey) {
      continue;
    }

    let index = actionsKey.index + actionsKey[0].length;
    while (index < candidate.length && /\s/.test(candidate[index])) {
      index += 1;
    }

    if (candidate[index] !== '[') {
      continue;
    }

    const arrayText = extractBalancedJson(candidate, index);
    if (!arrayText) {
      continue;
    }

    try {
      const parsedArray = JSON.parse(arrayText);
      if (Array.isArray(parsedArray)) {
        return parsedArray;
      }
    } catch {
      continue;
    }
  }

  return null;
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

  if (candidates.length === 0) {
    const actions = tryParseActionsArray(output);
    if (Array.isArray(actions)) {
      candidates.push(...actions);
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
    'Return a JSON object whenever possible.',
    'The JSON object must contain an actions array using only supported executor types:',
    '  create_folder, create_file, edit_file, append_file, read_file',
    'Each action must contain type and path. Include content when file content is available.',
    'If the task cannot be fully expressed as actions, return the generated code as a string in generatedCode.',
    'If both actions and generatedCode are available, return them together in the JSON object.'
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
  const parsed = tryParseJsonCandidate(output);
  const generatedCode = parsed && typeof parsed.generatedCode === 'string'
    ? parsed.generatedCode.trim()
    : output;

  return {
    role,
    selectedModel,
    task: taskText,
    contextSize: reducedContext ? Object.keys(reducedContext).length : 0,
    status: 'success',
    generatedCode,
    actions: extractActionsFromOutput(output)
  };
}
