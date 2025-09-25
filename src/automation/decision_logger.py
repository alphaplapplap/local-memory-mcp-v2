from datetime import datetime


class DecisionLogger:
    def __init__(self, memory_service=None):
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

        if self.memory:
            await self.memory.store(
                content=content, tags=["decision", decision_type, "architecture"]
            )
        else:
            # Fallback to simple logging if no memory service
            import logging

            logger = logging.getLogger(__name__)
            logger.info(f"Decision logged: {title} ({decision_type})")

    def log_decision_sync(self, title, category="general", importance=3):
        """Synchronous version for simple decision logging.

        Args:
            title: The decision title/description
            category: Category of the decision
            importance: Importance level (1-5)

        Returns:
            Dict with result information
        """
        content = f"""
        Decision: {title}
        Category: {category}
        Date: {datetime.now().isoformat()}
        Importance: {importance}
        """

        if self.memory:
            try:
                # Try to use memory service if available
                result = self.memory.store_memory(content, domain="decisions")
                return {"success": True, "memory_id": result}
            except Exception as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to store decision in memory: {e}")

        # Fallback to simple logging
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"Decision logged: {title} (category: {category}, importance: {importance})"
        )

        return {"success": True, "method": "logging_fallback"}
