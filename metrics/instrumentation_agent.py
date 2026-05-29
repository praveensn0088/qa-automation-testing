from metrics.track_latency_agent import track_agent_latency


def instrument_agent(agent):
    """
    Attach latency tracking to AutoGen agents.
    Safe for AutoGen 0.7.x and most agent types.
    """
    print(f"WRAPPING AGENT: {agent.name}")
    # Avoid double wrapping
    if getattr(agent, "_latency_instrumented", False):
        return agent

    # Wrap on_messages (AssistantAgent path)
    agent_name = getattr(agent, "name", agent.__class__.__name__)

    # ---------- wrap on_messages ----------
    if hasattr(agent, "on_messages"):
        original_on_messages = agent.on_messages

        async def wrapped_on_messages(*args, __orig=original_on_messages, __name=agent_name, **kwargs):
            print(f"🔥🔥🔥 AGENT EXECUTED: {__name}")

            with track_agent_latency(__name):
                return await __orig(*args, **kwargs)

        agent.on_messages = wrapped_on_messages
        # mark instrumented
        agent._latency_instrumented = True
        agent._instrumented = True  # 🔥 REQUIRED

    # ---------- wrap on_messages_stream (VERY IMPORTANT) ----------
    if hasattr(agent, "on_messages_stream"):
        original_stream = agent.on_messages_stream

        async def wrapped_stream(*args, __orig=original_stream, __name=agent_name, **kwargs):
            print(f"🔥🔥🔥 STREAM AGENT EXECUTED: {__name}")

            with track_agent_latency(__name):
                async for chunk in __orig(*args, **kwargs):
                    yield chunk

        agent.on_messages_stream = wrapped_stream
        # mark instrumented
        agent._latency_instrumented = True
        agent._instrumented = True  # 🔥 REQUIRED

    # ALSO wrap a_generate_reply (some agents use this)
    if hasattr(agent, "a_generate_reply"):
        original_gen = agent.a_generate_reply

        async def wrapped_gen(*args, **kwargs):
            with track_agent_latency(agent_name):
                return await original_gen(*args, **kwargs)

        agent.a_generate_reply = wrapped_gen
        # mark instrumented
        agent._latency_instrumented = True
        agent._instrumented = True  # 🔥 REQUIRED


    return agent