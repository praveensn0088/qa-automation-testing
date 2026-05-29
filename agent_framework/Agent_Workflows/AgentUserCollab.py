from typing import Optional, Dict, Any
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from pathlib import Path
from agent_framework.agent_config.AgentFactory import AgentFactory
from agent_framework.agent_config.Mcp_config import Mcp_config
from agent_framework.utils.logger import logger
from agent_framework.utils.utils import load_prompt, load_input_path, get_output_path, convert_to_serializable, \
    visualize_subtask_agent_mapping, route_subtask, sanitize_prompt, safe_team_run

subtask_status: Dict[str, Any] = {}

class AgentUserCollaboration:
    def __init__(self, config_path_param, input_path: Optional[str] = None, user_prompt: Optional[str] = None) -> None:
        self.config_path = config_path_param
        self.config_values = Mcp_config(config_path_param).config

        self.auto_repo_path = self.config_values.get("auto_repo_path")

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
        self.factory = AgentFactory(self.model_client, config_path=config_path_param)

        # Initialize agents
        self.workbench = self.factory.mcp_config.get_fs_workbench()
        self.decomposer = self.factory.create_task_decomposition_agent()
        self.read_agent = self.factory.create_fs_read_agent(
            file_name=input_path, input_dir="AI_Auto_Repos", output_dir="AI_Auto_Repos"
        )
        self.playwright_dev_agent = self.factory.create_playwright_dev_agent(
            input_file=input_path, output_dir="AI_Auto_Repos", target_dir="AI_Auto_Repos"
        )
        self.auto_write_agent, self.output_dir = self.factory.create_fs_write_agent(
            input_file_name=input_path,
            agent_name='qe_agent',
            output_dir="AI_Auto_Repos",
            input_dir="AI_Auto_Repos"
        )
        self.playwright_reviewer_agent = self.factory.create_playwright_reviewer_agent(
            file_path=self.auto_repo_path
        )

        self.agents = [
            self.decomposer,
            self.read_agent,
            self.playwright_dev_agent,
            self.playwright_reviewer_agent,
            self.update_agent
        ]

        prompt = load_prompt("role_prompts", "user_prompt")

        self.task_prompt = sanitize_prompt(
            prompt.replace("{input_file}", str(input_path))
            .replace("{AI_Auto_Repo}", str(self.output_dir))
            .replace("{user_prompt}", str(user_prompt))
        )

    async def run_user_team(self):
        try:
            logger.info("Starting QE team workflow")
            for agent in [self.read_agent, self.playwright_dev_agent, self.auto_write_agent]:
                agent.remember_context(self.task_prompt)

            # Decompose with protection
            self.subtasks = await self.decomposer.decompose_task(
                self.task_prompt, max_iterations=1
            )
            logger.info(f"Subtasks generated: {len(self.subtasks)}")

            for subtask in self.subtasks:
                clean_subtask = sanitize_prompt(subtask["task"])
                logger.info(f"Processing subtask: {clean_subtask[:150]}...")

                agent, score = route_subtask(subtask, self.agents)
                if agent:
                    subtask_status[subtask["task"]] = {
                        "agent": agent.name, "status": "Assigned", "score": score
                    }
                    logger.info(f"Routing '{subtask['task'][:50]}...' to {agent.name} (score={score:.2f})")

                    team = RoundRobinGroupChat(
                        participants=[agent],
                        termination_condition=MaxMessageTermination(max_messages=3)
                    )

                    result = await safe_team_run(team, clean_subtask)

                    try:
                        feedback = await agent.generate_feedback(clean_subtask, result)
                        await agent.send_feedback(feedback, self.workbench)
                    except Exception as fb_err:
                        logger.warning(f"Feedback failed for {agent.name}: {fb_err}")
                else:
                    subtask_status[subtask["task"]] = {
                        "agent": "None", "status": "Unassigned"
                    }
                    logger.warning(f"No agent for subtask: {subtask['task']}")

            qeteam = RoundRobinGroupChat(
                participants=[
                    self.decomposer,
                    self.read_agent,
                    self.playwright_dev_agent,
                    self.playwright_reviewer_agent,
                    self.auto_write_agent
                ],
                termination_condition=MaxMessageTermination(max_messages=100)
            )

            result = await safe_team_run(qeteam, self.task_prompt)

            logger.info("QE team workflow completed successfully")
            self.factory.ltm.save(
                f"subtask_status:{self.task_prompt}",
                convert_to_serializable(subtask_status)
            )
            visualize_subtask_agent_mapping(subtask_status)

            return str(self.output_dir)

        except Exception as e:
            logger.error("Agent QE collaboration failed", exc_info=True)
            raise
        finally:
            if self.agents:
                for agent in self.agents:
                    try:
                        await agent.close()
                    except Exception as e:
                        logger.warning(f"Failed to shutdown {agent.name}: {e}")

            if self.workbench:
                try:
                    await self.workbench.cleanup()
                except Exception as e:
                    logger.warning(f"Failed to cleanup workbench: {e}")
