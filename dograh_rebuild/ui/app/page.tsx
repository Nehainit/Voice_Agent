"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type Agent = {
  id: number;
  organization_id: number;
  name: string;
  system_prompt: string;
  voice: string;
};

type Workflow = {
  id: number;
  organization_id: number;
  agent_id: number | null;
  name: string;
  description: string;
};

type WorkflowNode = {
  id: number;
  workflow_id: number;
  node_key: string;
  node_type: string;
  label: string;
};

type WorkflowEdge = {
  id: number;
  workflow_id: number;
  source_node_key: string;
  target_node_key: string;
};

type WorkflowGraph = {
  workflow: Workflow;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
};

type Section = "overview" | "agents" | "workflows" | "builder" | "voice" | "telephony";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";

const navSections: { label: string; items: { key: Section; label: string; icon: string }[] }[] = [
  { label: "OPERATE", items: [{ key: "overview", label: "Overview", icon: "O" }] },
  {
    label: "BUILD",
    items: [
      { key: "agents", label: "Voice Agents", icon: "A" },
      { key: "workflows", label: "Workflows", icon: "W" },
      { key: "builder", label: "Graph Builder", icon: "G" },
      { key: "voice", label: "Voice Test", icon: "V" },
      { key: "telephony", label: "Telephony", icon: "T" },
    ],
  },
];

function readStored(key: string, fallback: string) {
  if (typeof window === "undefined") return fallback;
  return window.localStorage.getItem(key) || fallback;
}

export default function Home() {
  const [activeSection, setActiveSection] = useState<Section>("overview");
  const [apiKey, setApiKey] = useState("");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [graph, setGraph] = useState<WorkflowGraph | null>(null);
  const [providers, setProviders] = useState<string[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<number | null>(null);
  const [message, setMessage] = useState("Paste an API key, then load workspace data.");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [agentName, setAgentName] = useState("Inbound sales agent");
  const [agentVoice, setAgentVoice] = useState("alloy");
  const [systemPrompt, setSystemPrompt] = useState("You are a concise voice agent. Qualify the caller and route them through the workflow.");
  const [workflowName, setWorkflowName] = useState("Lead Qualification");
  const [workflowDescription, setWorkflowDescription] = useState("Ask questions and qualify inbound leads");
  const [workflowAgentId, setWorkflowAgentId] = useState("");
  const [nodeKey, setNodeKey] = useState("start");
  const [nodeType, setNodeType] = useState("start");
  const [nodeLabel, setNodeLabel] = useState("Start call");
  const [edgeSource, setEdgeSource] = useState("start");
  const [edgeTarget, setEdgeTarget] = useState("");
  const [testText, setTestText] = useState("What is the price?");
  const [testResult, setTestResult] = useState("");
  const [voiceFileName, setVoiceFileName] = useState("");
  const [voiceContentType, setVoiceContentType] = useState("");
  const [voiceBase64, setVoiceBase64] = useState("");

  const selectedWorkflow = workflows.find((workflow) => workflow.id === selectedWorkflowId) || null;
  const selectedAgent = agents.find((agent) => agent.id === selectedWorkflow?.agent_id) || null;
  const hasApiKey = apiKey.trim().length > 0;

  const headers = useMemo(() => {
    const result: Record<string, string> = { "Content-Type": "application/json" };
    if (hasApiKey) result["X-API-Key"] = apiKey.trim();
    return result;
  }, [apiKey, hasApiKey]);

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        ...headers,
        ...(options.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `Request failed with ${response.status}`);
    }
    return data as T;
  }

  async function refreshWorkspace() {
    if (!hasApiKey) {
      setError("X-API-Key is required for workspace data.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [nextAgents, nextWorkflows, nextProviders] = await Promise.all([
        request<Agent[]>("/agents"),
        request<Workflow[]>("/workflows"),
        request<string[]>("/telephony/providers", { headers: {} }),
      ]);
      setAgents(nextAgents);
      setWorkflows(nextWorkflows);
      setProviders(nextProviders);
      const nextWorkflowId = selectedWorkflowId || nextWorkflows[0]?.id || null;
      setSelectedWorkflowId(nextWorkflowId);
      if (nextWorkflowId) await loadGraph(nextWorkflowId);
      setMessage("Workspace loaded from backend.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load workspace.");
    } finally {
      setLoading(false);
    }
  }

  async function loadGraph(workflowId: number) {
    const nextGraph = await request<WorkflowGraph>(`/workflows/${workflowId}/graph`);
    setGraph(nextGraph);
  }

  async function createAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const agent = await request<Agent>("/agents", {
        method: "POST",
        body: JSON.stringify({ name: agentName, system_prompt: systemPrompt, voice: agentVoice }),
      });
      setAgents((current) => [...current, agent]);
      setWorkflowAgentId(String(agent.id));
      setMessage(`Agent created: ${agent.name}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create agent.");
    } finally {
      setLoading(false);
    }
  }

  async function createWorkflow(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const agentId = Number(workflowAgentId || agents[0]?.id);
    if (!agentId) {
      setError("Create an agent before creating a workflow.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const workflow = await request<Workflow>("/workflows", {
        method: "POST",
        body: JSON.stringify({ agent_id: agentId, name: workflowName, description: workflowDescription }),
      });
      setWorkflows((current) => [...current, workflow]);
      setSelectedWorkflowId(workflow.id);
      await loadGraph(workflow.id);
      setActiveSection("builder");
      setMessage(`Workflow created: ${workflow.name}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create workflow.");
    } finally {
      setLoading(false);
    }
  }

  async function createNode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkflowId) return;
    setLoading(true);
    setError("");
    try {
      await request<WorkflowNode>(`/workflows/${selectedWorkflowId}/nodes`, {
        method: "POST",
        body: JSON.stringify({ node_key: nodeKey, node_type: nodeType, label: nodeLabel }),
      });
      await loadGraph(selectedWorkflowId);
      setEdgeTarget(nodeKey);
      setNodeKey("");
      setNodeLabel("");
      setMessage("Node added to workflow graph.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create node.");
    } finally {
      setLoading(false);
    }
  }

  async function createEdge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorkflowId) return;
    setLoading(true);
    setError("");
    try {
      await request<WorkflowEdge>(`/workflows/${selectedWorkflowId}/edges`, {
        method: "POST",
        body: JSON.stringify({ source_node_key: edgeSource, target_node_key: edgeTarget }),
      });
      await loadGraph(selectedWorkflowId);
      setMessage("Edge added to workflow graph.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create edge.");
    } finally {
      setLoading(false);
    }
  }

  async function runTextTest(kind: "test-turn" | "llm-test-turn") {
    if (!selectedWorkflowId) return;
    setLoading(true);
    setError("");
    try {
      const result = await request<Record<string, unknown>>(`/workflows/${selectedWorkflowId}/${kind}`, {
        method: "POST",
        body: JSON.stringify({ user_text: testText }),
      });
      setTestResult(JSON.stringify(result, null, 2));
      setMessage(kind === "llm-test-turn" ? "LLM test completed." : "Stored workflow test completed.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not run test.");
    } finally {
      setLoading(false);
    }
  }

  async function runVoiceTest() {
    if (!selectedWorkflowId || !voiceBase64) return;
    setLoading(true);
    setError("");
    try {
      const result = await request<Record<string, unknown>>(`/workflows/${selectedWorkflowId}/voice-test-turn`, {
        method: "POST",
        body: JSON.stringify({
          filename: voiceFileName,
          content_type: voiceContentType,
          audio_base64: voiceBase64,
        }),
      });
      setTestResult(JSON.stringify(result, null, 2));
      setMessage("Voice test completed.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not run voice test.");
    } finally {
      setLoading(false);
    }
  }

  async function handleAudioFile(file: File | null) {
    if (!file) return;
    setVoiceFileName(file.name);
    setVoiceContentType(file.type || "application/octet-stream");
    const buffer = await file.arrayBuffer();
    let binary = "";
    for (const byte of new Uint8Array(buffer)) binary += String.fromCharCode(byte);
    setVoiceBase64(window.btoa(binary));
  }

  useEffect(() => {
    setApiKey(readStored("dograh.apiKey", ""));
  }, []);

  useEffect(() => {
    if (apiKey) window.localStorage.setItem("dograh.apiKey", apiKey);
  }, [apiKey]);

  useEffect(() => {
    if (!workflowAgentId && agents[0]) setWorkflowAgentId(String(agents[0].id));
  }, [agents, workflowAgentId]);

  useEffect(() => {
    if (selectedWorkflowId && hasApiKey) {
      loadGraph(selectedWorkflowId).catch((caught) => {
        setError(caught instanceof Error ? caught.message : "Could not load graph.");
      });
    }
  }, [selectedWorkflowId, hasApiKey]);

  return (
    <main className="dashboard">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">D</div>
          <div>
            <p className="brand-title">Dograh</p>
            <p className="brand-subtitle">Voice agent platform</p>
          </div>
        </div>

        {navSections.map((section) => (
          <div key={section.label}>
            <div className="nav-label">{section.label}</div>
            {section.items.map((item) => (
              <button
                className={`nav-button ${activeSection === item.key ? "active" : ""}`}
                key={item.key}
                onClick={() => setActiveSection(item.key)}
                type="button"
              >
                <span className="nav-icon">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </div>
        ))}

        <div className="sidebar-note">
          Requests use API-key tenant isolation. The organization id stays server-side.
        </div>
      </aside>

      <section className="main">
        <header className="topbar">
          <div>
            <h1 className="page-title">Voice agent workspace</h1>
            <p className="page-subtitle">Agents, workflows, graph runtime, and provider tests.</p>
          </div>
          <div className="topbar-controls">
            <input
              className="input"
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="X-API-Key"
              type="password"
              value={apiKey}
            />
            <button className="btn btn-primary" disabled={loading} onClick={refreshWorkspace} type="button">
              {loading ? "Working" : "Load"}
            </button>
          </div>
        </header>

        <div className="content">
          {(message || error) && <div className={`toast ${error ? "error" : ""}`}>{error || message}</div>}

          {activeSection === "overview" && (
            <>
              <div className="grid-3">
                <div className="stat"><p className="stat-value">{agents.length}</p><p className="stat-label">Agents</p></div>
                <div className="stat"><p className="stat-value">{workflows.length}</p><p className="stat-label">Workflows</p></div>
                <div className="stat"><p className="stat-value">{graph?.nodes.length || 0}</p><p className="stat-label">Selected graph nodes</p></div>
              </div>
              <div className="grid-2">
                <WorkspaceList title="Recent workflows" workflows={workflows} selectedWorkflowId={selectedWorkflowId} onSelect={setSelectedWorkflowId} />
                <div className="panel">
                  <div className="panel-header"><div><h2 className="panel-title">Selected agent</h2><p className="panel-kicker">Runtime personality</p></div></div>
                  <div className="panel-body">
                    {selectedAgent ? <AgentCard agent={selectedAgent} /> : <div className="empty">No workflow agent selected.</div>}
                  </div>
                </div>
              </div>
            </>
          )}

          {activeSection === "agents" && (
            <div className="grid-2">
              <div className="panel">
                <div className="panel-header"><div><h2 className="panel-title">Agents</h2><p className="panel-kicker">Behavior and voice configuration</p></div></div>
                <div className="panel-body list">{agents.length ? agents.map((agent) => <AgentCard agent={agent} key={agent.id} />) : <div className="empty">No agents yet.</div>}</div>
              </div>
              <div className="panel">
                <div className="panel-header"><div><h2 className="panel-title">Create agent</h2><p className="panel-kicker">Stored on backend</p></div></div>
                <form className="panel-body form-grid" onSubmit={createAgent}>
                  <label className="field"><span className="label">Name</span><input className="input" value={agentName} onChange={(event) => setAgentName(event.target.value)} /></label>
                  <label className="field"><span className="label">Voice</span><input className="input" value={agentVoice} onChange={(event) => setAgentVoice(event.target.value)} /></label>
                  <label className="field"><span className="label">System prompt</span><textarea className="textarea" value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} /></label>
                  <button className="btn btn-primary" disabled={!hasApiKey || loading} type="submit">Create agent</button>
                </form>
              </div>
            </div>
          )}

          {activeSection === "workflows" && (
            <div className="grid-2">
              <WorkspaceList title="Workflows" workflows={workflows} selectedWorkflowId={selectedWorkflowId} onSelect={setSelectedWorkflowId} />
              <div className="panel">
                <div className="panel-header"><div><h2 className="panel-title">Create workflow</h2><p className="panel-kicker">Attach it to an agent</p></div></div>
                <form className="panel-body form-grid" onSubmit={createWorkflow}>
                  <label className="field"><span className="label">Agent</span><select className="select" value={workflowAgentId} onChange={(event) => setWorkflowAgentId(event.target.value)}>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label>
                  <label className="field"><span className="label">Name</span><input className="input" value={workflowName} onChange={(event) => setWorkflowName(event.target.value)} /></label>
                  <label className="field"><span className="label">Description</span><textarea className="textarea" value={workflowDescription} onChange={(event) => setWorkflowDescription(event.target.value)} /></label>
                  <button className="btn btn-primary" disabled={!hasApiKey || loading || agents.length === 0} type="submit">Create workflow</button>
                </form>
              </div>
            </div>
          )}

          {activeSection === "builder" && (
            <div className="grid-2">
              <div className="panel">
                <div className="panel-header">
                  <div><h2 className="panel-title">Graph builder</h2><p className="panel-kicker">{selectedWorkflow?.name || "Select a workflow"}</p></div>
                  <select className="select" style={{ maxWidth: 260 }} value={selectedWorkflowId || ""} onChange={(event) => setSelectedWorkflowId(Number(event.target.value))}>
                    {workflows.map((workflow) => <option key={workflow.id} value={workflow.id}>{workflow.name}</option>)}
                  </select>
                </div>
                <div className="panel-body">
                  <div className="canvas">
                    {graph?.nodes.length ? (
                      <div className="node-stack">
                        {graph.nodes.map((node) => <NodeCard key={node.id} node={node} />)}
                      </div>
                    ) : <div className="empty">No nodes yet. Add a start node first.</div>}
                  </div>
                </div>
              </div>
              <div className="panel">
                <div className="panel-header"><div><h2 className="panel-title">Edit graph</h2><p className="panel-kicker">Nodes and edges are reusable building blocks</p></div></div>
                <div className="panel-body">
                  <form className="form-grid" onSubmit={createNode}>
                    <div className="form-row">
                      <label className="field"><span className="label">Node key</span><input className="input" value={nodeKey} onChange={(event) => setNodeKey(event.target.value)} placeholder="ask_price" /></label>
                      <label className="field"><span className="label">Type</span><select className="select" value={nodeType} onChange={(event) => setNodeType(event.target.value)}><option value="start">start</option><option value="message">message</option><option value="decision">decision</option><option value="tool">tool</option><option value="end">end</option></select></label>
                    </div>
                    <label className="field"><span className="label">Label</span><textarea className="textarea" value={nodeLabel} onChange={(event) => setNodeLabel(event.target.value)} placeholder="Ask the caller what they need" /></label>
                    <button className="btn btn-secondary" disabled={!selectedWorkflowId || loading} type="submit">Add node</button>
                  </form>

                  <form className="form-grid" onSubmit={createEdge}>
                    <div className="form-row">
                      <label className="field"><span className="label">From</span><input className="input" value={edgeSource} onChange={(event) => setEdgeSource(event.target.value)} placeholder="start" /></label>
                      <label className="field"><span className="label">To</span><input className="input" value={edgeTarget} onChange={(event) => setEdgeTarget(event.target.value)} placeholder="ask_price" /></label>
                    </div>
                    <button className="btn btn-secondary" disabled={!selectedWorkflowId || loading} type="submit">Add edge</button>
                  </form>

                  <div className="meta-row">{graph?.edges.map((edge) => <span className="badge" key={edge.id}>{edge.source_node_key} to {edge.target_node_key}</span>)}</div>
                </div>
              </div>
            </div>
          )}

          {activeSection === "voice" && (
            <div className="grid-2">
              <div className="panel">
                <div className="panel-header"><div><h2 className="panel-title">Runtime test</h2><p className="panel-kicker">Stored graph, LLM, STT, and TTS</p></div></div>
                <div className="panel-body form-grid">
                  <label className="field"><span className="label">Workflow</span><select className="select" value={selectedWorkflowId || ""} onChange={(event) => setSelectedWorkflowId(Number(event.target.value))}>{workflows.map((workflow) => <option key={workflow.id} value={workflow.id}>{workflow.name}</option>)}</select></label>
                  <label className="field"><span className="label">Caller text</span><textarea className="textarea" value={testText} onChange={(event) => setTestText(event.target.value)} /></label>
                  <div className="button-row">
                    <button className="btn btn-secondary" disabled={!selectedWorkflowId || loading} onClick={() => runTextTest("test-turn")} type="button">Stored test</button>
                    <button className="btn btn-warn" disabled={!selectedWorkflowId || loading} onClick={() => runTextTest("llm-test-turn")} type="button">LLM test</button>
                  </div>
                  <label className="field"><span className="label">Audio file for STT/TTS test</span><input className="input" type="file" accept="audio/*" onChange={(event) => handleAudioFile(event.target.files?.[0] || null)} /></label>
                  <button className="btn btn-primary" disabled={!selectedWorkflowId || !voiceBase64 || loading} onClick={runVoiceTest} type="button">Run voice test</button>
                </div>
              </div>
              <div className="panel">
                <div className="panel-header"><div><h2 className="panel-title">Response</h2><p className="panel-kicker">Raw runtime payload</p></div></div>
                <div className="panel-body"><pre className="response-box">{testResult || "No test result yet."}</pre></div>
              </div>
            </div>
          )}

          {activeSection === "telephony" && (
            <div className="panel">
              <div className="panel-header"><div><h2 className="panel-title">Telephony providers</h2><p className="panel-kicker">Inbound and outbound call rails</p></div></div>
              <div className="panel-body list">
                {(providers.length ? providers : ["twilio", "vonage", "telnyx"]).map((provider) => (
                  <div className="item" key={provider}>
                    <p className="item-title">{provider}</p>
                    <p className="item-copy">Provider configuration will own phone numbers, webhooks, and call routing.</p>
                    <div className="meta-row"><span className="badge badge-ok">available</span><span className="badge">webhook pending</span></div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

function AgentCard({ agent }: { agent: Agent }) {
  return (
    <div className="item">
      <p className="item-title">{agent.name}</p>
      <p className="item-copy">{agent.system_prompt}</p>
      <div className="meta-row"><span className="badge">voice {agent.voice}</span><span className="badge">org {agent.organization_id}</span></div>
    </div>
  );
}

function WorkspaceList({
  title,
  workflows,
  selectedWorkflowId,
  onSelect,
}: {
  title: string;
  workflows: Workflow[];
  selectedWorkflowId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <div className="panel">
      <div className="panel-header"><div><h2 className="panel-title">{title}</h2><p className="panel-kicker">Tenant-scoped results only</p></div></div>
      <div className="panel-body list">
        {workflows.length ? workflows.map((workflow) => (
          <button className={`item ${selectedWorkflowId === workflow.id ? "selected" : ""}`} key={workflow.id} onClick={() => onSelect(workflow.id)} type="button">
            <p className="item-title">{workflow.name}</p>
            <p className="item-copy">{workflow.description}</p>
            <div className="meta-row"><span className="badge">workflow {workflow.id}</span><span className="badge">agent {workflow.agent_id || "none"}</span></div>
          </button>
        )) : <div className="empty">No workflows loaded.</div>}
      </div>
    </div>
  );
}

function NodeCard({ node }: { node: WorkflowNode }) {
  return (
    <div className="node-card">
      <div className="node-type">{node.node_type}</div>
      <p className="item-title">{node.node_key}</p>
      <p className="item-copy">{node.label}</p>
    </div>
  );
}
