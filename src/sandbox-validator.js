import path from 'path';

const BLOCKED_SEGMENTS = new Set([
  '.git',
  '.env',
  '.env.local',
  '.env.production',
  '.env.development',
  'node_modules'
]);

const BLOCKED_FILES = new Set([
  'package-lock.json',
  'pnpm-lock.yaml',
  'yarn.lock'
]);
const ABSOLUTE_PATH_PATTERN = /^(?:[A-Za-z]:[\\/]|\\|\/)/;
const HOME_PATH_PATTERN = /(^|[\\/])~($|[\\/])/;

export function validateSandboxPath(filePath, { projectRoot = process.cwd() } = {}) {
  const issues = [];

  if (typeof filePath !== 'string' || !filePath.trim()) {
    return {
      valid: false,
      issues: ['Path must be a non-empty string.']
    };
  }

  const normalizedPath = filePath.replace(/\\/g, '/').trim();

  if (HOME_PATH_PATTERN.test(normalizedPath)) {
    issues.push(`Path '${filePath}' references a home directory and is not allowed.`);
  }

  const isAbsolute = ABSOLUTE_PATH_PATTERN.test(normalizedPath);
  const normalizedRoot = path.resolve(projectRoot);
  const resolvedPath = isAbsolute
    ? path.resolve(normalizedPath)
    : path.resolve(normalizedRoot, normalizedPath);

  if (!resolvedPath.startsWith(normalizedRoot + path.sep) && resolvedPath !== normalizedRoot) {
    issues.push(`Path '${filePath}' is outside sandbox.`);
  }

  const cleanPath = path.posix.normalize(normalizedPath);
  const segments = cleanPath.split('/').filter(Boolean);

  if (BLOCKED_FILES.has(path.posix.basename(cleanPath))) {
  issues.push(
    `Path '${filePath}' references a protected file.`
  );
}

  if (segments.some((segment) => BLOCKED_SEGMENTS.has(segment))) {
    issues.push(`Path '${filePath}' references a blocked sandbox location.`);
  }

  if (segments.includes('..')) {
    issues.push(`Path '${filePath}' contains parent directory traversal and is not allowed.`);
  }

  return {
    valid: issues.length === 0,
    issues
  };
}
