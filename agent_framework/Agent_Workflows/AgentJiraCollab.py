import os.path
from typing import Optional
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from agent_framework.agent_config.AgentFeedback import AgentFeedback
from autogen_agentchat.ui import Console
from pathlib import Path
from agent_framework.Agent_Workflows.AgentCollaboration import subtask_status
from agent_framework.agent_config.AgentFactory import AgentFactory
from agent_framework.agent_config.Mcp_config import Mcp_config
from agent_framework.utils.logger import logger
from agent_framework.utils.utils import load_prompt, load_input_path, route_subtask, convert_to_serializable, \
    visualize_subtask_agent_mapping


class Agent_Jira_Collaboration:

    def __init__(self, config_path_param, jira_story_id: Optional[str] = None, user_prompt: Optional[str] = None) -> None:
        self.config_path = config_path_param
        self.config_values = Mcp_config(config_path_param).config

        # Initialize paths
        self.input_path = self.config_values.get("inputData_path")
        self.output_path = self.config_values.get("outputData_path")
        self.auto_repo_path = self.config_values.get("auto_repo_path")
        self.task_prompt_path = Path(
            config_path_param.parent.parent / "agent_framework/prompts/task_prompts/JiraScriptGen.txt"
        )
        # Validate required configuration
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

        # Initialize factory
        self.factory = AgentFactory(self.model_client, config_path=config_path_param)

        # Initialize agents
        self.workbench = self.factory.mcp_config.get_fs_workbench()
        self.decomposer = self.factory.create_task_decomposition_agent()
        self.jira_agent = self.factory.create_jira_agent()
        self.fallback_agent = self.factory.create_user_proxy_agent(file_path=None, name="user_proxy_agent")

        self.read_agent = self.factory.create_fs_read_agent(file_name=self.input_path, input_dir="inputData", output_dir="AIOutput")
        self.qa_agent = self.factory.create_qa_agent()
        self.write_agent, self.output_file_path = self.factory.create_fs_write_agent(
            input_file_name="jira_demo",
            agent_name="jira_agent",
            output_dir="AIOutput",
            input_dir="inputData"
        )
        self.output_file_name = os.path.basename(self.output_file_path)

        self.agents = [self.read_agent, self.jira_agent, self.qa_agent, self.write_agent, self.fallback_agent]
        self.workbench.register_agents(self.agents + [self.decomposer])
        prompt = load_prompt("JiraScriptGen", "task_prompts")

        input_add = load_input_path(self.input_path, "inputData")
        self.task_prompt = (prompt
                            .replace("{inputData_path}", str(input_add))
                            .replace("{AIOutput}", str("AIOutput"))
                            .replace("{fileName}", str(self.output_file_name))
                            .replace("{ISSUE_KEY}", str(jira_story_id))
                            )

    async def run_jira_team(self):
        try:
            logger.info("Starting QA team workflow")
            for agent in self.agents:
                agent.remember_context(self.task_prompt)
            self.subtasks = await self.decomposer.decompose_task(self.task_prompt)
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

            qateam = RoundRobinGroupChat(
                participants=[self.decomposer] + self.agents,
                termination_condition=MaxMessageTermination(max_messages=100)
            )
            await Console(qateam.run_stream(task=self.task_prompt))

            self.factory.ltm.save(f"subtask_status:{self.task_prompt}", convert_to_serializable(subtask_status))
            visualize_subtask_agent_mapping(subtask_status)

            return {
                "status": "success",
                "message": "QA workflow completed",
                "output_file": str(self.output_file_path)
            }

        except Exception as e:
            logger.error("Agent QA collaboration failed: %s", str(e), exc_info=True)

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
