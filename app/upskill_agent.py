import json


class UpskillAgent:
    """Interactive agent that guides user through upskilling process."""

    def __init__(self, llm):
        self.llm = llm
        self.context = {}

    def start(self, profile: dict, target_jd: str):
        self.context = {
            "profile": profile or {},
            "target_jd": target_jd or "",
            "conversation": [],
            "current_stage": "target_job_confirmation",
            "plan": "",
        }
        self._ask_target_job_confirmation()
        return self.context

    def _add_message(self, speaker: str, text: str):
        self.context["conversation"].append({"speaker": speaker, "text": text})

    def _ask_target_job_confirmation(self):
        prompt = (
            "User provided target job description:\n{jd}\n\n"
            "Ask one concise clarifying question to confirm main role, level, and key focus areas."
        ).format(jd=self.context.get("target_jd", "(none)"))
        resp = self.llm.generate(prompt)
        self._add_message("agent", resp)

    def handle_user_response(self, user_input: str):
        if not user_input.strip():
            return False
        self._add_message("user", user_input)
        self.context["user_target_job_response"] = user_input
        self.context["current_stage"] = "follow_ups"
        self._ask_follow_ups()
        return True

    def _ask_follow_ups(self):
        profile = self.context.get("profile", {})
        jd = self.context.get("target_jd", "")
        user_response = self.context.get("user_target_job_response", "")
        prompt = (
            "Based on:\n"
            "1. User profile JSON: {profile}\n"
            "2. Target job: {jd}\n"
            "3. User understanding: {user_response}\n\n"
            "Ask 3-4 focused follow-up questions to identify skill gaps, experience gaps, and realistic learning capacity."
        ).format(
            profile=json.dumps(profile, indent=0),
            jd=jd[:1500],
            user_response=user_response[:600],
        )
        resp = self.llm.generate(prompt)
        self._add_message("agent", resp)

    def handle_followup_response(self, user_input: str):
        if not user_input.strip():
            return False
        self._add_message("user", user_input)
        self.context["user_followup_response"] = user_input
        self.context["current_stage"] = "plan_generation"
        self._generate_plan()
        return True

    def _generate_plan(self):
        profile = self.context.get("profile", {})
        jd = self.context.get("target_jd", "")
        followup_answer = self.context.get("user_followup_response", "")
        prompt = (
            "Generate a practical upskill action plan with:\n"
            "- timeline (weeks/months)\n"
            "- specific skills to learn\n"
            "- learning resources and project ideas\n"
            "- checkpoints/milestones\n\n"
            "User Profile: {profile}\n"
            "Target Job: {jd}\n"
            "User Follow-up Answers: {followup_answer}"
        ).format(
            profile=json.dumps(profile, indent=0),
            jd=jd[:1500],
            followup_answer=followup_answer[:1200],
        )
        plan = self.llm.generate(prompt)
        self.context["plan"] = plan
        self.context["current_stage"] = "refinement"
        self._add_message("agent", f"Here is your personalized upskill action plan:\n\n{plan}")

    def refine_plan(self, refinement_input: str):
        if not refinement_input.strip():
            return False
        self._add_message("user", f"Refinement request: {refinement_input}")
        prompt = (
            "Refine this action plan based on the user's feedback.\n\n"
            "Current plan:\n{plan}\n\n"
            "User feedback: {feedback}"
        ).format(plan=self.context.get("plan", ""), feedback=refinement_input)
        refined_plan = self.llm.generate(prompt)
        self.context["plan"] = refined_plan
        self._add_message("agent", f"Here is the refined plan:\n\n{refined_plan}")
        return True
