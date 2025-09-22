from datetime import datetime

class DecisionLogger:
    def __init__(self, memory_service):
        self.memory = memory_service

    async def log_decision(self, decision_type, title, rationale, alternatives):
        content = f"""
        Decision: {title}
        Type: {decision_type}
        Date: {datetime.now().isoformat()}

        Rationale: {rationale}

        Alternatives Considered:
        {chr(10).join(f'- {alt}' for alt in alternatives)}
        """

        await self.memory.store(
            content=content,
            tags=['decision', decision_type, 'architecture']
        )