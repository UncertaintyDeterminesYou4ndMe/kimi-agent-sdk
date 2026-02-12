#!/usr/bin/env python3
"""
Event-Driven GitHub Bot Agent

This example demonstrates how to build a reactive agent that:
1. Listens to GitHub webhooks (PR created, issue opened, etc.)
2. Maintains conversation state across interactions
3. Responds intelligently using Kimi

Usage:
    GITHUB_TOKEN=ghp_xxx python github_bot.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from kimi_agent_sdk import prompt
from kimi_agent_sdk.connectors import Event, EventBus, StateManager, FileStateBackend


@dataclass
class PRContext:
    """Context for a PR review session."""
    pr_id: str
    repo: str
    author: str
    title: str
    description: str
    files: list[str]
    review_comments: list[dict]
    status: str  # "pending", "reviewing", "approved", "changes_requested"


class GitHubBot:
    """Event-driven GitHub bot using Kimi Agent."""
    
    def __init__(self, github_token: str, state_dir: str = "./.bot_state") -> None:
        self.github_token = github_token
        self.bus = EventBus()
        self.state = StateManager(FileStateBackend(state_dir))
        self._setup_handlers()
    
    def _setup_handlers(self) -> None:
        """Set up event handlers for GitHub events."""
        
        @self.bus.on("github.pr.opened")
        async def on_pr_opened(event: Event) -> None:
            """Handle new PR opened."""
            pr_data = event.data
            pr_id = f"{pr_data['repo']}#{pr_data['number']}"
            
            print(f"📬 New PR opened: {pr_id}")
            
            # Store PR context
            context = PRContext(
                pr_id=pr_id,
                repo=pr_data["repo"],
                author=pr_data["author"],
                title=pr_data["title"],
                description=pr_data.get("description", ""),
                files=pr_data.get("files", []),
                review_comments=[],
                status="pending"
            )
            
            await self.state.set(f"pr:{pr_id}", context.__dict__)
            
            # Trigger review
            await self.bus.emit(Event(
                type="agent.pr.review_requested",
                data={"pr_id": pr_id, "priority": "normal"}
            ))
        
        @self.bus.on("github.pr.updated")
        async def on_pr_updated(event: Event) -> None:
            """Handle PR updated (new commits)."""
            pr_data = event.data
            pr_id = f"{pr_data['repo']}#{pr_data['number']}"
            
            print(f"📝 PR updated: {pr_id}")
            
            # Update context
            context_data = await self.state.get(f"pr:{pr_id}")
            if context_data:
                context_data["files"] = pr_data.get("files", [])
                context_data["status"] = "pending"  # Re-review needed
                await self.state.set(f"pr:{pr_id}", context_data)
                
                # Trigger re-review
                await self.bus.emit(Event(
                    type="agent.pr.review_requested",
                    data={"pr_id": pr_id, "priority": "high"}
                ))
        
        @self.bus.on("agent.pr.review_requested")
        async def review_pr(event: Event) -> None:
            """Agent reviews a PR."""
            pr_id = event.data["pr_id"]
            priority = event.data.get("priority", "normal")
            
            # Load context
            context_data = await self.state.get(f"pr:{pr_id}")
            if not context_data:
                print(f"⚠️  No context found for {pr_id}")
                return
            
            context = PRContext(**context_data)
            
            # Skip if already reviewed
            if context.status == "approved":
                print(f"⏭️  PR {pr_id} already approved, skipping")
                return
            
            # Mark as reviewing
            context.status = "reviewing"
            await self.state.set(f"pr:{pr_id}", context.__dict__)
            
            print(f"🔍 Reviewing PR {pr_id} (priority: {priority})")
            
            # Build review prompt
            review_prompt = f"""Review this Pull Request:

**Title:** {context.title}
**Author:** {context.author}
**Description:** {context.description}

**Files changed:** {', '.join(context.files)}

Please provide:
1. Summary of changes
2. Code quality assessment
3. Potential issues or bugs
4. Suggestions for improvement
5. Overall recommendation (approve/request changes)

Format your response as JSON:
{{
    "summary": "brief summary",
    "quality_score": 1-10,
    "issues": ["issue1", "issue2"],
    "suggestions": ["suggestion1"],
    "recommendation": "approve|request_changes|comment"
}}"""
            
            try:
                # Get review from Kimi
                review_text = ""
                async for message in prompt(review_prompt, yolo=True):
                    review_text += message.extract_text()
                
                # Parse review (simplified - in production use JSON parser)
                review_result = self._parse_review(review_text)
                
                # Store review
                context.review_comments.append({
                    "timestamp": datetime.now().isoformat(),
                    "review": review_result,
                    "raw": review_text[:500]  # Truncate for storage
                })
                
                # Update status based on recommendation
                if review_result.get("recommendation") == "approve":
                    context.status = "approved"
                    print(f"✅ Approved PR {pr_id}")
                else:
                    context.status = "changes_requested"
                    print(f"📝 Requested changes for PR {pr_id}")
                
                await self.state.set(f"pr:{pr_id}", context.__dict__)
                
                # Emit review complete event
                await self.bus.emit(Event(
                    type="agent.pr.review_complete",
                    data={
                        "pr_id": pr_id,
                        "recommendation": review_result.get("recommendation"),
                        "quality_score": review_result.get("quality_score")
                    }
                ))
                
            except Exception as e:
                print(f"❌ Error reviewing PR {pr_id}: {e}")
                context.status = "error"
                await self.state.set(f"pr:{pr_id}", context.__dict__)
        
        @self.bus.on("github.issue.opened")
        async def on_issue_opened(event: Event) -> None:
            """Handle new issue."""
            issue_data = event.data
            issue_id = f"{issue_data['repo']}#{issue_data['number']}"
            
            print(f"🐛 New issue opened: {issue_id}")
            
            # Analyze issue and suggest labels/assignees
            analysis_prompt = f"""Analyze this GitHub issue:

**Title:** {issue_data['title']}
**Description:** {issue_data.get('body', 'No description')}

Suggest:
1. Labels (bug, feature, documentation, etc.)
2. Priority (low, medium, high, critical)
3. Whether it needs immediate attention

Format as JSON."""
            
            try:
                analysis_text = ""
                async for message in prompt(analysis_prompt, yolo=True):
                    analysis_text += message.extract_text()
                
                print(f"📊 Analysis for {issue_id}:")
                print(f"   {analysis_text[:200]}...")
                
            except Exception as e:
                print(f"❌ Error analyzing issue {issue_id}: {e}")
    
    def _parse_review(self, text: str) -> dict[str, Any]:
        """Parse review text into structured format."""
        # Simplified parsing - in production use proper JSON extraction
        return {
            "summary": text[:200],
            "quality_score": 7,
            "issues": [],
            "suggestions": [],
            "recommendation": "comment"
        }
    
    async def handle_webhook(self, event_type: str, payload: dict) -> None:
        """Handle incoming webhook from GitHub."""
        # Map GitHub events to our event types
        if event_type == "pull_request":
            action = payload.get("action")
            pr_data = payload.get("pull_request", {})
            
            event_data = {
                "repo": payload.get("repository", {}).get("full_name"),
                "number": pr_data.get("number"),
                "author": pr_data.get("user", {}).get("login"),
                "title": pr_data.get("title"),
                "description": pr_data.get("body"),
                "files": [],  # Would need to fetch files separately
            }
            
            if action == "opened":
                await self.bus.emit(Event(type="github.pr.opened", data=event_data))
            elif action == "synchronize":  # New commits pushed
                await self.bus.emit(Event(type="github.pr.updated", data=event_data))
        
        elif event_type == "issues":
            action = payload.get("action")
            issue_data = payload.get("issue", {})
            
            if action == "opened":
                await self.bus.emit(Event(type="github.issue.opened", data={
                    "repo": payload.get("repository", {}).get("full_name"),
                    "number": issue_data.get("number"),
                    "title": issue_data.get("title"),
                    "body": issue_data.get("body"),
                }))
    
    def get_stats(self) -> dict[str, Any]:
        """Get bot statistics."""
        # Would be async in real implementation
        return {
            "events_processed": self.bus.handler_count(),
            "active_prs": "N/A (async needed)",
        }


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for GitHub webhooks."""
    
    bot: GitHubBot | None = None
    
    def do_POST(self) -> None:
        """Handle POST request (GitHub webhook)."""
        if self.path != "/webhook":
            self.send_error(404)
            return
        
        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        
        try:
            payload = json.loads(body)
            event_type = self.headers.get("X-GitHub-Event", "unknown")
            
            print(f"📥 Received {event_type} webhook")
            
            # Process asynchronously
            if self.bot:
                asyncio.create_task(self.bot.handle_webhook(event_type, payload))
            
            self.send_response(200)
            self.end_headers()
            
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
    
    def log_message(self, format: str, *args) -> None:
        """Suppress default logging."""
        pass


async def simulate_events(bot: GitHubBot) -> None:
    """Simulate GitHub events for testing without actual webhooks."""
    print("\n🎮 Simulating GitHub events...\n")
    
    # Simulate PR opened
    await bot.bus.emit(Event(type="github.pr.opened", data={
        "repo": "myorg/myproject",
        "number": 42,
        "author": "developer1",
        "title": "Add user authentication feature",
        "description": "This PR adds OAuth2 authentication...",
        "files": ["auth.py", "models.py", "tests/test_auth.py"]
    }))
    
    await asyncio.sleep(2)
    
    # Simulate issue opened
    await bot.bus.emit(Event(type="github.issue.opened", data={
        "repo": "myorg/myproject",
        "number": 123,
        "title": "Bug: Login fails with 500 error",
        "body": "When I try to login with invalid credentials, the server crashes."
    }))
    
    await asyncio.sleep(2)
    
    # Simulate PR updated
    await bot.bus.emit(Event(type="github.pr.updated", data={
        "repo": "myorg/myproject",
        "number": 42,
        "files": ["auth.py", "models.py", "tests/test_auth.py", "config.py"]
    }))
    
    print("\n✅ Simulation complete")


async def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Event-driven GitHub Bot")
    parser.add_argument("--simulate", "-s", action="store_true", help="Simulate events instead of running server")
    parser.add_argument("--port", "-p", type=int, default=8080, help="Webhook server port")
    parser.add_argument("--state-dir", default="./.github_bot_state", help="State storage directory")
    args = parser.parse_args()
    
    # Get GitHub token
    token = os.environ.get("GITHUB_TOKEN", "fake_token_for_demo")
    
    # Create bot
    bot = GitHubBot(token, state_dir=args.state_dir)
    
    if args.simulate:
        # Run simulation
        await simulate_events(bot)
        
        # Show final state
        print("\n📊 Final State:")
        for key in await bot.state.list("pr:"):
            pr_data = await bot.state.get(key)
            print(f"   {key}: {pr_data.get('status', 'unknown')}")
        
    else:
        # Run webhook server
        WebhookHandler.bot = bot
        server = HTTPServer(("", args.port), WebhookHandler)
        
        print(f"🚀 GitHub Bot listening on port {args.port}")
        print(f"   Webhook URL: http://localhost:{args.port}/webhook")
        print("   Press Ctrl+C to stop\n")
        
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
            server.shutdown()
    
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
