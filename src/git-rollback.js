import { execSync } from 'child_process';

export function rollbackToCheckpoint({
  commitHash,
  cwd = process.cwd()
}) {
  if (typeof commitHash !== 'string' || !commitHash.trim()) {
    return {
      success: false,
      reason: 'git_error',
      error: 'Commit hash must be provided.'
    };
  }

  try {
    execSync('git rev-parse --is-inside-work-tree', {
      cwd,
      stdio: 'pipe'
    });

    execSync(`git rev-parse --verify ${commitHash}`, {
      cwd,
      stdio: 'pipe'
    });

    execSync(`git reset --hard ${commitHash}`, {
      cwd,
      stdio: 'pipe'
    });

    return {
      success: true,
      commitHash
    };
  } catch (error) {
    return {
      success: false,
      reason: 'git_error',
      error: error?.message ?? String(error)
    };
  }
}
