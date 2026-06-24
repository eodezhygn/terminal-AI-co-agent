import path from 'path';

export function validateProjectPath(projectRoot, targetPath) {
  if (typeof projectRoot !== 'string' || !projectRoot.trim()) {
    throw new Error('projectRoot must be a non-empty string');
  }

  if (typeof targetPath !== 'string') {
    throw new Error('targetPath must be a string');
  }

  const resolvedRoot = path.resolve(projectRoot);

  // Resolve target: if absolute, resolve directly; if relative, resolve against projectRoot
  const resolvedTarget = path.isAbsolute(targetPath)
    ? path.resolve(targetPath || '.')
    : path.resolve(resolvedRoot, targetPath || '.');

  const relative = path.relative(resolvedRoot, resolvedTarget);

  const isInside = (
    relative === '' ||
    (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative))
  );

  // On Windows, do a case-insensitive check as an extra precaution
  if (!isInside) {
    throw new Error('targetPath escapes projectRoot');
  }

  if (process.platform === 'win32') {
    const rootLower = resolvedRoot.toLowerCase();
    const targetLower = resolvedTarget.toLowerCase();
    if (!(targetLower === rootLower || targetLower.startsWith(rootLower + path.sep))) {
      throw new Error('targetPath escapes projectRoot');
    }
  }

  return resolvedTarget;
}
