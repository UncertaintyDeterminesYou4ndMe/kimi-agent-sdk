import { spawn } from "child_process";
import * as path from "node:path";
import * as fs from "fs";
import { KimiPaths } from "../../../agent_sdk/paths";
import type { FileChange } from "../../shared/types";

const BASELINE_REF = "refs/kimi/baseline";

function execGit(args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    const proc = spawn("git", args, { stdio: ["ignore", "pipe", "pipe"] });
    let out = "";
    let err = "";
    proc.stdout.on("data", (d) => (out += d));
    proc.stderr.on("data", (d) => (err += d));
    proc.on("close", (code) => (code === 0 ? resolve(out.trim()) : reject(new Error(err || `git exited ${code}`))));
    proc.on("error", reject);
  });
}

function git(workDir: string, sessionId: string, ...args: string[]): Promise<string> {
  const gitDir = KimiPaths.shadowGitDir(workDir, sessionId);
  return execGit([`--git-dir=${gitDir}`, `--work-tree=${workDir}`, ...args]);
}

function toRelative(workDir: string, absolutePath: string): string {
  return path.relative(workDir, absolutePath);
}

async function ensureRepo(workDir: string, sessionId: string): Promise<void> {
  const gitDir = KimiPaths.shadowGitDir(workDir, sessionId);
  if (!fs.existsSync(gitDir)) {
    fs.mkdirSync(path.dirname(gitDir), { recursive: true });
    await execGit(["init", "--bare", gitDir]);
  }
}

async function commitAll(workDir: string, sessionId: string, message: string): Promise<string> {
  await git(workDir, sessionId, "add", "-A").catch(() => {});
  await git(workDir, sessionId, "commit", "--allow-empty", "-m", message).catch(() => {});
  return git(workDir, sessionId, "rev-parse", "HEAD");
}

async function getBaselineRef(workDir: string, sessionId: string): Promise<string | null> {
  try {
    return await git(workDir, sessionId, "rev-parse", BASELINE_REF);
  } catch {
    return null;
  }
}

async function setBaselineRef(workDir: string, sessionId: string, hash: string): Promise<void> {
  await git(workDir, sessionId, "update-ref", BASELINE_REF, hash);
}

export const GitManager = {
  async initBaseline(workDir: string, sessionId: string): Promise<void> {
    await ensureRepo(workDir, sessionId);
    const hash = await commitAll(workDir, sessionId, "baseline");
    await setBaselineRef(workDir, sessionId, hash);
  },

  async commit(workDir: string, sessionId: string): Promise<void> {
    await ensureRepo(workDir, sessionId);
    await commitAll(workDir, sessionId, "snapshot");
  },

  async updateBaseline(workDir: string, sessionId: string): Promise<void> {
    await ensureRepo(workDir, sessionId);
    const head = await git(workDir, sessionId, "rev-parse", "HEAD");
    await setBaselineRef(workDir, sessionId, head);
  },

  async revertToBaseline(workDir: string, sessionId: string): Promise<void> {
    await ensureRepo(workDir, sessionId);
    const baseline = await getBaselineRef(workDir, sessionId);
    if (baseline) {
      await git(workDir, sessionId, "reset", "--hard", baseline);
    }
  },

  async revertFile(workDir: string, sessionId: string, absolutePath: string): Promise<void> {
    await ensureRepo(workDir, sessionId);
    const baseline = await getBaselineRef(workDir, sessionId);
    if (!baseline) {
      return;
    }

    const rel = toRelative(workDir, absolutePath);
    try {
      await git(workDir, sessionId, "checkout", baseline, "--", rel);
    } catch {
      if (fs.existsSync(absolutePath)) {
        fs.unlinkSync(absolutePath);
      }
    }
  },

  async getChanges(workDir: string, sessionId: string, trackedFiles: Set<string>): Promise<FileChange[]> {
    await ensureRepo(workDir, sessionId);
    const baseline = await getBaselineRef(workDir, sessionId);
    if (!baseline) {
      return [];
    }

    const changes: FileChange[] = [];

    for (const absolutePath of trackedFiles) {
      const relativePath = toRelative(workDir, absolutePath);
      if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
        continue;
      }

      const exists = fs.existsSync(absolutePath);
      const baselineContent = await this.getBaselineContent(workDir, sessionId, absolutePath);

      if (!exists && baselineContent !== null) {
        changes.push({
          path: relativePath,
          status: "Deleted",
          additions: 0,
          deletions: baselineContent.split("\n").length,
        });
        continue;
      }

      if (exists && baselineContent === null) {
        try {
          const content = fs.readFileSync(absolutePath, "utf-8");
          changes.push({
            path: relativePath,
            status: "Added",
            additions: content.split("\n").length,
            deletions: 0,
          });
        } catch {
          changes.push({ path: relativePath, status: "Added", additions: 0, deletions: 0 });
        }
        continue;
      }

      if (exists && baselineContent !== null) {
        const diff = await this.diff(workDir, sessionId, absolutePath);
        if (diff) {
          let additions = 0;
          let deletions = 0;
          for (const line of diff.split("\n")) {
            if (line.startsWith("+") && !line.startsWith("+++")) {
              additions++;
            } else if (line.startsWith("-") && !line.startsWith("---")) {
              deletions++;
            }
          }
          changes.push({ path: relativePath, status: "Modified", additions, deletions });
        }
      }
    }

    return changes;
  },

  async diff(workDir: string, sessionId: string, absolutePath: string): Promise<string> {
    await ensureRepo(workDir, sessionId);
    const baseline = await getBaselineRef(workDir, sessionId);
    if (!baseline) {
      return "";
    }

    const rel = toRelative(workDir, absolutePath);
    return git(workDir, sessionId, "diff", baseline, "--", rel).catch(() => "");
  },

  async getBaselineContent(workDir: string, sessionId: string, absolutePath: string): Promise<string | null> {
    await ensureRepo(workDir, sessionId);
    const baseline = await getBaselineRef(workDir, sessionId);
    if (!baseline) {
      return null;
    }

    const rel = toRelative(workDir, absolutePath);
    try {
      return await git(workDir, sessionId, "show", `${baseline}:${rel}`);
    } catch {
      return null;
    }
  },
};
