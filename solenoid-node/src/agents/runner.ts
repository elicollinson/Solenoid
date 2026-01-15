import type { Agent, AgentContext, AgentRequest, AgentStreamChunk } from './types.js';

interface Session {
  id: string;
  state: Record<string, unknown>;
  messages: Array<{ role: string; content: string }>;
}

export class AgentRunner {
  private rootAgent: Agent;
  private sessions: Map<string, Session> = new Map();

  constructor(rootAgent: Agent) {
    this.rootAgent = rootAgent;
  }

  async *run(
    input: string,
    sessionId?: string
  ): AsyncGenerator<AgentStreamChunk, void, unknown> {
    const session = this.getOrCreateSession(sessionId);

    session.messages.push({ role: 'user', content: input });

    const context: AgentContext = {
      sessionId: session.id,
      state: session.state,
    };

    const request: AgentRequest = {
      messages: session.messages.map((m) => ({
        role: m.role as 'user' | 'assistant' | 'system',
        content: m.content,
      })),
      context,
    };

    let assistantContent = '';

    for await (const chunk of this.rootAgent.run(request)) {
      if (chunk.type === 'text' && chunk.content) {
        assistantContent += chunk.content;
      }
      yield chunk;
    }

    if (assistantContent) {
      session.messages.push({ role: 'assistant', content: assistantContent });
    }
  }

  private getOrCreateSession(sessionId?: string): Session {
    const id = sessionId ?? crypto.randomUUID();

    let session = this.sessions.get(id);
    if (!session) {
      session = {
        id,
        state: {},
        messages: [],
      };
      this.sessions.set(id, session);
    }

    return session;
  }

  getSession(sessionId: string): Session | undefined {
    return this.sessions.get(sessionId);
  }

  clearSession(sessionId: string): void {
    this.sessions.delete(sessionId);
  }
}
