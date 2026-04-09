"""Pydantic schemas for Jira API responses."""

from datetime import datetime
from typing import Optional, List, Any

from pydantic import BaseModel, Field, field_validator


# === User / Author schemas ===

class JiraUserSchema(BaseModel):
    """Jira user from API response."""
    
    accountId: str
    displayName: str
    emailAddress: Optional[str] = None
    avatarUrls: Optional[dict] = None
    active: bool = True
    
    @property
    def avatar_48(self) -> Optional[str]:
        """Get 48x48 avatar URL."""
        if self.avatarUrls:
            return self.avatarUrls.get("48x48")
        return None


# === Project schemas ===

class JiraProjectSchema(BaseModel):
    """Jira project from API response."""
    
    id: str
    key: str
    name: str
    description: Optional[str] = None
    projectTypeKey: Optional[str] = None
    
    class Config:
        extra = "ignore"


# === Issue schemas ===

class JiraIssueTypeSchema(BaseModel):
    """Issue type (Task, Bug, Epic, etc.)."""
    
    id: str
    name: str
    subtask: bool = False


class JiraStatusSchema(BaseModel):
    """Issue status."""
    
    id: str
    name: str
    statusCategory: Optional[dict] = None


class JiraPrioritySchema(BaseModel):
    """Issue priority."""
    
    id: str
    name: str


class JiraIssueFieldsSchema(BaseModel):
    """Issue fields from API response."""
    
    summary: str
    description: Optional[Any] = None  # Can be string or ADF
    issuetype: JiraIssueTypeSchema
    status: JiraStatusSchema
    priority: Optional[JiraPrioritySchema] = None
    project: JiraProjectSchema
    parent: Optional[dict] = None
    creator: Optional[JiraUserSchema] = None
    assignee: Optional[JiraUserSchema] = None
    created: Optional[str] = None
    updated: Optional[str] = None
    
    @property
    def parent_key(self) -> Optional[str]:
        """Get parent issue key if exists."""
        if self.parent:
            return self.parent.get("key")
        return None
    
    @property
    def description_text(self) -> Optional[str]:
        """Extract plain text from description (handles ADF format)."""
        if self.description is None:
            return None
        if isinstance(self.description, str):
            return self.description
        # ADF format - extract text content
        if isinstance(self.description, dict):
            return self._extract_adf_text(self.description)
        return str(self.description)
    
    def _extract_adf_text(self, node: dict) -> str:
        """Recursively extract text from Atlassian Document Format."""
        text_parts = []
        if node.get("type") == "text":
            text_parts.append(node.get("text", ""))
        for child in node.get("content", []):
            if isinstance(child, dict):
                text_parts.append(self._extract_adf_text(child))
        return " ".join(text_parts).strip()
    
    class Config:
        extra = "ignore"


class JiraIssueSchema(BaseModel):
    """Jira issue from API response."""
    
    id: str
    key: str
    fields: JiraIssueFieldsSchema
    
    class Config:
        extra = "ignore"


# === Worklog schemas ===

class JiraWorklogAuthorSchema(BaseModel):
    """Worklog author."""
    
    accountId: str
    displayName: str
    emailAddress: Optional[str] = None


class JiraWorklogSchema(BaseModel):
    """Jira worklog from API response."""
    
    id: str
    issueId: str
    author: JiraWorklogAuthorSchema
    started: str  # ISO datetime string
    timeSpentSeconds: int
    comment: Optional[Any] = None  # Can be string or ADF
    created: Optional[str] = None
    updated: Optional[str] = None
    
    @property
    def hours(self) -> float:
        """Convert seconds to hours."""
        return self.timeSpentSeconds / 3600
    
    @property
    def started_datetime(self) -> datetime:
        """Parse started timestamp."""
        # Jira format: "2024-01-15T10:30:00.000+0300"
        started_str = self.started.replace("+0000", "+00:00")
        if "." in started_str:
            # Handle milliseconds
            base, tz = started_str.rsplit("+", 1) if "+" in started_str else (started_str.rsplit("-", 1))
            if "." in base:
                base = base.split(".")[0]
            started_str = f"{base}+{tz}" if "+" in self.started else f"{base}-{tz}"
        return datetime.fromisoformat(started_str.replace("Z", "+00:00"))
    
    @property
    def comment_text(self) -> Optional[str]:
        """Extract plain text from comment."""
        if self.comment is None:
            return None
        if isinstance(self.comment, str):
            return self.comment
        if isinstance(self.comment, dict):
            # ADF format
            return self._extract_adf_text(self.comment)
        return str(self.comment)
    
    def _extract_adf_text(self, node: dict) -> str:
        """Recursively extract text from ADF."""
        text_parts = []
        if node.get("type") == "text":
            text_parts.append(node.get("text", ""))
        for child in node.get("content", []):
            if isinstance(child, dict):
                text_parts.append(self._extract_adf_text(child))
        return " ".join(text_parts).strip()
    
    class Config:
        extra = "ignore"


# === Comment schemas ===

class JiraCommentAuthorSchema(BaseModel):
    """Comment author."""

    accountId: str
    displayName: str
    emailAddress: Optional[str] = None


class JiraCommentSchema(BaseModel):
    """Jira comment from API response."""

    id: str
    author: JiraCommentAuthorSchema
    body: Optional[Any] = None  # Can be string or ADF
    created: Optional[str] = None
    updated: Optional[str] = None

    @property
    def body_text(self) -> Optional[str]:
        """Extract plain text from comment body."""
        if self.body is None:
            return None
        if isinstance(self.body, str):
            return self.body
        if isinstance(self.body, dict):
            return self._extract_adf_text(self.body)
        return str(self.body)

    @property
    def created_datetime(self) -> Optional[datetime]:
        """Parse created timestamp."""
        if not self.created:
            return None
        created_str = self.created.replace("+0000", "+00:00")
        if "." in created_str:
            base, tz = created_str.rsplit("+", 1) if "+" in created_str else (created_str.rsplit("-", 1))
            if "." in base:
                base = base.split(".")[0]
            created_str = f"{base}+{tz}" if "+" in self.created else f"{base}-{tz}"
        return datetime.fromisoformat(created_str.replace("Z", "+00:00"))

    def _extract_adf_text(self, node: dict) -> str:
        """Recursively extract text from ADF."""
        text_parts = []
        if node.get("type") == "text":
            text_parts.append(node.get("text", ""))
        for child in node.get("content", []):
            if isinstance(child, dict):
                text_parts.append(self._extract_adf_text(child))
        return " ".join(text_parts).strip()

    class Config:
        extra = "ignore"


class JiraCommentsResponseSchema(BaseModel):
    """Paginated comments response."""

    startAt: int = 0
    maxResults: int = 50
    total: int = 0
    comments: List[JiraCommentSchema] = Field(default_factory=list)

    @property
    def has_more(self) -> bool:
        return self.startAt + len(self.comments) < self.total


# === Paginated response schemas ===

class JiraSearchResponseSchema(BaseModel):
    """Paginated search response for issues."""
    
    startAt: int = 0
    maxResults: int = 50
    total: int = 0
    issues: List[JiraIssueSchema] = Field(default_factory=list)
    
    @property
    def has_more(self) -> bool:
        """Check if there are more results."""
        return self.startAt + len(self.issues) < self.total


class JiraWorklogsResponseSchema(BaseModel):
    """Paginated worklog response."""
    
    startAt: int = 0
    maxResults: int = 100
    total: int = 0
    worklogs: List[JiraWorklogSchema] = Field(default_factory=list)
    
    @property
    def has_more(self) -> bool:
        return self.startAt + len(self.worklogs) < self.total


class JiraProjectsResponseSchema(BaseModel):
    """Paginated projects response."""
    
    startAt: int = 0
    maxResults: int = 50
    total: int = 0
    values: List[JiraProjectSchema] = Field(default_factory=list)
    
    @property
    def has_more(self) -> bool:
        return self.startAt + len(self.values) < self.total
