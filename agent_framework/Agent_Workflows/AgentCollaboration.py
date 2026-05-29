import sys
import asyncio
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.ui import Console
from pathlib import Path
from agent_framework.agent_config.AgentFactory import AgentFactory
from agent_framework.agent_config.Mcp_config import Mcp_config
from agent_framework.utils.utils import config_path, load_prompt, route_subtask, visualize_subtask_agent_mapping, \
    convert_to_serializable
from agent_framework.utils.logger import logger

subtask_status = {}
async def run_agent_collaboration():
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        # Load configuration
        config_values = Mcp_config(config_path).config
        input_path = config_values.get("inputData_path")
        output_path = config_values.get("outputData_path")
        auto_repo_path = config_values.get("auto_repo_path")
        task_prompt_path = Path(config_path.parent.parent / "agent_framework/prompts/task_prompts/SauceLab_Task.txt")
        model_name = config_values.get("model_name")
        api_key = config_values.get("AZURE_OPENAI_API_KEY")
        AZURE_OPENAI_ENDPOINT = config_values.get("AZURE_OPENAI_ENDPOINT")
        api_type = config_values.get("api_type")
        api_version = config_values.get("AZURE_OPENAI_API_VERSION")
        AZURE_OPENAI_DEPLOYMENT_ID = config_values.get("AZURE_OPENAI_DEPLOYMENT_ID")

        if not all([input_path, output_path, model_name, api_key]):
            raise ValueError("Missing required configuration values.")

        model_client = OpenAIChatCompletionClient(
            model=model_name,
            api_key=api_key,
            base_url=AZURE_OPENAI_ENDPOINT,
            api_type=api_type,
            api_version=api_version,
            deployment_id=AZURE_OPENAI_DEPLOYMENT_ID
        )

        factory = AgentFactory(model_client, config_path=config_path)

        decomposer = factory.create_task_decomposition_agent()
        read_agent = factory.create_fs_read_agent(file_name=input_path, input_dir="inputData",
                                                  output_dir="AIOutput")
        jira_agent = factory.create_jira_agent()
        # qtest_agent = factory.create_qtest_agent()
        # qa_agent = factory.create_qa_agent()
        # db_agent = factory.create_db_agent(system_message="get all the details from db table.")
        write_agent, output_file_path = factory.create_fs_write_agent(
            input_file_name=input_path,
            agent_name="write_agent",
            output_dir="AIOutput",
            input_dir="inputData"
        )
        # auto_write_agent, output_dir = factory.create_fs_write_agent(input_file_name=input_path,
        #                                                              agent_name='qe_agent',
        #                                                              output_dir="AI_Auto_Repos",
        #                                                              input_dir="AIOutput")

        # playwright_dev_agent = factory.create_playwright_dev_agent(input_file=input_path,
        #                                                                      output_dir="AI_Auto_Repos")
        # playwright_reviwer_agent = factory.create_playwright_reviewer_agent(file_path=auto_repo_path)
        # playwright_execution_agent = factory.create_playwright_execution_agent(file_path=auto_repo_path)
        # puppeteer_dev_agent = factory.create_puppeteer_dev_agent(file_path=auto_repo_path)
        # fallback_agent = factory.create_user_proxy_agent(file_path=None, name="user_proxy_agent")

        task_context = task_prompt_path.read_text()
        for agent in [read_agent, jira_agent, write_agent]:
            agent.remember_context(task_context)

        subtasks = await decomposer.decompose_task(task_context)
        logger.info(f"Subtasks generated: {subtasks}")

        agents = [read_agent, jira_agent, write_agent]

        for subtask in subtasks:
            agent, score = route_subtask(subtask["task"], agents)
            if agent:
                subtask_status[subtask["task"]] = {"agent": agent.name, "status": "Assigned", "score": score}
                logger.info(f"Routing subtask '{subtask['task']}' to {agent.name} (score={score:.2f})")

                # Use RoundRobinGroupChat to invoke agent
                team = RoundRobinGroupChat(
                    participants=[agent],
                    termination_condition=MaxMessageTermination(max_messages=3)
                )
                await Console(team.run_stream(task=subtask["task"]))
            else:
                subtask_status[subtask["task"]] = {"agent": "None", "status": "Unassigned"}
                logger.warning(f"No agent found for subtask: {subtask['task']}")

        # Final team execution for full task context
        qeteam = RoundRobinGroupChat(
            participants=[decomposer, read_agent, jira_agent, write_agent],
            termination_condition=MaxMessageTermination(max_messages=80)
        )
        await Console(qeteam.run_stream(task=task_context))

        factory.ltm.save(f"subtask_status:{task_context}", convert_to_serializable(subtask_status))


    except Exception as e:
        logger.error("Agent collaboration failed: %s", str(e), exc_info=True)


if __name__ == "__main__":
    asyncio.run(run_agent_collaboration())
