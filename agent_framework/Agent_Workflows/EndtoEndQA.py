import asyncio
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.ui import Console
from pathlib import Path
from agent_framework.agent_config.AgentFactory import AgentFactory
from agent_framework.agent_config.Mcp_config import Mcp_config
from agent_framework.utils.utils import config_path
from agent_framework.utils.logger import logger

async def run_collaboration():
    try:
        # Load configuration
        config = Mcp_config(config_path).config
        input_data_path = config.get("inputData_path")
        output_data_path = config.get("outputData_path")
        task_prompt_path = Path(config_path.parent.parent/"agent_framework/prompts/task_prompts/end_to_end_qa.txt")
        model_name = config.get("model_name")
        api_key = config.get("AZURE_OPENAI_API_KEY")

        # Validate config
        if not all([input_data_path, output_data_path, model_name, api_key]):
            raise ValueError("Missing required configuration values.")

        # Initialize model client and agents
        model_client = OpenAIChatCompletionClient(model=model_name, api_key=api_key)
        factory = AgentFactory(model_client, config_path=config_path)

        read_agent = factory.create_fs_read_agent(file_path=input_data_path)
        qa_agent = factory.create_qa_agent()
        write_agent = factory.create_fs_write_agent(file_path=output_data_path)

        # Setup team
        team = RoundRobinGroupChat(
            participants=[read_agent, qa_agent, write_agent],
            termination_condition=MaxMessageTermination(max_messages=10)
        )

        # Run collaboration
        await Console(team.run_stream(task=task_prompt_path.read_text()))

    except Exception as e:
        logger.error("Agent collaboration failed: %s", str(e), exc_info=True)


if __name__ == "__main__":
    asyncio.run(run_collaboration())