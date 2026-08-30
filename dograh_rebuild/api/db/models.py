from sqlalchemy import Column, ForeignKey, Integer, String,DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class ServiceKey(Base):
    __tablename__ = "service_keys"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String, nullable=False)
    key_hash = Column(String, nullable=False, unique=True)
    key_prefix = Column(String, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String, nullable=False)
    system_prompt = Column(String, nullable=False)
    voice = Column(String, nullable=False)


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)

class WorkflowNode(Base):
    __tablename__ = "workflow_nodes"

    id = Column(Integer, primary_key=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    node_key = Column(String, nullable=False)
    node_type = Column(String, nullable=False)
    label = Column(String, nullable=False)


class WorkflowEdge(Base):
    __tablename__ = "workflow_edges"

    id = Column(Integer, primary_key=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    source_node_key = Column(String, nullable=False)
    target_node_key = Column(String, nullable=False)
