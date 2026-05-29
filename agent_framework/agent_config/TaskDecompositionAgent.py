import json
import random
import re
from agent_framework.agent_config.MemoryAwareAssistantAgent import MemoryAwareAssistantAgent
from agent_framework.utils.logger import logger
from autogen_core.models import UserMessage

from metrics.track_latency_agent import track_agent_latency


class TaskDecompositionAgent(MemoryAwareAssistantAgent):
    def __init__(self, name, model_client, short_term_memory, long_term_memory, system_message=None):
        system_message = (
            "You break complex work into smaller steps for a team of specialists. "
            "Output format: JSON array of step objects with task, type, and target_agent fields. "
            "Keep steps practical and sequential."
        )

        super().__init__(
            name=name,
            model_client=model_client,
            workbench=None,
            system_message=system_message,
            short_term_memory=short_term_memory,
            long_term_memory=long_term_memory,
            memory_enabled=True,
        )

        self._model_client = model_client
        self._long_term_memory = long_term_memory

    async def decompose_task(self, task_description: str, max_iterations: int = 5, threshold: float = 0.9) -> list:
        logger.info(f"Dynamically decomposing task: {task_description}")

        context = {
            "task_description": task_description,
            "iterations": 0,
            "subtasks": [],
            "feedback_score": 0.0,
            "agent_feedback": [],
        }

        while context["iterations"] < max_iterations and context["feedback_score"] < threshold:
            context["iterations"] += 1
            logger.info(f"Iteration {context['iterations']}")

            messages = [
                UserMessage(
                    content=(
                        "Decompose the task into subtasks.\n"
                        "Return ONLY JSON array. Each item must include:\n"
                        "- task (string)\n"
                        "- type (string)\n"
                        "- agent_hint (string)\n\n"
                        f"Task:\n{context['task_description']}\n\n"
                        f"Current subtasks:\n{json.dumps(context['subtasks'], ensure_ascii=False)}\n\n"
                        f"Agent feedback:\n{json.dumps(context['agent_feedback'], ensure_ascii=False)}\n"
                    ),
                    source="user",
                )
            ]

            try:
                response = await self._model_client.create(messages)
                content = getattr(response, "content", None)
                if content is None:
                    content = str(response)

                content_str = str(content).strip()
                if not content_str:
                    raise ValueError("Empty model response")

                content_str = self._extract_json_payload(content_str)
                subtasks = json.loads(content_str)

                if not isinstance(subtasks, list):
                    raise ValueError(f"Model response is not a list, got {type(subtasks)}")

                if (not subtasks) and context["iterations"] == 1:
                    logger.warning("Model returned empty list, using fallback")
                    context["subtasks"] = self._generate_fallback_subtasks(task_description)
                    break

                context["subtasks"] = subtasks

                feedback, score = await self.evaluate_subtasks(subtasks)
                if score is None:
                    score = 0.0

                context["agent_feedback"].append(feedback)
                context["feedback_score"] = float(score)

                logger.info(f"Feedback score: {context['feedback_score']:.2f}")

                if context["feedback_score"] >= threshold:
                    logger.info(f"Threshold {threshold} reached, stopping decomposition")
                    break

            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse or validate subtasks: {e}")
                if context["iterations"] == 1:
                    context["subtasks"] = self._generate_fallback_subtasks(task_description)
                    break
            except Exception as e:
                logger.error(f"Error in decomposition loop: {e}", exc_info=True)
                if context["iterations"] == 1:
                    context["subtasks"] = self._generate_fallback_subtasks(task_description)
                    break

        self._long_term_memory.save(f"decomposition:{task_description}", context["subtasks"])
        return context["subtasks"]

    def _extract_json_payload(self, text: str) -> str:
        m = re.search(r"``````", text, flags=re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return text.strip()

    def _generate_fallback_subtasks(self, task_description: str) -> list:
        return [
            {
                "task": task_description,
                "type": "direct",
                "agent_hint": "Process the full task directly without decomposition."
            }
        ]

    async def evaluate_subtasks(self, subtasks: list) -> tuple[str, float]:
        agent_responses = self.collect_feedback(subtasks)
        feedback = self.summarize_feedback(agent_responses)
        score = self.compute_quality_score(agent_responses)
        return feedback, score

    def collect_feedback(self, subtasks):
        feedback = []
        for subtask in subtasks:
            status = random.choice(["success", "partial", "failed"])
            feedback.append(
                {
                    "task": (subtask.get("task") if isinstance(subtask, dict) else str(subtask)),
                    "status": status,
                    "comments": f"Simulated feedback with status '{status}'.",
                }
            )
        return feedback

    def summarize_feedback(self, agent_responses):
        summary = "Summary of agent feedback:\n"
        for response in agent_responses:
            summary += f"- Task: {response['task']} | Status: {response['status']} | Comments: {response['comments']}\n"
        return summary

    def compute_quality_score(self, agent_responses):
        score_map = {"success": 1.0, "partial": 0.5, "failed": 0.0}
        if not agent_responses:
            return 0.0
        total_score = sum(score_map.get(resp.get("status"), 0.0) for resp in agent_responses)
        return total_score / len(agent_responses)
