import { listModels } from './providers/ollama.js';

/**
 * Lightweight local model router and local model detection helpers.
 *
 * Exports:
 * - getModelForRole(role)
 * - getRoleForIntent(intent)
 * - getAvailableLocalModels()
 * - getPlannerModel()
 * - getCoderModel()
 * - getLocalModelAssignments()
 *
 * Notes:
 * - ESM module
 * - Uses Ollama local model listing for detection
 * - Normalizes input with trim()+toLowerCase()
 */

/** @type {Record<string, string>} */
const ROLE_MODEL_MAP = {
  planner: 'qwen2.5:0.5b',
  coder: 'qwen2.5-coder:1.5b',
};

const PREFERRED_PLANNER_MODELS = ['qwen2.5:0.5b'];
const PREFERRED_CODER_MODELS = ['coder'];

function selectPreferredModel(models, preferences) {
  if (!Array.isArray(models) || models.length === 0) {
    return '';
  }

  const normalized = models.map((model) => String(model ?? '').trim());
  for (const preference of preferences) {
    const match = normalized.find((name) =>
      name.toLowerCase().includes(preference.toLowerCase())
    );
    if (match) {
      return match;
    }
  }

  return normalized[0];
}

/** @type {Record<string, 'planner' | 'coder'>} */
const INTENT_ROLE_MAP = {
  planning: 'planner',
  implementation: 'coder',
  filesystem: 'planner',
  unknown: 'planner',
};

/**
 * Resolve a model name for a logical role.
 *
 * @param {string} role - Logical role (e.g., 'planner', 'coder')
 * @returns {string} Model identifier to use for the role.
 */
export function getModelForRole(role) {
  const normalizedRole = String(role ?? '').trim().toLowerCase();
  return (
    ROLE_MODEL_MAP[normalizedRole] || process.env.DEFAULT_MODEL || 'gemini'
  );
}

/**
 * Attempt to list installed local Ollama models.
 *
 * @returns {Promise<string[]>}
 */
export async function getAvailableLocalModels() {
  try {
    const models = await listModels();
    return Array.isArray(models) ? models.map((m) => String(m ?? '').trim()).filter(Boolean) : [];
  } catch {
    return [];
  }
}

/**
 * Resolve the best local model for planner duties.
 *
 * @param {string[]} availableModels
 * @returns {string}
 */
export function getPlannerModel(availableModels) {
  return selectPreferredModel(availableModels, PREFERRED_PLANNER_MODELS);
}

/**
 * Resolve the best local model for coder duties.
 *
 * @param {string[]} availableModels
 * @returns {string}
 */
export function getCoderModel(availableModels) {
  return selectPreferredModel(availableModels, PREFERRED_CODER_MODELS);
}

/**
 * Resolve the local model assignments for planner/coder.
 *
 * @returns {Promise<{plannerModel:string,coderModel:string,availableModels:string[]}>}
 */
export async function getLocalModelAssignments() {
  const availableModels = await getAvailableLocalModels();
  return {
    plannerModel: getPlannerModel(availableModels),
    coderModel: getCoderModel(availableModels),
    availableModels
  };
}

/**
 * Resolve the agent role for a given task intent.
 *
 * @param {string} intent - Intent classification (e.g., 'planning')
 * @returns {'planner'|'coder'} The mapped role.
 */
export function getRoleForIntent(intent) {
  const normalizedIntent = String(intent ?? '').trim().toLowerCase();
  return INTENT_ROLE_MAP[normalizedIntent] || 'planner';
}
