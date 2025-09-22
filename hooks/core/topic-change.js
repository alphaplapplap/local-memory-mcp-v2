#!/usr/bin/env node

/**
 * Topic Change Hook for Claude Code
 * Handles context updates when conversation topics change
 *
 * Features:
 * - Dynamic topic change detection
 * - Automatic context refresh when topics shift
 * - Intelligent memory retrieval for new topics
 * - Context update formatting and injection
 * - Conversation flow analysis
 *
 * @version 2.0.0
 * @author Memory Awareness System
 */

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

// ANSI color codes for terminal output
const colors = {
    reset: '\x1b[0m',
    bright: '\x1b[1m',
    dim: '\x1b[2m',
    red: '\x1b[31m',
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    blue: '\x1b[34m',
    magenta: '\x1b[35m',
    cyan: '\x1b[36m',
    white: '\x1b[37m',
    gray: '\x1b[90m'
};

// Topic tracking state
let lastTopics = [];
let conversationHistory = [];
let topicChangeThreshold = 0.6;

/**
 * Configuration loader with fallback defaults
 */
function loadConfig() {
    const configPath = path.join(process.env.HOME || process.env.USERPROFILE, '.claude', 'hooks', 'config.json');

    const defaultConfig = {
        topicChange: {
            enabled: true,
            detectionThreshold: 0.6,
            maxContextMemories: 8,
            minTopicScore: 0.3,
            cooldownPeriod: 30000 // 30 seconds
        },
        memoryService: {
            enabled: true,
            timeout: 3000
        },
        postgres: {
            host: 'localhost',
            port: 5432,
            database: 'postgres',
            user: 'postgres',
            password: 'postgres'
        },
        verbosity: {
            enabled: true,
            showDetails: false
        }
    };

    try {
        if (fs.existsSync(configPath)) {
            const userConfig = JSON.parse(fs.readFileSync(configPath, 'utf8'));
            return { ...defaultConfig, ...userConfig };
        }
    } catch (error) {
        console.error(`${colors.yellow}⚠️  Failed to load config: ${error.message}${colors.reset}`);
    }

    return defaultConfig;
}

/**
 * Extract topics from conversation data
 */
function extractTopicsFromConversation(conversationData) {
    if (!conversationData || !Array.isArray(conversationData)) {
        return [];
    }

    const topics = new Set();
    const recentMessages = conversationData.slice(-5); // Focus on recent messages

    recentMessages.forEach(message => {
        if (!message.content) return;

        const content = message.content.toLowerCase();

        // Extract technical topics
        const techPatterns = [
            /implementing?\s+([a-zA-Z0-9\-_]{3,20})/g,
            /working on\s+([a-zA-Z0-9\-_\s]{3,30})/g,
            /using\s+([a-zA-Z0-9\-_]{3,20})/g,
            /building\s+([a-zA-Z0-9\-_\s]{3,30})/g,
            /creating\s+([a-zA-Z0-9\-_\s]{3,30})/g,
            /debugging\s+([a-zA-Z0-9\-_\s]{3,30})/g,
            /fixing\s+([a-zA-Z0-9\-_\s]{3,30})/g
        ];

        techPatterns.forEach(pattern => {
            let match;
            while ((match = pattern.exec(content)) !== null) {
                const topic = match[1].trim();
                if (topic.length > 2 && topic.length < 50) {
                    topics.add(topic);
                }
            }
        });

        // Extract technology and framework mentions
        const techKeywords = [
            'react', 'vue', 'angular', 'node', 'python', 'javascript', 'typescript',
            'postgresql', 'mysql', 'mongodb', 'redis', 'docker', 'kubernetes',
            'aws', 'azure', 'gcp', 'api', 'rest', 'graphql', 'microservices',
            'authentication', 'authorization', 'security', 'testing', 'deployment'
        ];

        techKeywords.forEach(keyword => {
            if (content.includes(keyword)) {
                topics.add(keyword);
            }
        });
    });

    return Array.from(topics);
}

/**
 * Calculate topic similarity between two topic sets
 */
function calculateTopicSimilarity(topics1, topics2) {
    if (topics1.length === 0 && topics2.length === 0) return 1.0;
    if (topics1.length === 0 || topics2.length === 0) return 0.0;

    const set1 = new Set(topics1.map(t => t.toLowerCase()));
    const set2 = new Set(topics2.map(t => t.toLowerCase()));

    const intersection = new Set([...set1].filter(x => set2.has(x)));
    const union = new Set([...set1, ...set2]);

    return intersection.size / union.size;
}

/**
 * Detect if a significant topic change has occurred
 */
function detectTopicChange(currentTopics, config) {
    if (lastTopics.length === 0) {
        lastTopics = [...currentTopics];
        return { changed: false, similarity: 1.0 };
    }

    const similarity = calculateTopicSimilarity(currentTopics, lastTopics);
    const changed = similarity < config.topicChange.detectionThreshold;

    if (changed) {
        if (config.verbosity.enabled && config.verbosity.showDetails) {
            console.log(`${colors.blue}📍 Topic change detected${colors.reset}`);
            console.log(`   Previous: [${lastTopics.join(', ')}]`);
            console.log(`   Current: [${currentTopics.join(', ')}]`);
            console.log(`   Similarity: ${similarity.toFixed(2)}`);
        }
        lastTopics = [...currentTopics];
    }

    return { changed, similarity, previousTopics: lastTopics, currentTopics };
}

/**
 * Generate search queries based on new topics
 */
function generateTopicQueries(topics, projectContext) {
    const queries = [];

    // Direct topic queries
    topics.forEach(topic => {
        queries.push(topic);

        // Combined topic + project queries
        if (projectContext && projectContext.name) {
            queries.push(`${topic} ${projectContext.name}`);
        }

        // Topic + language queries
        if (projectContext && projectContext.language && projectContext.language !== 'unknown') {
            queries.push(`${topic} ${projectContext.language}`);
        }
    });

    // Multi-topic queries for complex topics
    if (topics.length > 1) {
        queries.push(topics.slice(0, 3).join(' '));
    }

    // Context-aware queries
    queries.push('architecture decisions', 'best practices', 'common patterns');

    return queries;
}

/**
 * Query memories from PostgreSQL for specific topics
 */
async function queryMemoriesForTopics(queries, config) {
    const { spawn } = require('child_process');
    let allMemories = [];

    for (const query of queries.slice(0, 5)) { // Limit to 5 queries for performance
        const memories = await new Promise((resolve) => {
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
        LIMIT 3
    ''', (search_query,))

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
            'updated_at': row[4].isoformat() if row[4] else None,
            'query': search_query
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
                        resolve([]);
                    } else {
                        resolve(result);
                    }
                } catch (e) {
                    resolve([]);
                }
            });

            setTimeout(() => {
                python.kill();
                resolve([]);
            }, config.memoryService.timeout);
        });

        allMemories.push(...memories);
    }

    // Remove duplicates by ID
    const uniqueMemories = allMemories.filter((memory, index, self) =>
        index === self.findIndex(m => m.id === memory.id)
    );

    return uniqueMemories;
}

/**
 * Score memories for topic relevance
 */
function scoreMemoriesForTopics(memories, topics) {
    return memories.map(memory => {
        let score = 0.1; // Base score
        const factors = ['base'];

        // Topic relevance scoring
        const content = memory.content.toLowerCase();
        let topicMatches = 0;

        topics.forEach(topic => {
            if (content.includes(topic.toLowerCase())) {
                topicMatches++;
                score += 0.3;
                factors.push(`topic(${topic})`);
            }
        });

        // Multiple topic match bonus
        if (topicMatches > 1) {
            score += 0.2;
            factors.push('multi-topic');
        }

        // Recency bonus
        if (memory.updated_at) {
            const age = Date.now() - new Date(memory.updated_at).getTime();
            const daysSince = age / (1000 * 60 * 60 * 24);
            if (daysSince < 7) {
                score += 0.2;
                factors.push('recent');
            }
        }

        // Metadata type bonus
        if (memory.metadata && memory.metadata.type) {
            const typeBonus = {
                'decision': 0.3,
                'architecture': 0.25,
                'insights': 0.2,
                'preferences': 0.15
            };
            const bonus = typeBonus[memory.metadata.type] || 0;
            if (bonus > 0) {
                score += bonus;
                factors.push(`type(${memory.metadata.type})`);
            }
        }

        return {
            ...memory,
            topicRelevanceScore: Math.min(1.0, score),
            scoringFactors: factors
        };
    }).sort((a, b) => b.topicRelevanceScore - a.topicRelevanceScore);
}

/**
 * Format context update for injection
 */
function formatContextUpdate(memories, topics) {
    if (!memories || memories.length === 0) {
        return '';
    }

    let context = '\n<topic_context_update>\n';
    context += `Context update for topics: ${topics.join(', ')}\n\n`;

    // Group memories by type
    const groups = {
        decisions: [],
        architecture: [],
        insights: [],
        other: []
    };

    memories.forEach(memory => {
        const type = memory.metadata?.type || 'other';
        const group = groups[type] || groups.other;
        group.push(memory);
    });

    // Format each group
    Object.entries(groups).forEach(([type, items]) => {
        if (items.length === 0) return;

        const typeTitle = type.charAt(0).toUpperCase() + type.slice(1);
        context += `## ${typeTitle}\n`;

        items.forEach((memory, index) => {
            context += `${index + 1}. ${memory.content}\n`;
        });

        context += '\n';
    });

    context += '</topic_context_update>\n';
    return context;
}

/**
 * Detect project context (simplified version)
 */
function detectProjectContext(workingDir = process.cwd()) {
    const context = {
        directory: workingDir,
        name: path.basename(workingDir),
        language: 'unknown'
    };

    try {
        const files = fs.readdirSync(workingDir);
        const languageIndicators = {
            'package.json': 'javascript',
            'requirements.txt': 'python',
            'Cargo.toml': 'rust',
            'go.mod': 'go'
        };

        for (const file of files) {
            if (languageIndicators[file]) {
                context.language = languageIndicators[file];
                break;
            }
        }
    } catch (error) {
        // Ignore errors
    }

    return context;
}

/**
 * Main topic change handler
 */
async function onTopicChange(conversationData) {
    const config = loadConfig();

    if (!config.topicChange.enabled) {
        return { success: true, message: 'Topic change detection disabled' };
    }

    const startTime = Date.now();

    try {
        // Step 1: Extract current topics
        const currentTopics = extractTopicsFromConversation(conversationData);

        if (currentTopics.length === 0) {
            return { success: true, message: 'No topics detected' };
        }

        // Step 2: Detect topic change
        const changeDetection = detectTopicChange(currentTopics, config);

        if (!changeDetection.changed) {
            return {
                success: true,
                message: 'No significant topic change',
                similarity: changeDetection.similarity
            };
        }

        if (config.verbosity.enabled) {
            console.log(`${colors.bright}🔄 Topic Change Detected${colors.reset}`);
            console.log(`${colors.gray}Updating context for new topics...${colors.reset}\n`);
        }

        // Step 3: Get project context
        const projectContext = detectProjectContext();

        // Step 4: Generate search queries for new topics
        const queries = generateTopicQueries(currentTopics, projectContext);

        if (config.verbosity.enabled) {
            process.stdout.write(`${colors.blue}🔎 Searching for topic-relevant memories... ${colors.reset}`);
        }

        // Step 5: Query memories for new topics
        const memories = await queryMemoriesForTopics(queries, config);

        if (config.verbosity.enabled) {
            console.log(`${colors.green}✅ Found ${memories.length} memories${colors.reset}`);
        }

        // Step 6: Score and select relevant memories
        const scoredMemories = scoreMemoriesForTopics(memories, currentTopics);
        const relevantMemories = scoredMemories
            .filter(m => m.topicRelevanceScore >= config.topicChange.minTopicScore)
            .slice(0, config.topicChange.maxContextMemories);

        // Step 7: Format context update
        const contextUpdate = formatContextUpdate(relevantMemories, currentTopics);

        const elapsed = Date.now() - startTime;

        if (config.verbosity.enabled) {
            console.log(`${colors.green}🎉 Topic context update complete${colors.reset} ${colors.gray}(${elapsed}ms)${colors.reset}\n`);
        }

        return {
            success: true,
            contextUpdate,
            topicChange: changeDetection,
            memoriesFound: relevantMemories.length,
            topics: currentTopics,
            elapsed
        };

    } catch (error) {
        if (config.verbosity.enabled) {
            console.log(`${colors.red}❌ Topic change error: ${error.message}${colors.reset}\n`);
        }

        return {
            success: false,
            error: error.message
        };
    }
}

/**
 * Initialize topic tracking
 */
function initializeTopicTracking() {
    lastTopics = [];
    conversationHistory = [];
    topicChangeThreshold = 0.6;
}

/**
 * Reset topic tracking state
 */
function resetTopicTracking() {
    lastTopics = [];
    conversationHistory = [];
}

/**
 * Hook export for Claude Code
 */
module.exports = {
    name: 'topic-change-context-update',
    version: '2.0.0',
    description: 'Handles context updates when conversation topics change',
    trigger: 'topic-change',
    handler: onTopicChange,

    // Utility functions
    initializeTopicTracking,
    resetTopicTracking,

    // Export internals for testing
    _internal: {
        extractTopicsFromConversation,
        detectTopicChange,
        generateTopicQueries,
        scoreMemoriesForTopics,
        formatContextUpdate,
        calculateTopicSimilarity
    }
};

// Allow running directly for testing
if (require.main === module) {
    const testConversation = [
        { content: 'Working on implementing a PostgreSQL memory system for AI context' },
        { content: 'Now I need to set up Redis caching for better performance' },
        { content: 'Let me create a Docker configuration for the Redis setup' }
    ];

    (async () => {
        const result = await onTopicChange(testConversation);
        console.log('\nTest Result:', result);
    })();
}