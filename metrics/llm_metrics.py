from metrics.metrics import LLM_COMPLETION_TOKENS, LLM_PROMPT_TOKENS, LLM_TOKENS

def record_llm_usage(agent_name: str,message: dict, model_name:str):
    usage = message.models_usage
    prompt_tokens = usage.prompt_tokens
    completion_tokens = usage.completion_tokens

    total_tokens = (prompt_tokens + completion_tokens)

    LLM_PROMPT_TOKENS.labels(agent_name=agent_name).inc(prompt_tokens)

    LLM_COMPLETION_TOKENS.labels(agent_name=agent_name).inc(completion_tokens)

    LLM_TOKENS.labels(agent_name=agent_name,model=model_name).inc(total_tokens)