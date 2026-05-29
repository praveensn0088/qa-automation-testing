from typing import Optional
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.ui import Console
from pathlib import Path
import os
from agent_framework.agent_config.AgentFactory import AgentFactory
from agent_framework.agent_config.Mcp_config import Mcp_config
from agent_framework.utils.logger import logger
from agent_framework.utils.utils import load_prompt, load_input_path, get_output_path, convert_to_serializable, \
    visualize_subtask_agent_mapping, route_subtask

subtask_status = {}
class AgentBitbucketPullCollaboration:

    def __init__(self, config_values, repo_url: str, branch_name: str) -> None:
        self.config_values = config_values

        self.repo_url = repo_url
        self.branch_name = branch_name
        # Initialize paths
        self.input_path = self.config_values.get("clone_repo_path")
        self.task_prompt_path = Path.cwd().parent / "agent_framework" / "prompts" / "task_prompts" / "BitBucketPullGen.txt"
        self.base_dir = self.config_values.get("base_dir")
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

        # Initialize factory
        self.factory = AgentFactory(self.model_client, config_path="agent_framework/config.json")

        # Initialize agents
        self.workbench = self.factory.mcp_config.get_fs_workbench()
        self.decomposer = self.factory.create_task_decomposition_agent()
        self.bitbucket_agent = self.factory.create_bitbucket_agent()
        self.agents = [
            self.decomposer,
            self.bitbucket_agent
        ]
        prompt = load_prompt("BitBucketPullGen", "task_prompts")

        dir_path = Path(os.path.join(self.base_dir, str("AI_Clone_Repo"), str("agenticai_test_repo")))

        dir_path.mkdir(parents=True, exist_ok=True)

        self.input_add = dir_path

        self.task_prompt = (prompt
            .replace("{localPath}", str(self.input_add))
            .replace("{workspace}", str("is_corp"))
            .replace("{repo_slug}", str("agenticai_test_repo"))
            .replace("{branch}", str("main"))
            )



    async def run_bitbucket_pull_team(self):
        try:
            logger.info("Starting Bitbucket team workflow")
            for agent in [self.bitbucket_agent]:
                agent.remember_context(self.task_prompt)
            self.subtasks = await self.decomposer.decompose_task(self.task_prompt, max_iterations=1)
            logger.info(f"Subtasks generated: {self.subtasks}")

            for subtask in self.subtasks:
                agent, score = route_subtask(subtask, self.agents)
                if agent:
                    subtask_status[subtask["task"]] = {"agent": agent.name, "status": "Assigned", "score": score}
                    logger.info(f"Routing subtask '{subtask['task']}' to {agent.name} (score={score:.2f})")

                    team = RoundRobinGroupChat(
                        participants=[agent],
                        termination_condition=MaxMessageTermination(max_messages=3)
                    )
                    result = await Console(team.run_stream(task=subtask["task"]))

                    feedback = await agent.generate_feedback(subtask["task"], result)
                    await agent.send_feedback(feedback, self.workbench)
                else:
                    subtask_status[subtask["task"]] = {"agent": "None", "status": "Unassigned"}
                    logger.warning(f"No agent found for subtask: {subtask['task']}")

            bitbucketteam = RoundRobinGroupChat(
                participants=[
                    self.decomposer,
                    self.bitbucket_agent
                ],
                termination_condition=MaxMessageTermination(max_messages=30)
            )
            await Console(bitbucketteam.run_stream(task=self.task_prompt))
            logger.info("Bitbucket team workflow completed successfully")
            self.factory.ltm.save(f"subtask_status:{self.task_prompt}", convert_to_serializable(subtask_status))
            visualize_subtask_agent_mapping(subtask_status)

            return {
                "file_path": str(self.input_add)
            }
        except Exception as e:
            logger.error("Agent Bitbucket collaboration failed: %s", str(e), exc_info=True)

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

