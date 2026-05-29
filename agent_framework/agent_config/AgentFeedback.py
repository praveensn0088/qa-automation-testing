# agent_framework/agent_config/AgentFeedback.py

class AgentFeedback:
    def __init__(self, agent_name, task_id, success, message, suggestions=None):
        self.agent_name = agent_name
        self.task_id = task_id
        self.success = success
        self.message = message
        self.suggestions = suggestions or []

    def to_dict(self):
        return {
            "agent_name": self.agent_name,
            "task_id": self.task_id,
            "success": self.success,
            "message": self.message,
            "suggestions": self.suggestions
        }

    def __str__(self):
        return (
            f"AgentFeedback("
            f"agent_name='{self.agent_name}', "
            f"task_id='{self.task_id}', "
            f"success={self.success}, "
            f"message='{self.message}', "
            f"suggestions={self.suggestions})"
        )