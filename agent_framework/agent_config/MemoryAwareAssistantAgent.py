from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from agent_framework.utils.logger import logger
from agent_framework.agent_config.AgentFeedback import AgentFeedback

class MemoryAwareAssistantAgent(AssistantAgent):
    def __init__(self, name, model_client, workbench, system_message,
                 short_term_memory=None, long_term_memory=None,
                 memory_enabled=True):
        super().__init__(name=name, model_client=model_client, workbench=workbench, system_message=system_message)
        self.stm = short_term_memory
        self.ltm = long_term_memory
        self.memory_enabled = memory_enabled
        self._system_message = system_message

        if self.memory_enabled:
            self.previous_context = self.recall("last_context", long_term=True)
            if self.previous_context:
                print(f"[{self.name}] Loaded previous context from LTM.")

    async def receive(self, message: TextMessage, sender: str) -> TextMessage:
        print(f"[{self.name}] Received message from {sender}: {message.content}")

        incoming_text = message.content
        context = self.recall("last_context", long_term=True)
        if context:
            task_text = f"Task Context:\n{context}\n\nIncoming Message:\n{incoming_text}"
        else:
            task_text = incoming_text

        self.remember_context(task_text)

        result = await self.run(task=task_text)

        if hasattr(result, "messages") and result.messages:
            last = result.messages[-1]
            content = getattr(last, "content", str(last))
        else:
            content = "No response generated."

        return TextMessage(content=content, source=self.name)

    def remember_context(self, context):
        if self.memory_enabled:
            self.remember("last_context", context, long_term=True)

    def remember(self, key, value, long_term=False):
        if long_term and self.ltm:
            self.ltm.save(f"{self.name}:{key}", value)
        elif self.stm:
            self.stm.update(f"{self.name}:{key}", value)

    def recall(self, key, long_term=False):
        if long_term and self.ltm:
            return self.ltm.retrieve(f"{self.name}:{key}")
        elif self.stm:
            return self.stm.get(f"{self.name}:{key}")
        return None

    def clear_memory(self, long_term=False):
        if not long_term and self.stm:
            self.stm.clear()

    def log_memory(self):
        stm_data = self.stm.memory if self.stm else {}
        ltm_data = self.ltm.all() if self.ltm else {}
        print(f"[{self.name}] STM: {stm_data}")
        print(f"[{self.name}] LTM: {ltm_data}")

    async def generate_feedback(self, task_id, result):
        if hasattr(result, "messages"):
            success = True
            message_parts = []
            for m in result.messages:
                content = getattr(m, "content", str(m))
                if isinstance(content, list):
                    content = "\n".join(str(item) for item in content)
                elif not isinstance(content, str):
                    content = str(content)
                message_parts.append(content)
            message = "\n".join(message_parts)
        else:
            message = result if isinstance(result, str) else str(result)
            success = "error" not in message.lower()
        return AgentFeedback(agent_name=self.name, task_id=task_id, success=success, message=message)

    async def send_feedback(self, feedback, workbench):
        await workbench.receive_feedback(feedback)
        self.remember(f"feedback:{feedback.task_id}", feedback.to_dict(), long_term=True)

    async def shutdown(self):
        if self.memory_enabled:
            self.clear_memory(long_term=False)
        print(f"[{self.name}] Shutdown completed.")

    async def retrieve_knowledge(self, query, top_k=5):
        """
        Retrieve relevant documents from ChromaDB using LTM.
        Returns a list of documents or an empty list if no results.
        """
        if self.ltm and self.ltm.use_chroma:
            try:
                results = self.ltm.chroma.query(query_text=query, top_k=top_k)
                documents = results.get("documents", [])
                if documents and documents[0]:
                    logger.info(f"[{self.name}] Retrieved {len(documents[0])} documents for query: {query}")
                    return documents[0]  # Flatten first batch
                else:
                    logger.warning(f"[{self.name}] No documents found for query: {query}")
                    return []
            except Exception as e:
                logger.exception(f"[{self.name}] Failed to retrieve knowledge: {e}")
                return []
        else:
            logger.warning(f"[{self.name}] ChromaDB not enabled or LTM missing.")
            return []