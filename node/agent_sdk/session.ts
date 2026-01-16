import * as crypto from "node:crypto";
import { ProtocolClient } from "./protocol";
import { SessionError } from "./errors";
import type { SessionOptions, ContentPart, StreamEvent, RunResult, ApprovalResponse } from "./schema";

export type SessionState = "idle" | "active" | "closed";

/** 当前生效的配置快照 */
interface ActiveConfig {
  model: string | undefined;
  thinking: boolean;
  yoloMode: boolean;
  executable: string;
  env: string; // JSON stringified for comparison
}

/** Turn 接口，代表一次对话轮次 */
export interface Turn {
  /** 异步迭代事件流，迭代完成后返回 RunResult */
  [Symbol.asyncIterator](): AsyncIterator<StreamEvent, RunResult, undefined>;
  /** 中断当前轮次，清空消息队列 */
  interrupt(): Promise<void>;
  /** 响应审批请求 */
  approve(requestId: string, response: ApprovalResponse): Promise<void>;
  /** 轮次完成后的结果 Promise */
  readonly result: Promise<RunResult>;
}

/** Session 接口，代表一个与 Kimi Code 的持久连接 */
export interface Session {
  /** 会话 ID */
  readonly sessionId: string;
  /** 工作目录 */
  readonly workDir: string;
  /** 当前状态：idle | active | closed */
  readonly state: SessionState;
  /** 模型 ID，可在轮次间修改 */
  model: string | undefined;
  /** 是否启用思考模式，可在轮次间修改 */
  thinking: boolean;
  /** 是否自动批准操作，可在轮次间修改 */
  yoloMode: boolean;
  /** CLI 可执行文件路径，可在轮次间修改 */
  executable: string;
  /** 环境变量，可在轮次间修改 */
  env: Record<string, string>;
  /** 发送消息，返回 Turn 对象 */
  prompt(content: string | ContentPart[]): Turn;
  /** 关闭会话，释放资源 */
  close(): Promise<void>;
  /** 支持 using 语法自动关闭 */
  [Symbol.asyncDispose](): Promise<void>;
}

class TurnImpl implements Turn {
  readonly result: Promise<RunResult>;
  private resolveResult: (result: RunResult) => void;
  private rejectResult: (error: Error) => void;
  private interrupted = false;

  constructor(
    private getClient: () => Promise<ProtocolClient>,
    private getCurrentClient: () => ProtocolClient | null,
    private getNextPending: () => (string | ContentPart[]) | undefined,
    private clearPending: () => void,
    private onComplete: () => void,
  ) {
    let resolve!: (result: RunResult) => void;
    let reject!: (error: Error) => void;
    this.result = new Promise<RunResult>((res, rej) => {
      resolve = res;
      reject = rej;
    });
    this.result.catch(() => {});
    this.resolveResult = resolve;
    this.rejectResult = reject;
  }

  async *[Symbol.asyncIterator](): AsyncIterator<StreamEvent, RunResult, undefined> {
    try {
      let result: RunResult | undefined;
      let content: string | ContentPart[] | undefined;
      while (!this.interrupted && (content = this.getNextPending()) !== undefined) {
        result = yield* this.processOne(content);
      }
      this.onComplete();
      this.resolveResult(result!);
      return result!;
    } catch (err) {
      this.onComplete();
      this.rejectResult(err as Error);
      throw err;
    }
  }

  private async *processOne(content: string | ContentPart[]): AsyncGenerator<StreamEvent, RunResult, undefined> {
    const client = await this.getClient();
    const stream = client.sendPrompt(content);
    for await (const event of stream.events) {
      yield event;
    }
    return await stream.result;
  }

  async interrupt(): Promise<void> {
    this.interrupted = true;
    this.clearPending();
    const client = this.getCurrentClient();
    if (client?.isRunning) {
      return client.sendCancel();
    }
  }

  async approve(requestId: string, response: ApprovalResponse): Promise<void> {
    const client = this.getCurrentClient();
    if (!client?.isRunning) {
      throw new SessionError("SESSION_CLOSED", "Cannot approve: no active client");
    }
    return client.sendApproval(requestId, response);
  }
}

class SessionImpl implements Session {
  private readonly _sessionId: string;
  private readonly _workDir: string;
  private _model: string | undefined;
  private _thinking: boolean;
  private _yoloMode: boolean;
  private _executable: string;
  private _env: Record<string, string>;
  private _state: SessionState = "idle";

  private client: ProtocolClient | null = null;
  private activeConfig: ActiveConfig | null = null;
  private currentTurn: TurnImpl | null = null;
  private pendingMessages: (string | ContentPart[])[] = [];

  constructor(options: SessionOptions) {
    this._sessionId = options.sessionId ?? crypto.randomUUID();
    this._workDir = options.workDir;
    this._model = options.model;
    this._thinking = options.thinking ?? false;
    this._yoloMode = options.yoloMode ?? false;
    this._executable = options.executable ?? "kimi";
    this._env = options.env ?? {};
  }

  get sessionId(): string {
    return this._sessionId;
  }
  get workDir(): string {
    return this._workDir;
  }
  get state(): SessionState {
    return this._state;
  }
  get model(): string | undefined {
    return this._model;
  }
  set model(v: string | undefined) {
    this._model = v;
  }
  get thinking(): boolean {
    return this._thinking;
  }
  set thinking(v: boolean) {
    this._thinking = v;
  }
  get yoloMode(): boolean {
    return this._yoloMode;
  }
  set yoloMode(v: boolean) {
    this._yoloMode = v;
  }
  get executable(): string {
    return this._executable;
  }
  set executable(v: string) {
    this._executable = v;
  }
  get env(): Record<string, string> {
    return this._env;
  }
  set env(v: Record<string, string>) {
    this._env = v;
  }

  prompt(content: string | ContentPart[]): Turn {
    if (this._state === "closed") {
      throw new SessionError("SESSION_CLOSED", "Session is closed");
    }

    this.pendingMessages.push(content);

    if (this._state === "active" && this.currentTurn) {
      return this.currentTurn;
    }

    this._state = "active";
    this.currentTurn = new TurnImpl(
      () => this.getClientWithConfigCheck(),
      () => this.client,
      () => this.pendingMessages.shift(),
      () => {
        this.pendingMessages = [];
      },
      () => {
        if (this._state === "active") {
          this._state = "idle";
        }
        this.currentTurn = null;
      },
    );

    return this.currentTurn;
  }

  async close(): Promise<void> {
    if (this._state === "closed") {
      return;
    }
    this._state = "closed";
    this.currentTurn = null;
    this.pendingMessages = [];

    if (this.client) {
      try {
        await this.client.stop();
      } catch (err) {
        console.warn("[session] Error during close:", err);
      }
      this.client = null;
      this.activeConfig = null;
    }
  }

  [Symbol.asyncDispose](): Promise<void> {
    return this.close();
  }

  private async getClientWithConfigCheck(): Promise<ProtocolClient> {
    const currentConfig = this.snapshotConfig();

    if (this.client?.isRunning && this.activeConfig && !this.configChanged(currentConfig)) {
      return this.client;
    }

    // Config changed or no client, restart
    if (this.client) {
      await this.client.stop();
      this.client = null;
    }

    this.client = new ProtocolClient();
    this.client.start({
      sessionId: this._sessionId,
      workDir: this._workDir,
      model: this._model,
      thinking: this._thinking,
      yoloMode: this._yoloMode,
      executablePath: this._executable,
      environmentVariables: this._env,
    });
    this.activeConfig = currentConfig;

    return this.client;
  }

  private snapshotConfig(): ActiveConfig {
    return {
      model: this._model,
      thinking: this._thinking,
      yoloMode: this._yoloMode,
      executable: this._executable,
      env: JSON.stringify(this._env),
    };
  }

  private configChanged(current: ActiveConfig): boolean {
    const active = this.activeConfig!;
    return (
      current.model !== active.model ||
      current.thinking !== active.thinking ||
      current.yoloMode !== active.yoloMode ||
      current.executable !== active.executable ||
      current.env !== active.env
    );
  }
}

/** Start New Session */
export function createSession(options: SessionOptions): Session {
  return new SessionImpl(options);
}

/** One-time run: create session, send message, collect all events, and automatically close session after returning result */
export async function prompt(content: string | ContentPart[], options: Omit<SessionOptions, "sessionId">): Promise<{ result: RunResult; events: StreamEvent[] }> {
  const session = createSession(options);
  try {
    const turn = session.prompt(content);
    const events: StreamEvent[] = [];
    for await (const event of turn) {
      events.push(event);
    }
    return { result: await turn.result, events };
  } finally {
    await session.close();
  }
}
