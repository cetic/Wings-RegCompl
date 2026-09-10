#!/usr/bin/env python3
"""
CLI entry point for the CRA Knowledge Graph Agent system.

Usage:
    # Interactive mode (ADK web UI)
    adk web cra_agents

    # Or run directly as a CLI
    python -m cra_agents
"""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from .agent import root_agent

load_dotenv()


async def main():
    """Run the CRA orchestrator in an interactive CLI loop."""
    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        app_name="cra_knowledge_graph",
        session_service=session_service,
    )

    # Create a session
    session = await session_service.create_session(
        app_name="cra_knowledge_graph",
        user_id="user",
    )

    print("=" * 60)
    print("  CRA Knowledge Graph Agent")
    print("  Powered by Google ADK + Gemma4 + Neo4j")
    print("=" * 60)
    print()
    print("Examples:")
    print('  • "Ingest Article 14"')
    print('  • "Ingest all articles from Chapter II"')
    print('  • "What are the obligations for manufacturers?"')
    print('  • "Show me all actors in the graph"')
    print('  • "What must a product with digital elements comply with?"')
    print('  • "Graph stats"')
    print()
    print("Type 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        # Build the user message content
        from google.genai import types

        user_msg = types.Content(
            role="user",
            parts=[types.Part(text=user_input)],
        )

        print("\nAgent: ", end="", flush=True)

        async for event in runner.run_async(
            user_id="user",
            session_id=session.id,
            new_message=user_msg,
        ):
            # Print final agent responses
            if event.is_final_response():
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            print(part.text)
        print()


if __name__ == "__main__":
    asyncio.run(main())
