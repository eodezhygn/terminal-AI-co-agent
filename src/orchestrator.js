import { Planner } from './planner.js';
import { extractProjectContext } from './context-extractor.js';
import { reduceTaskContext } from './task-reducer.js';
import { runCoder } from './coder-wrapper.js';
import { validateActions, validateGeneratedCode } from './validator.js';
import { getRoleForIntent } from './local-model-router.js';

const FALLBACK_FILE_NAME = 'generated_code.txt';

function buildFallbackActions(generatedCode) {
  const text = typeof generatedCode === 'string' ? generatedCode.trim() : '';
  if (!text) {
    return [];
  }

  return [
    {
      type: 'create_file',
      path: FALLBACK_FILE_NAME,
      content: text
    }
  ];
}

function extractActions(coderResult) {
  if (!coderResult || typeof coderResult !== 'object') {
    return [];
  }

  if (Array.isArray(coderResult.actions)) {
    return coderResult.actions.filter(
      (action) => action && typeof action === 'object' && typeof action.type === 'string' && typeof action.path === 'string'
    );
  }

  return [];
}

/**
 * Orchestrate the logical flow for a single task.
 * @param {Object} params
 * @param {string} params.taskDescription
 * @param {string} [params.projectRoot=process.cwd()]
 * @returns {Object} deterministic orchestration result
 */
export async function orchestrate({ taskDescription, projectRoot = process.cwd(), runCoderFn = runCoder } = {}) {
  if (typeof taskDescription !== 'string') {
    throw new TypeError('taskDescription must be a string');
  }

  // 1) Classify intent using Planner
  const planner = new Planner();
  const classification = planner.classifyIntent(taskDescription);
  const intent = classification.intent || 'unknown';
  const confidence = typeof classification.confidence === 'number' ? classification.confidence : null;

  // 2) Extract project context
  const projectContext = extractProjectContext(projectRoot);

  // 3) Reduce context deterministically
  const reducedString = reduceTaskContext({ taskDescription, projectContext });
  let reducedContext;
  try {
    reducedContext = JSON.parse(reducedString);
  } catch (e) {
    reducedContext = { payload: String(reducedString) };
  }

  // 4) Resolve role from intent
  const role = getRoleForIntent(intent);

  // 5) Run coder wrapper (deterministic stub)
  const coderResult = await runCoderFn({ role, reducedContext });
  const validation = validateGeneratedCode(coderResult);
  const status = coderResult?.status === 'success' && validation.valid ? 'success' : 'error';
  const actions = extractActions(coderResult);
  const actionValidation = validateActions(actions);
  const fallbackActions = buildFallbackActions(coderResult?.generatedCode);
  const effectiveActions = actionValidation.valid ? actions : fallbackActions;

  // 6) Return deterministic orchestration result (nested as requested)
  return {
    planner: {
      intent: { name: intent, confidence },
      role
    },
    reducedTask: reducedContext,
    coder: coderResult,
    validation,
    actions: effectiveActions,
    generatedCode: coderResult?.generatedCode ?? null,
    status,
    task: taskDescription,
    intent: {
      name: intent,
      confidence,
      role: {
        name: role,
        reducedContext,
        coderResult
      }
    }
  };
}

export default orchestrate;
