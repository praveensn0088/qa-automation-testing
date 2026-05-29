# metrics.py

from prometheus_client import Counter, Histogram, Gauge, start_http_server
 
# -------- Agent Level --------

# AGENT_EXECUTION_TIME = Histogram(
#     "autogen_agent_execution_seconds",
#     "Execution time of AutoGen agents",
#     ["agent_name"]
# )

AGENT_EXECUTION_TIME = Histogram(
    "autogen_agent_execution_seconds",
    "Execution time per agent",
    ["agent_name"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300)
)

# Token Counters
LLM_PROMPT_TOKENS = Counter(
    "autogen_prompt_tokens_total",
    "Total prompt tokens used",
    ["agent_name"]
)

LLM_COMPLETION_TOKENS = Counter(
    "autogen_completion_tokens_total",
    "Total completion tokens used",
    ["agent_name"]
)

LLM_TOKENS = Counter(
    "llm_tokens_total",
    "Total tokens consumed",
    ["agent_name", "model"]
)

LLM_COST = Counter(
    "llm_cost_usd_total",
    "Total LLM cost in USD",
    ["agent_name", "model"]
)
 
AGENT_FAILURES = Counter(
    "autogen_agent_failures_total",
    "Failures per AutoGen agent",
    ["agent_name"]
)
 
# -------- Routing --------

AGENT_ROUTING = Counter(
    "autogen_agent_routing_total",
    "Subtask routing count",
    ["agent_name"]
)
 
ROUTING_SCORE = Histogram(
    "autogen_agent_routing_score",
    "Routing score distribution",
    ["agent_name"]
)
 
# -------- GroupChat --------

GROUPCHAT_DURATION = Histogram(
    "autogen_groupchat_duration_seconds",
    "Execution time of RoundRobinGroupChat"
)
 
# -------- Jira Tools --------

JIRA_TOOL_CALLS = Counter(
    "autogen_jira_tool_calls_total",
    "Number of Jira tool calls"
)
 
JIRA_TOOL_DURATION = Histogram(
    "autogen_jira_tool_duration_seconds",
    "Time spent in Jira tool calls"
)
 
def start_metrics():
    start_http_server(9090)

 