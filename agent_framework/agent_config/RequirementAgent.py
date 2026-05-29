
from autogen_core.models import SystemMessage, UserMessage
from agent_framework.agent_config.MemoryAwareAssistantAgent import MemoryAwareAssistantAgent
from agent_framework.utils.utils import extract_model_response

import logging

class RequirementAgent(MemoryAwareAssistantAgent):
    def __init__(self, name, model_client, short_term_memory, long_term_memory, system_message=None):
        system_message = system_message or "You are a Requirement Extraction Agent. Convert transcript into functional and technical requirements."
        super().__init__(name, model_client, None, system_message, short_term_memory, long_term_memory, memory_enabled=True)
        self.model_client = model_client

    async def run(self, task):
        try:
            transcript = task.get("transcript")
            prompt = f"""
            Extract functional and technical requirements from the following transcript.
            Output in JSON format with keys: functional_requirements, technical_requirements.
            Transcript:
            {transcript}
            """

            messages = [
                SystemMessage(content="You are a Requirement Extraction Agent."),
                UserMessage(content=prompt, source="user")
            ]

            # Call model client
            response = await self.model_client.create(messages=messages)
            logging.info(f"Raw response: {response}")

            # Use reusable helper to normalize response
            requirements = extract_model_response(response)

            # Save clean data to memory
            self.remember("last_requirements", requirements, long_term=True)

            logging.info("Requirements successfully stored in memory.")
            return requirements

        except Exception as e:
            logging.exception("Error in RequirementAgent.run()")
            return {"error": str(e)}
