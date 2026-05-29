import os.path
import re
from typing import Optional
from pathlib import Path
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient
from agent_framework.agent_config.AgentFactory import AgentFactory
from agent_framework.agent_config.Mcp_config import Mcp_config
from agent_framework.utils.logger import logger
from agent_framework.utils.utils import (
    load_prompt,
    load_input_path,
    route_subtask,
    convert_to_serializable,
    visualize_subtask_agent_mapping
)
from agent_framework.Agent_Workflows.AgentCollaboration import subtask_status
from metrics.llm_metrics import record_llm_usage
from metrics.track_latency_agent import track_agent_latency

class DomainAgentCollaboration:

    def __init__(self, config_path_param, input_path: Optional[str] = None, domainType: str = "", user_prompt: Optional[str] = None) -> None:
        self.config_path = config_path_param
        self.config_values = Mcp_config(config_path_param).config
        self.base_dir = self.config_values.get("base_dir")

        self.domainType = domainType
        self.input_path = input_path
        self.output_path = self.config_values.get("outputData_path")
        self.auto_repo_path = self.config_values.get("auto_repo_path")
        self.task_prompt_path = Path(
            config_path_param.parent.parent / "agent_framework/prompts/task_prompts/Domain_Agent_Task.txt"
        )

        if not all([self.input_path, self.output_path]):
            raise ValueError("Missing required configuration values.")

        # Initialize model client
        model_name = self.config_values.get("model_name")
        api_key = self.config_values.get("AZURE_OPENAI_API_KEY")
        AZURE_OPENAI_ENDPOINT = self.config_values.get("AZURE_OPENAI_ENDPOINT")
        api_type = self.config_values.get("api_type")
        api_version = self.config_values.get("AZURE_OPENAI_API_VERSION")
        AZURE_OPENAI_DEPLOYMENT_ID = self.config_values.get("AZURE_OPENAI_DEPLOYMENT_ID")

        if not all([model_name, api_key]):
            raise ValueError("Missing required configuration values.")

        self.model_client = OpenAIChatCompletionClient(
            model=model_name,
            api_key=api_key,
            base_url=AZURE_OPENAI_ENDPOINT,
            api_type=api_type,
            api_version=api_version,
            deployment_id=AZURE_OPENAI_DEPLOYMENT_ID
        )

        self.factory = AgentFactory(self.model_client, config_path=config_path_param)

        # Initialize agents
        self.workbench = self.factory.mcp_config.get_fs_workbench()
        self.decomposer = self.factory.create_task_decomposition_agent()
        self.fallback_agent = self.factory.create_user_proxy_agent(file_path=None, name="user_proxy_agent")

        self.read_agent = self.factory.create_fs_read_agent(
            file_name=self.input_path,
            input_dir="inputData",
            output_dir="AIOutput"
        )

        self.domain_agent = self.factory.create_domain_agent(config_path_param)
        self.knowledge_agent = self.factory.create_knowledge_agent()
        if self.domainType == "transcript":
            out_dir = Path(os.path.join(self.base_dir,"AIOutput", "specs", "transcript_req"))
            out_dir.mkdir(parents=True, exist_ok=True)
            self.output_path = str(out_dir)
            self.write_agent, self.output_file_path = self.factory.create_fs_write_agent(
                input_file_name=self.input_path,
                agent_name="write_agent",
                input_dir="inputData",
                output_dir=os.path.join("AIOutput", "specs", "transcript_req")
                
            )
            input_add = load_input_path(self.input_path, "inputData")
        elif self.domainType == "repo_analyzer":
            input_add = input_path
            out_dir = Path(os.path.join(self.base_dir,"AIOutput", "specs", "repo_analyzer_req"))
            out_dir.mkdir(parents=True, exist_ok=True)

            self.output_path = str(out_dir)
            self.write_agent, self.output_file_path = self.factory.create_fs_write_agent(
                input_file_name=self.input_path,
                agent_name="write_agent",
                input_dir="inputData",
                output_dir=os.path.join("AIOutput", "specs", "repo_analyzer_req")
            )

        self.output_file_name = os.path.basename(self.output_file_path)

        self.agents = [self.read_agent, self.domain_agent, self.knowledge_agent, self.write_agent, self.fallback_agent]
        self.workbench.register_agents(self.agents + [self.decomposer])

        prompt = load_prompt("Domain_Agent_Task", "task_prompts")

        self.task_prompt = sanitize_prompt(prompt)
        

        print("input_path:", str(input_add))
        print("aioutput:", str(self.output_path))

        self.task_prompt = (prompt
                            .replace("{input_path}", str(input_add))
                            .replace("{output_path}", str(self.output_path))
                            )
    
    async def run_domain_team(self):
        try:
            logger.info("Starting Domain Agent team workflow")
            for agent in self.agents:
                agent.remember_context(self.task_prompt)

            # self.subtasks = await self.decomposer.decompose_task(self.task_prompt)
            # logger.info(f"Subtasks generated: {self.subtasks}")

            # for subtask in self.subtasks:
            #     clean_subtask = sanitize_prompt(subtask["task"])
            #     logger.info(f"Processing subtask: {clean_subtask[:150]}...")

            #     agent, score = route_subtask(subtask, self.agents)
            #     print(agent.name if agent else "None", score)

            #     if agent:
            #         subtask_status[subtask["task"]] = {"agent": agent.name, "status": "Assigned", "score": score}
            #         logger.info(f"Routing subtask '{subtask['task']}' to {agent.name} (score={score:.2f})")

            #         # SPECIAL PATH: Domain Agent pipeline (clone -> analyze -> generate)
            #         if agent.name.lower() == "domain_agent":
            #             try:
            #                 subtask_status[subtask["task"]]["status"] = "InProgress"

            #                 # 1) Clone repo
            #                 clone_res = await agent.call_tool("clone_repo", {})
            #                 logger.info("clone_repo result: %s", str(clone_res)[:800])

            #                 # 2) Analyze code
            #                 _ = await agent.call_tool("analyze_code", {})

            #                 # 3) Generate FRD/TRD
            #                 docs_res = await agent.call_tool("generate_docs", {"top_k_kb": 8})
            #                 logger.info("generate_docs result: %s", docs_res)

            #                 subtask_status[subtask["task"]]["status"] = "Completed"

            #             except Exception as e:
            #                 logger.error("Domain pipeline failed for '%s': %s", subtask["task"], e, exc_info=True)
            #                 subtask_status[subtask["task"]]["status"] = "Failed"
            #                 continue

            #         # Default path for other agents
            #         else:
            #             team = RoundRobinGroupChat(
            #                 participants=[agent],
            #                 termination_condition=MaxMessageTermination(max_messages=3)
            #             )
            #             result = await Console(team.run_stream(task=subtask["task"]))

            #             feedback = await agent.generate_feedback(subtask["task"], result)
            #             print(feedback)
            #             await agent.send_feedback(feedback, self.workbench)

            #             # RAG retrieval for knowledge enhancement
            #             if bool(self.config_values.get("retrieve_once_per_subtask", True)):
            #                 if "rag_answer" not in subtask_status[subtask["task"]]:
            #                     query = f"Answer based on knowledge base for: {subtask['task']}"
            #                     rag_answer = await self.knowledge_agent.retrieve_knowledge(query)
            #                     subtask_status[subtask["task"]]["rag_answer"] = rag_answer
            #                     logger.info("RAG for '%s': %s", subtask["task"], str(rag_answer)[:600])

            #             # Special review agent handling
            #             if "review" in agent.name.lower():
            #                 str_result = result if isinstance(result, str) else str(result)
            #                 approved = isinstance(result, str) and ("approved" in result.lower())
            #                 review_status = "Approved" if approved else "Rejected"
            #                 subtask_status[subtask["task"]]["status"] = review_status

            #                 if approved:
            #                     await self.write_agent.run(task=f"Write the following content:\n{str_result}")
            #                     subtask_status[subtask["task"]]["status"] = "Written"
            #                 else:
            #                     await self.fallback_agent.run(
            #                         task=f"Review failed for '{subtask['task']}'. Please check manually.")
            #                     subtask_status[subtask["task"]]["status"] = "Review Failed"
            #             else:
            #                 subtask_status[subtask["task"]]["status"] = "Completed"

            #     else:
            #         subtask_status[subtask["task"]] = {"agent": "None", "status": "Unassigned"}
            #         logger.warning(f"No agent found for subtask: {subtask['task']}")

            print("=== DECOMPOSER ===")
            print(
                self.decomposer.name,
                "instrumented=", getattr(self.decomposer, "_instrumented", False),
                "method=", getattr(self.decomposer, "on_messages", None),
            )

            print("\n=== FACTORY AGENTS ===")
            for idx, agent in enumerate(self.agents):
                print(
                    f"[{idx}]",
                    agent.name,
                    "instrumented=", getattr(agent, "_instrumented", False),
                    "method=", getattr(agent, "on_messages", None),
                )

            # Final multi-agent team pass
            domainteam = RoundRobinGroupChat(
                participants=[self.decomposer] + self.agents,
                termination_condition=MaxMessageTermination(max_messages=50)
            )
            print(f"prompt -------",self.task_prompt)

            print("=== PARTICIPANTS ===")
            for p in domainteam._participants:
                print(p.name, getattr(p, "_instrumented", False), p.on_messages)

            llm_res = await run_with_console_and_tokens(domainteam, task=self.task_prompt, model_name = self.config_values.get("model_name"))

            self.factory.ltm.save(f"subtask_status:{self.task_prompt}", convert_to_serializable(subtask_status))
            visualize_subtask_agent_mapping(subtask_status)
            dir_path = str(Path(self.output_file_path).parent)

            return {
                "status": "success",
                "message": "Domain Agent workflow completed",
                "output_path": dir_path,
                "llm_usage": llm_res
            }

        except Exception as e:
            logger.error("Domain Agent collaboration failed: %s", str(e), exc_info=True)
            raise

        finally:
            if self.agents:
                for agent in self.agents:
                    try:
                        await agent.close()
                    except Exception as e:
                        logger.warning(f"Failed to shutdown agent {agent.name}: {e}")

            if self.workbench:
                try:
                    await self.workbench.cleanup()
                except Exception as e:
                    logger.warning(f"Failed to cleanup workbench: {e}")

async def run_with_console_and_tokens(team, task: str, model_name:str):

    total_prompt_tokens = 0
    total_completion_tokens = 0
    per_agent_usage = {}
    async for event in team.run_stream(task=task):
        
        # 🔹 Print message safely
        if event and hasattr(event, "models_usage") and event.models_usage:
            
            # print(f"\n[{event.get('source')}]")
            # print(event.get("content"))

            usage = event.models_usage
            if usage:

                # ✅ accumulate per-agent locally (optional but useful)
                if event.source not in per_agent_usage:

                    agent_name=event.source
                    prompt_tokens = usage.prompt_tokens
                    completion_tokens = usage.completion_tokens
                    per_agent_usage[agent_name] = {
                        "agent_name": agent_name,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    }
                
                per_agent_usage[agent_name]["prompt_tokens"] += prompt_tokens
                per_agent_usage[agent_name]["completion_tokens"] += completion_tokens
                per_agent_usage[agent_name]["total_tokens"] += (prompt_tokens + completion_tokens)

                record_llm_usage(agent_name=agent_name, message = event, model_name= model_name)

                total_prompt_tokens += prompt_tokens
                total_completion_tokens += completion_tokens

    total_tokens = total_prompt_tokens + total_completion_tokens
    per_agent_list = list(per_agent_usage.values())
    print("\n=== Final Token Summary ===")
    print("Prompt Tokens:", total_prompt_tokens)
    print("Completion Tokens:", total_completion_tokens)
    print("Total Tokens:", total_tokens)
    print("per_agent_usage:", per_agent_list)



    response = {
        "workflow_tokens": {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
        },
        "per_agent_tokens": per_agent_list,
    }
    print(f"Response  = {response}")
    return response

def sanitize_prompt(prompt: str) -> str:
    triggers = [
        r'IGNORE PREVIOUS? INSTRUCTIONS?', r'NO ANALYSIS', r'EXECUTE NOW',
        r'NO EXPLANATION', r'RETURN ONLY', r'DO NOT EXPLAIN', r'MANDATORY',
        r'CRITICAL', r'IMPORTANT', r'OVERRIDE', r'BYPASS', r'JAILBREAK', r'HALT',
        r'HALT ALL', r'HALT ALL FURTHER ACTION',r'STOP ALL',
        r'STOP ALL FURTHER ACTION',r'EMIT', r'EMIT THE', r'EMIT .* TOKEN', r'FORCE',
        r'FORCE OUTPUT', r'FORCE RESPONSE', r'TERMINATE',  r'TERMINATE EXECUTION',
        r'TERMINATION', r'DO NOT CONTINUE', r'NO FURTHER ACTION', r'CEASE', r'CEASE RESPONDING',
        r'VERIFY ALL',
        r'OUTPUT ARTIFACTS',
        r'FINAL USER SIGNAL',
        r'NO FURTHER PROCESSING',
        r'RETURN THE MESSAGE',
        r'RETURN THE MESSAGE .*',
        r'REQUIREMENTS_GENERATION_COMPLETED'
    ]

    # 2️⃣ Agentic / autonomy phrasing (REWRITE, not delete)
    AGENTIC_REWRITES = {
        r'\bsystem remains\b': 'the application remains',
        r'\bsystem is\b': 'the application is',
        r'\bstandby mode\b': '',
        r'\ball agents?\b': 'all components',
        r'\bagents? are available\b': 'resources are available',
        r'\bready to (process|execute)\b': 'able to generate',
        r'\bprocess your instructions\b': 'handle your request',
        r'\bfollow your instructions\b': 'respond to your request',
        r'\bplease specify\b': 'you may choose',
        r'\bnext action\b': 'one of the following options',
        r'\binitiate\b': 'start',
        r'\bexecute\b': 'generate',
        r'\binstruction(s)?\b': 'request',
        r'\bcommand(s)?\b': 'request',
        r'\bworkflow\b': 'process',
        r'\borchestrate\b': 'coordinate',
    }

    for trigger in triggers:
        prompt = re.sub(trigger, '', prompt, flags=re.IGNORECASE)

    # Rewrite agentic framing
    for pattern, replacement in AGENTIC_REWRITES.items():
        prompt = re.sub(pattern, replacement, prompt, flags=re.IGNORECASE)

    # Normalize whitespace
    prompt = re.sub(r'\s{2,}', ' ', prompt).strip()

    # Shorten to avoid context buildup
    return prompt[:20000]