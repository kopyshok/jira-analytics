"""Tests for Jira schemas."""

import pytest
from datetime import datetime, timedelta, timezone

from app.connectors.schemas import (
    JiraCommentSchema,
    JiraUserSchema,
    JiraProjectSchema,
    JiraWorklogSchema,
    JiraIssueSchema,
    JiraIssueFieldsSchema,
    JiraIssueTypeSchema,
    JiraStatusSchema,
    JiraWorklogAuthorSchema,
)


class TestJiraUserSchema:
    """Tests for JiraUserSchema."""
    
    def test_basic_user(self):
        """Test parsing basic user data."""
        data = {
            "accountId": "abc123",
            "displayName": "John Doe",
            "emailAddress": "john@example.com",
            "active": True,
            "avatarUrls": {
                "48x48": "https://example.com/avatar.png"
            }
        }
        user = JiraUserSchema(**data)
        
        assert user.accountId == "abc123"
        assert user.displayName == "John Doe"
        assert user.emailAddress == "john@example.com"
        assert user.active is True
        assert user.avatar_48 == "https://example.com/avatar.png"
    
    def test_user_without_email(self):
        """Test user without email (common for service accounts)."""
        data = {
            "accountId": "abc123",
            "displayName": "Bot User",
            "active": True,
        }
        user = JiraUserSchema(**data)
        
        assert user.emailAddress is None
        assert user.avatar_48 is None


class TestJiraProjectSchema:
    """Tests for JiraProjectSchema."""
    
    def test_basic_project(self):
        """Test parsing project data."""
        data = {
            "id": "10001",
            "key": "PRJ",
            "name": "My Project",
            "description": "Project description",
            "projectTypeKey": "software"
        }
        project = JiraProjectSchema(**data)
        
        assert project.id == "10001"
        assert project.key == "PRJ"
        assert project.name == "My Project"
        assert project.projectTypeKey == "software"


class TestJiraWorklogSchema:
    """Tests for JiraWorklogSchema."""
    
    def test_worklog_hours_conversion(self):
        """Test that timeSpentSeconds converts to hours correctly."""
        data = {
            "id": "123",
            "issueId": "456",
            "author": {
                "accountId": "user1",
                "displayName": "John"
            },
            "started": "2024-01-15T10:00:00.000+0000",
            "timeSpentSeconds": 7200,  # 2 hours
        }
        worklog = JiraWorklogSchema(**data)
        
        assert worklog.hours == 2.0
        assert worklog.timeSpentSeconds == 7200
    
    def test_worklog_datetime_parsing(self):
        """Test datetime parsing from Jira format."""
        data = {
            "id": "123",
            "issueId": "456",
            "author": {
                "accountId": "user1",
                "displayName": "John"
            },
            "started": "2024-01-15T10:30:00.000+0000",
            "timeSpentSeconds": 3600,
        }
        worklog = JiraWorklogSchema(**data)

        dt = worklog.started_datetime
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30
        assert dt.utcoffset() == timedelta(0)

    def test_worklog_datetime_moscow_offset(self):
        """Регрессия: таймзона без двоеточия (+0300) должна парситься на Python 3.10."""
        data = {
            "id": "123",
            "issueId": "456",
            "author": {"accountId": "user1", "displayName": "John"},
            "started": "2024-01-15T10:30:00.000+0300",
            "timeSpentSeconds": 3600,
        }
        worklog = JiraWorklogSchema(**data)

        dt = worklog.started_datetime
        assert dt.hour == 10
        assert dt.minute == 30
        assert dt.utcoffset() == timedelta(hours=3)

    def test_worklog_datetime_negative_offset(self):
        """Отрицательная таймзона тоже должна парситься."""
        data = {
            "id": "123",
            "issueId": "456",
            "author": {"accountId": "user1", "displayName": "John"},
            "started": "2024-01-15T10:30:00.000-0500",
            "timeSpentSeconds": 3600,
        }
        worklog = JiraWorklogSchema(**data)

        dt = worklog.started_datetime
        assert dt.utcoffset() == timedelta(hours=-5)

    def test_worklog_datetime_zulu(self):
        """Формат с Z (UTC) должен парситься."""
        data = {
            "id": "123",
            "issueId": "456",
            "author": {"accountId": "user1", "displayName": "John"},
            "started": "2024-01-15T10:30:00Z",
            "timeSpentSeconds": 3600,
        }
        worklog = JiraWorklogSchema(**data)

        dt = worklog.started_datetime
        assert dt.utcoffset() == timedelta(0)
    
    def test_worklog_with_adf_comment(self):
        """Test extracting text from ADF format comment."""
        data = {
            "id": "123",
            "issueId": "456",
            "author": {
                "accountId": "user1",
                "displayName": "John"
            },
            "started": "2024-01-15T10:00:00.000+0000",
            "timeSpentSeconds": 3600,
            "comment": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Working on "}, 
                            {"type": "text", "text": "feature X"}
                        ]
                    }
                ]
            }
        }
        worklog = JiraWorklogSchema(**data)
        
        assert "Working on" in worklog.comment_text
        assert "feature X" in worklog.comment_text


class TestJiraCommentSchema:
    """Tests for JiraCommentSchema."""

    def test_comment_created_datetime_moscow_offset(self):
        data = {
            "id": "c1",
            "author": {"accountId": "u1", "displayName": "John"},
            "body": "hello",
            "created": "2024-01-15T10:30:00.000+0300",
        }
        comment = JiraCommentSchema(**data)

        dt = comment.created_datetime
        assert dt is not None
        assert dt.hour == 10
        assert dt.utcoffset() == timedelta(hours=3)

    def test_comment_created_none(self):
        data = {
            "id": "c1",
            "author": {"accountId": "u1", "displayName": "John"},
            "body": "hello",
        }
        comment = JiraCommentSchema(**data)
        assert comment.created_datetime is None


class TestJiraIssueSchema:
    """Tests for JiraIssueSchema."""
    
    def test_basic_issue(self):
        """Test parsing basic issue data."""
        data = {
            "id": "10001",
            "key": "PRJ-123",
            "fields": {
                "summary": "Test issue",
                "issuetype": {"id": "1", "name": "Task", "subtask": False},
                "status": {"id": "1", "name": "Open"},
                "project": {"id": "100", "key": "PRJ", "name": "Project"}
            }
        }
        issue = JiraIssueSchema(**data)
        
        assert issue.key == "PRJ-123"
        assert issue.fields.summary == "Test issue"
        assert issue.fields.issuetype.name == "Task"
        assert issue.fields.status.name == "Open"
    
    def test_issue_with_parent(self):
        """Test issue with parent (subtask)."""
        data = {
            "id": "10002",
            "key": "PRJ-124",
            "fields": {
                "summary": "Subtask",
                "issuetype": {"id": "2", "name": "Sub-task", "subtask": True},
                "status": {"id": "1", "name": "Open"},
                "project": {"id": "100", "key": "PRJ", "name": "Project"},
                "parent": {"key": "PRJ-123"}
            }
        }
        issue = JiraIssueSchema(**data)
        
        assert issue.fields.parent_key == "PRJ-123"
        assert issue.fields.issuetype.subtask is True
