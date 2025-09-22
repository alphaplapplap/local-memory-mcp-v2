/**
 * Dynamic Context Updater
 * Orchestrates intelligent context updates during active conversations
 * Phase 2: Intelligent Context Updates
 */

const { analyzeConversation, detectTopicChanges } = require('./conversation-analyzer');
const { scoreMemoryRelevance } = require('./memory-scorer');
const { formatMemoriesForContext } = require('./context-formatter');
const { getSessionTracker } = require('./session-tracker');

/**
 * Dynamic Context Update Manager
 * Coordinates between conversation analysis, memory retrieval, and context injection
 */
class DynamicContextUpdater {
    constructor(options = {}) {
        this.options = {
            updateThreshold: 0.3,           // Minimum significance score to trigger update
            maxMemoriesPerUpdate: 3,        // Maximum memories to inject per update
            updateCooldownMs: 30000,        // Minimum time between updates (30 seconds)
            maxUpdatesPerSession: 10,       // Maximum updates per session
            debounceMs: 5000,               // Debounce rapid conversation changes
            enableCrossSessionContext: true, // Include cross-session intelligence
            ...options
        };

        this.lastUpdateTime = 0;
        this.updateCount = 0;
        this.conversationBuffer = '';
        this.lastAnalysis = null;
        this.loadedMemoryHashes = new Set();
        this.sessionTracker = null;
        this.debounceTimer = null;
    }

    /**
     * Initialize the dynamic context updater
     */
    async initialize(sessionContext = {}) {
        console.log('[Dynamic Context] Initializing dynamic context updater...');
        
        this.sessionContext = sessionContext;
        this.updateCount = 0;
        this.loadedMemoryHashes.clear();
        
        if (this.options.enableCrossSessionContext) {
            this.sessionTracker = getSessionTracker();
            await this.sessionTracker.initialize();
        }

        console.log('[Dynamic Context] Dynamic context updater initialized');
    }

    /**
     * Process conversation update and potentially inject new context
     * @param {string} conversationText - Current conversation content
     * @param {object} config - PostgreSQL and memory system configuration
     * @param {function} contextInjector - Function to inject context into conversation
     */
    async processConversationUpdate(conversationText, config, contextInjector) {
        try {
            // Check rate limiting
            if (!this.shouldProcessUpdate()) {
                return { processed: false, reason: 'rate_limited' };
            }

            // Debounce rapid updates
            if (this.debounceTimer) {
                clearTimeout(this.debounceTimer);
            }

            return new Promise((resolve) => {
                this.debounceTimer = setTimeout(async () => {
                    const result = await this.performContextUpdate(
                        conversationText,
                        config,
                        contextInjector
                    );
                    resolve(result);
                }, this.options.debounceMs);
            });

        } catch (error) {
            console.error('[Dynamic Context] Error processing conversation update:', error.message);
            return { processed: false, error: error.message };
        }
    }

    /**
     * Perform the actual context update
     */
    async performContextUpdate(conversationText, config, contextInjector) {
        console.log('[Dynamic Context] Processing conversation update...');

        // Analyze current conversation
        const currentAnalysis = analyzeConversation(conversationText, {
            extractTopics: true,
            extractEntities: true,
            detectIntent: true,
            detectCodeContext: true,
            minTopicConfidence: 0.3
        });

        // Detect significant changes
        const changes = detectTopicChanges(this.lastAnalysis, currentAnalysis);

        if (!changes.hasTopicShift || changes.significanceScore < this.options.updateThreshold) {
            console.log(`[Dynamic Context] No significant changes detected (score: ${changes.significanceScore.toFixed(2)})`);
            this.lastAnalysis = currentAnalysis;
            return { processed: false, reason: 'insufficient_change', significanceScore: changes.significanceScore };
        }

        console.log(`[Dynamic Context] Significant conversation change detected (score: ${changes.significanceScore.toFixed(2)})`);
        console.log(`[Dynamic Context] New topics: ${changes.newTopics.map(t => t.name).join(', ')}`);

        // Generate memory queries based on conversation changes
        const queries = this.generateMemoryQueries(currentAnalysis, changes);
        
        if (queries.length === 0) {
            this.lastAnalysis = currentAnalysis;
            return { processed: false, reason: 'no_actionable_queries' };
        }

        // Retrieve memories from PostgreSQL
        const memories = await this.retrieveRelevantMemories(queries, config);
        
        if (memories.length === 0) {
            this.lastAnalysis = currentAnalysis;
            return { processed: false, reason: 'no_relevant_memories' };
        }

        // Score memories with conversation context
        const scoredMemories = this.scoreMemoriesWithContext(memories, currentAnalysis);
        
        // Select top memories for injection
        const selectedMemories = scoredMemories
            .filter(memory => memory.relevanceScore > 0.3)
            .slice(0, this.options.maxMemoriesPerUpdate);

        if (selectedMemories.length === 0) {
            this.lastAnalysis = currentAnalysis;
            return { processed: false, reason: 'no_high_relevance_memories' };
        }

        // Track loaded memories to avoid duplicates
        selectedMemories.forEach(memory => {
            this.loadedMemoryHashes.add(memory.content_hash);
        });

        // Include cross-session context if enabled
        let crossSessionContext = null;
        if (this.options.enableCrossSessionContext && this.sessionTracker) {
            crossSessionContext = await this.sessionTracker.getConversationContext(
                this.sessionContext.projectContext,
                { maxPreviousSessions: 2, maxDaysBack: 3 }
            );
        }

        // Format context update
        const contextUpdate = this.formatContextUpdate(
            selectedMemories,
            currentAnalysis,
            changes,
            crossSessionContext
        );

        // Inject context into conversation
        if (contextInjector && typeof contextInjector === 'function') {
            await contextInjector(contextUpdate);
        }

        // Update state
        this.lastAnalysis = currentAnalysis;
        this.lastUpdateTime = Date.now();
        this.updateCount++;

        console.log(`[Dynamic Context] Context update completed (update #${this.updateCount})`);
        console.log(`[Dynamic Context] Injected ${selectedMemories.length} memories`);

        return {
            processed: true,
            updateCount: this.updateCount,
            memoriesInjected: selectedMemories.length,
            significanceScore: changes.significanceScore,
            topics: changes.newTopics.map(t => t.name),
            hasConversationContext: true,
            hasCrossSessionContext: !!crossSessionContext
        };
    }

    /**
     * Check if we should process an update based on rate limiting
     */
    shouldProcessUpdate() {
        const now = Date.now();
        
        // Check cooldown period
        if (now - this.lastUpdateTime < this.options.updateCooldownMs) {
            return false;
        }

        // Check maximum updates per session
        if (this.updateCount >= this.options.maxUpdatesPerSession) {
            return false;
        }

        return true;
    }

    /**
     * Generate memory queries from conversation analysis
     */
    generateMemoryQueries(analysis, changes) {
        const queries = [];

        // Query for new topics
        changes.newTopics.forEach(topic => {
            if (topic.confidence > 0.4) {
                queries.push({
                    query: topic.name,
                    type: 'topic',
                    weight: topic.confidence,
                    limit: 2
                });
            }
        });

        // Query for changed intent
        if (changes.changedIntents && analysis.intent && analysis.intent.confidence > 0.5) {
            queries.push({
                query: `${analysis.intent.name} ${this.sessionContext.projectContext?.name || ''}`,
                type: 'intent',
                weight: analysis.intent.confidence,
                limit: 1
            });
        }

        // Query for high-confidence entities
        analysis.entities
            .filter(entity => entity.confidence > 0.7)
            .slice(0, 2)
            .forEach(entity => {
                queries.push({
                    query: `${entity.name} ${entity.type}`,
                    type: 'entity',
                    weight: entity.confidence,
                    limit: 1
                });
            });

        // Sort by weight and limit total queries
        return queries
            .sort((a, b) => b.weight - a.weight)
            .slice(0, 4); // Maximum 4 queries per update
    }

    /**
     * Retrieve memories from PostgreSQL for multiple queries
     */
    async retrieveRelevantMemories(queries, config) {
        const allMemories = [];

        for (const queryObj of queries) {
            try {
                const memories = await this.queryPostgreSQLMemories(
                    queryObj.query,
                    config,
                    {
                        limit: queryObj.limit,
                        excludeHashes: Array.from(this.loadedMemoryHashes)
                    }
                );

                // Add query context to memories
                memories.forEach(memory => {
                    memory.queryContext = queryObj;
                });

                allMemories.push(...memories);

            } catch (error) {
                console.error(`[Dynamic Context] Failed to query memories for "${queryObj.query}":`, error.message);
            }
        }

        return allMemories;
    }

    /**
     * Query PostgreSQL memories directly
     */
    async queryPostgreSQLMemories(query, config, options = {}) {
        const { spawn } = require('child_process');

        return new Promise((resolve) => {
            const { limit = 3, excludeHashes = [] } = options;

            const searchScript = `
import psycopg2
import json
import sys

try:
    conn = psycopg2.connect(
        host='${config.postgres.host}',
        port=${config.postgres.port},
        database='${config.postgres.database}',
        user='${config.postgres.user}',
        password='${config.postgres.password}'
    )
    cursor = conn.cursor()

    search_query = '${query.replace(/'/g, "''")}'  # Escape single quotes

    # Search in default domain
    cursor.execute('''
        SELECT id, content, metadata, created_at, updated_at
        FROM default_memories
        WHERE to_tsvector('english', content) @@ plainto_tsquery('english', %s)
        ORDER BY updated_at DESC
        LIMIT %s
    ''', (search_query, ${limit}))

    results = []
    for row in cursor.fetchall():
        metadata = {}
        if row[2]:
            try:
                if isinstance(row[2], str):
                    metadata = json.loads(row[2])
                else:
                    metadata = row[2]
            except:
                metadata = {}

        results.append({
            'id': row[0],
            'content': row[1],
            'metadata': metadata,
            'created_at': row[3].isoformat() if row[3] else None,
            'updated_at': row[4].isoformat() if row[4] else None
        })

    conn.close()
    print(json.dumps(results))

except Exception as e:
    print(json.dumps({'error': str(e)}))
`;

            const python = spawn('python3', ['-c', searchScript]);
            let output = '';

            python.stdout.on('data', (data) => {
                output += data.toString();
            });

            python.on('close', (code) => {
                try {
                    const result = JSON.parse(output.trim());
                    if (result.error) {
                        console.error('[Dynamic Context] PostgreSQL query error:', result.error);
                        resolve([]);
                    } else {
                        // Filter out excluded hashes
                        const filteredMemories = result.filter(memory =>
                            !excludeHashes.includes(memory.content_hash)
                        );
                        resolve(filteredMemories);
                    }
                } catch (e) {
                    console.error('[Dynamic Context] Failed to parse PostgreSQL response:', e.message);
                    resolve([]);
                }
            });

            python.on('error', (error) => {
                console.error('[Dynamic Context] PostgreSQL query failed:', error.message);
                resolve([]);
            });

            setTimeout(() => {
                python.kill();
                resolve([]);
            }, config.postgres.timeout || 5000);
        });
    }


    /**
     * Score memories with enhanced conversation context
     */
    scoreMemoriesWithContext(memories, conversationAnalysis) {
        return scoreMemoryRelevance(memories, this.sessionContext.projectContext || {}, {
            includeConversationContext: true,
            conversationAnalysis: conversationAnalysis,
            weights: {
                timeDecay: 0.2,
                tagRelevance: 0.3,
                contentRelevance: 0.15,
                conversationRelevance: 0.35  // High weight for conversation context
            }
        });
    }

    /**
     * Format the context update message
     */
    formatContextUpdate(memories, analysis, changes, crossSessionContext) {
        let updateMessage = '\n🧠 **Dynamic Context Update**\n\n';

        // Explain the trigger
        if (changes.newTopics.length > 0) {
            updateMessage += `**New topics detected**: ${changes.newTopics.map(t => t.name).join(', ')}\n`;
        }
        if (changes.changedIntents && analysis.intent) {
            updateMessage += `**Focus shifted to**: ${analysis.intent.name}\n`;
        }
        updateMessage += '\n';

        // Add cross-session context if available
        if (crossSessionContext && crossSessionContext.recentSessions.length > 0) {
            updateMessage += '**Recent session context**:\n';
            crossSessionContext.recentSessions.slice(0, 2).forEach(session => {
                const timeAgo = this.formatTimeAgo(session.endTime);
                updateMessage += `• ${session.outcome?.type || 'Session'} completed ${timeAgo}\n`;
            });
            updateMessage += '\n';
        }

        // Add relevant memories
        updateMessage += '**Relevant context**:\n';
        memories.slice(0, 3).forEach((memory, index) => {
            const content = memory.content.length > 100 ? 
                memory.content.substring(0, 100) + '...' : 
                memory.content;
            
            const relevanceIndicator = memory.relevanceScore > 0.7 ? '🔥' : 
                                     memory.relevanceScore > 0.5 ? '⭐' : '💡';
            
            updateMessage += `${relevanceIndicator} ${content}\n`;
            
            if (memory.tags && memory.tags.length > 0) {
                updateMessage += `   *${memory.tags.slice(0, 3).join(', ')}*\n`;
            }
            updateMessage += '\n';
        });

        updateMessage += '---\n';
        return updateMessage;
    }

    /**
     * Format time ago for human readability
     */
    formatTimeAgo(timestamp) {
        const now = new Date();
        const time = new Date(timestamp);
        const diffMs = now - time;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 60) return `${diffMins} minutes ago`;
        if (diffHours < 24) return `${diffHours} hours ago`;
        if (diffDays < 7) return `${diffDays} days ago`;
        return time.toLocaleDateString();
    }

    /**
     * Get statistics about dynamic context updates
     */
    getStats() {
        return {
            updateCount: this.updateCount,
            loadedMemoriesCount: this.loadedMemoryHashes.size,
            lastUpdateTime: this.lastUpdateTime,
            hasSessionTracker: !!this.sessionTracker,
            isInitialized: !!this.sessionContext
        };
    }

    /**
     * Reset the updater state for a new conversation
     */
    reset() {
        console.log('[Dynamic Context] Resetting dynamic context updater');
        
        this.lastUpdateTime = 0;
        this.updateCount = 0;
        this.conversationBuffer = '';
        this.lastAnalysis = null;
        this.loadedMemoryHashes.clear();
        
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = null;
        }
    }
}

module.exports = {
    DynamicContextUpdater
};