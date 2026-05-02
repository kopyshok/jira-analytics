"""Schemas for GET /issues/{issue_id}/context endpoint."""

from typing import List, Optional

from pydantic import BaseModel


class IssueContextAncestor(BaseModel):
    id: str
    key: str
    summary: str
    issue_type: str


class IssueContextChild(BaseModel):
    id: str
    key: str
    summary: str
    status: str
    status_category: Optional[str] = None
    issue_type: str
    category: Optional[str] = None
    assigned_category: Optional[str] = None
    include_in_analysis: bool
    subtree_count: int


class IssueContextResponse(BaseModel):
    id: str
    key: str
    summary: str
    status: str
    status_category: Optional[str] = None
    issue_type: str
    category: Optional[str] = None
    assigned_category: Optional[str] = None
    include_in_analysis: bool
    is_container: bool
    ancestors: List[IssueContextAncestor]
    siblings_total: int
    children: List[IssueContextChild]
    subtree_count: int


class IssueChildNode(BaseModel):
    """Lightweight child node for GET /issues/{parent_id}/children."""
    id: str
    key: str
    summary: str
    status: str
    status_category: Optional[str] = None
    issue_type: str
    category: Optional[str] = None
    assigned_category: Optional[str] = None
    include_in_analysis: bool
