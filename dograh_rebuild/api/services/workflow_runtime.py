def run_workflow_text_turn(agent, workflow, nodes, edges, user_text: str):
    start_node = next((node for node in nodes if node.node_type == "start"), None)
    current_node = start_node or (nodes[0] if nodes else None)

    next_node = None
    if current_node is not None:
        next_edge = next(
            (edge for edge in edges if edge.source_node_key == current_node.node_key),
            None,
        )
        if next_edge is not None:
            next_node = next(
                (node for node in nodes if node.node_key == next_edge.target_node_key),
                None,
            )

    target = next_node or current_node
    if target is None:
        response_text = f"{agent.name}: {workflow.description}"
    else:
        response_text = f"{agent.name}: {target.label}"

    return {
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "system_prompt": agent.system_prompt,
            "voice": agent.voice,
        },
        "workflow": {
            "id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
        },
        "user_text": user_text,
        "current_node_key": current_node.node_key if current_node else None,
        "next_node_key": next_node.node_key if next_node else None,
        "response_text": response_text,
    }


def summarize_workflow_graph(nodes, edges):
    node_lines = [
        f"node {node.node_key}: type={node.node_type}, label={node.label}"
        for node in nodes
    ]
    edge_lines = [
        f"edge {edge.source_node_key} -> {edge.target_node_key}"
        for edge in edges
    ]
    return "\n".join(node_lines + edge_lines) or "No workflow graph is configured."
