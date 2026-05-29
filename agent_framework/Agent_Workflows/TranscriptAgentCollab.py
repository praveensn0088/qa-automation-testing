import sys
import os
import time
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from metrics.llm_metrics import record_llm_usage
from metrics.metrics import AGENT_EXECUTION_TIME
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat.ui import Console
from pathlib import Path
from agent_framework.Agent_Workflows.DomainCollab import DomainAgentCollaboration
from agent_framework.agent_config.AgentFactory import AgentFactory, SummaryAgent
from agent_framework.agent_config.Mcp_config import Mcp_config
from agent_framework.agent_config.AgentFeedback import AgentFeedback
from agent_framework.utils.utils import config_path, load_prompt, route_subtask, visualize_subtask_agent_mapping,convert_to_serializable
from agent_framework.utils.logger import logger

subtask_status = {}

async def run_transcript_agent_collaboration(file_path:str, model:str, user_prompt:str):
    sys.stdout.reconfigure(encoding='utf-8')
    factory = None
    start = time.time()

    try:
        config_values = Mcp_config(config_path).config
        media_path = config_values.get("mediaData_path")
        output_path = config_values.get("outputData_path")
        auto_repo_path = config_values.get("auto_repo_path")
        task_prompt_path = Path(config_path.parent.parent / "agent_framework/prompts/task_prompts/Transcript_Requirements.txt")
        model_name = config_values.get("model_name")
        api_key = config_values.get("AZURE_OPENAI_API_KEY")
        AZURE_OPENAI_ENDPOINT = config_values.get("AZURE_OPENAI_ENDPOINT")
        api_type = config_values.get("api_type")
        api_version = config_values.get("AZURE_OPENAI_API_VERSION")
        AZURE_OPENAI_DEPLOYMENT_ID = config_values.get("AZURE_OPENAI_DEPLOYMENT_ID")

        model_client = OpenAIChatCompletionClient(
            model=model_name,
            api_key=api_key,
            base_url=AZURE_OPENAI_ENDPOINT,
            api_type=api_type,
            api_version=api_version,
            deployment_id=AZURE_OPENAI_DEPLOYMENT_ID,
            temperature=0.7
        )

        factory = AgentFactory(model_client, config_path=config_path)
        
        transcript_agent = factory.create_transcript_agent(config_values)
        
        # Run TranscriptAgent
        # transcript_result = await transcript_agent.run(task=transcript_task)
        transcript_result = await transcript_agent.run(file_path=file_path)
        print("Transcript Generated:\n", transcript_result)
        duration = time.time() - start
        AGENT_EXECUTION_TIME.labels(agent_name=transcript_agent.name).observe(duration)
        file_stem = Path(file_path).stem

        output_dir = "AIOutput\\specs\\transcript" 
        file_name = "transcript_" + file_stem + "_call.doc"
        os.makedirs(output_dir, exist_ok=True)

        file_path = os.path.join(output_dir, file_name)

        with open(os.path.join("inputData\\",file_path), "w", encoding="utf-8") as f:
            f.write(transcript_result)

        print(f"File written successfully at: {file_path}")
        # start = time.time()
        domain_collab = DomainAgentCollaboration(config_path, file_path, "transcript")

        response = await domain_collab.run_domain_team()
        # duration = time.time() - start
        # AGENT_EXECUTION_TIME.labels(agent_name="domain_agent").observe(duration)
        
        # record_llm_usage(agent_name="domain_agent", message = response)
        
        print(response)
        return response
       
    except Exception as e:
        logger.error("Agent collaboration failed: %s", str(e), exc_info=True)
