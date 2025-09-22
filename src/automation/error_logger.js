// error_logger.js
class MemoryErrorLogger {
    constructor(memoryService) {
        this.memory = memoryService;
    }

    async logError(error, context) {
        // Store error details
        await this.memory.store({
            content: `Error: ${error.message}
Stack: ${error.stack}
Context: ${JSON.stringify(context)}`,
            tags: ['error', 'automated', context.service]
        });

        // Check for similar errors
        const similar = await this.memory.search(`error ${error.message.split(' ')[0]}`);
        if (similar.length > 0) {
            console.log('Similar errors found:', similar.length);
        }
    }
}

module.exports = MemoryErrorLogger;