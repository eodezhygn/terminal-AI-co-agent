import { spawnSync } from 'child_process';

/**
 * Attempt to parse Ollama list output into model names.
 * Supports both JSON output and plain text table output.
 *
 * @param {string} stdout
 * @returns {string[]}
 */
function parseOllamaList(stdout) {
  if (!stdout) {
    return [];
  }

  const content = String(stdout).trim();
  if (!content) {
    return [];
  }

  try {
    const parsed = JSON.parse(content);
    if (Array.isArray(parsed)) {
      return parsed
        .map((item) => {
          if (typeof item === 'string') {
            return item;
          }
          if (item && typeof item === 'object') {
            return item.name || item.model || item.id || '';
          }
          return '';
        })
        .filter(Boolean);
    }
  } catch {
    // Ignore JSON parse failures and fall back to text parsing.
  }

  return content
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && !/^MODEL\s+/i.test(line) && !/^NAME\s+/i.test(line))
    .map((line) => line.split(/\s+/)[0])
    .filter(Boolean);
}

/**
 * Check whether the Ollama CLI is available on the local environment.
 *
 * @returns {boolean}
 */
export function isOllamaAvailable() {
  const checks = [
    ['--version'],
    ['version']
  ];

  for (const args of checks) {
    try {
      const result = spawnSync('ollama', args, {
        stdio: ['ignore', 'ignore', 'ignore'],
        timeout: 5000,
        encoding: 'utf8'
      });

      if (result.error) {
        if (result.error.code === 'ENOENT') {
          // Ollama CLI is not installed at all.
          return false;
        }

        // The command form may not be supported by this Ollama version;
        // continue and try the next compatibility form.
        continue;
      }

      if (result.status === 0) {
        return true;
      }
    } catch (error) {
      if (error?.code === 'ENOENT') {
        return false;
      }
    }
  }

  return false;
}

/**
 * List installed Ollama models.
 *
 * @returns {Promise<string[]>}
 */
export async function listModels() {
  try {
    const result = spawnSync('ollama', ['list', '--json'], {
      stdio: ['ignore', 'pipe', 'pipe'],
      encoding: 'utf8',
      timeout: 10000,
      maxBuffer: 10 * 1024 * 1024
    });

    if (result.status === 0 && result.stdout) {
      return parseOllamaList(result.stdout);
    }

    // Ollama versions without --json support still expose a plain text list.
    const fallback = spawnSync('ollama', ['list'], {
      stdio: ['ignore', 'pipe', 'pipe'],
      encoding: 'utf8',
      timeout: 10000,
      maxBuffer: 10 * 1024 * 1024
    });

    if (fallback.status === 0 && fallback.stdout) {
      return parseOllamaList(fallback.stdout);
    }

    return [];
  } catch {
    return [];
  }
}

/**
 * Run Ollama with the provided model and prompt.
 *
 * @param {Object} options
 * @param {string} options.model
 * @param {string} options.prompt
 * @returns {Promise<{success: boolean, output?: string, error?: string}>}
 */
export async function generateCompletion({ model, prompt }) {
  if (!model) {
    return {
      success: false,
      error: 'Missing Ollama model name.'
    };
  }

  if (typeof prompt !== 'string' || !prompt.trim()) {
    return {
      success: false,
      error: 'Missing prompt text for Ollama.'
    };
  }

  try {
    const result = spawnSync('ollama', ['run', model], {
      input: prompt,
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 120000,
      maxBuffer: 10 * 1024 * 1024
    });

    if (result.error) {
      return {
        success: false,
        error: `Ollama execution failed: ${result.error.message}`
      };
    }

    if (result.status !== 0) {
      const stderr = String(result.stderr || '').trim();
      return {
        success: false,
        error: `Ollama returned code ${result.status}${stderr ? `: ${stderr}` : ''}`
      };
    }

    const output = String(result.stdout || '').trim();
    return {
      success: true,
      output
    };
  } catch (error) {
    return {
      success: false,
      error: `Failed to run Ollama: ${error?.message || 'unknown error'}`
    };
  }
}

export default {
  name: 'ollama',
  isAvailable: isOllamaAvailable,
  listModels,
  generateCompletion
};
