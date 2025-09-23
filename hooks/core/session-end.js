/**
 * Claude Code Session End Hook
 * Automatically consolidates session outcomes and stores them as memories
 */

const fs = require('fs').promises;
const path = require('path');
const https = require('https');
const http = require('http');

// Import utilities
const { detectProjectContext } = require('../utilities/project-detector');
const { formatSessionConsolidation } = require('../utilities/context-formatter');

/**
 * Load hook configuration
 */
async function loadConfig() {
    try {
        const configPath = path.join(__dirname, '../config.json');
        const configData = await fs.readFile(configPath, 'utf8');
        return JSON.parse(configData);
    } catch (error) {
        console.warn('[Memory Hook] Using default configuration:', error.message);
        return {
            memoryService: {
                endpoint: 'http://localhost:8000',
                apiKey: 'test-key-123',
                defaultTags: ['claude-code', 'auto-generated'],
                enableSessionConsolidation: true
            },
            sessionAnalysis: {
                extractTopics: true,
                extractDecisions: true,
                extractInsights: true,
                extractCodeChanges: true,
                extractNextSteps: true,
                minSessionLength: 100 // Minimum characters for meaningful session
            }
        };
    }
}

/**
 * Analyze conversation to extract key information
 */
function analyzeConversation(conversationData) {
    try {
        const analysis = {
            topics: [],
            decisions: [],
            insights: [],
            codeChanges: [],
            nextSteps: [],
            sessionLength: 0,
            confidence: 0
        };
        
        if (!conversationData || !conversationData.messages) {
            return analysis;
        }
        
        const messages = conversationData.messages;
        const conversationText = messages.map(msg => msg.content || '').join('\n').toLowerCase();
        analysis.sessionLength = conversationText.length;
        
        // Extract topics (simple keyword matching)
        const topicKeywords = {
            'implementation': /implement|implementing|implementation|build|building|create|creating/g,
            'debugging': /debug|debugging|bug|error|fix|fixing|issue|problem/g,
            'architecture': /architecture|design|structure|pattern|framework|system/g,
            'performance': /performance|optimization|speed|memory|efficient|faster/g,
            'testing': /test|testing|unit test|integration|coverage|spec/g,
            'deployment': /deploy|deployment|production|staging|release/g,
            'configuration': /config|configuration|setup|environment|settings/g,
            'database': /database|db|sql|query|schema|migration/g,
            'api': /api|endpoint|rest|graphql|service|interface/g,
            'ui': /ui|interface|frontend|component|styling|css|html/g
        };
        
        Object.entries(topicKeywords).forEach(([topic, regex]) => {
            if (conversationText.match(regex)) {
                analysis.topics.push(topic);
            }
        });
        
        // Extract decisions (look for decision language)
        const decisionPatterns = [
            /decided to|decision to|chose to|choosing|will use|going with/g,
            /better to|prefer|recommend|should use|opt for/g,
            /concluded that|determined that|agreed to/g
        ];
        
        messages.forEach(msg => {
            const content = (msg.content || '').toLowerCase();
            decisionPatterns.forEach(pattern => {
                const matches = content.match(pattern);
                if (matches) {
                    // Extract sentences containing decisions
                    const sentences = msg.content.split(/[.!?]+/);
                    sentences.forEach(sentence => {
                        if (pattern.test(sentence.toLowerCase()) && sentence.length > 20) {
                            analysis.decisions.push(sentence.trim());
                        }
                    });
                }
            });
        });
        
        // Extract insights (look for learning language)
        const insightPatterns = [
            /learned that|discovered|realized|found out|turns out/g,
            /insight|understanding|conclusion|takeaway|lesson/g,
            /important to note|key finding|observation/g
        ];
        
        messages.forEach(msg => {
            const content = (msg.content || '').toLowerCase();
            insightPatterns.forEach(pattern => {
                if (pattern.test(content)) {
                    const sentences = msg.content.split(/[.!?]+/);
                    sentences.forEach(sentence => {
                        if (pattern.test(sentence.toLowerCase()) && sentence.length > 20) {
                            analysis.insights.push(sentence.trim());
                        }
                    });
                }
            });
        });
        
        // Extract code changes (look for technical implementations)
        const codePatterns = [
            /added|created|implemented|built|wrote/g,
            /modified|updated|changed|refactored|improved/g,
            /fixed|resolved|corrected|patched/g
        ];
        
        messages.forEach(msg => {
            const content = msg.content || '';
            if (content.includes('```') || /\.(js|py|rs|go|java|cpp|c|ts|jsx|tsx)/.test(content)) {
                // This message contains code
                const lowerContent = content.toLowerCase();
                codePatterns.forEach(pattern => {
                    if (pattern.test(lowerContent)) {
                        const sentences = content.split(/[.!?]+/);
                        sentences.forEach(sentence => {
                            if (pattern.test(sentence.toLowerCase()) && sentence.length > 15) {
                                analysis.codeChanges.push(sentence.trim());
                            }
                        });
                    }
                });
            }
        });
        
        // Extract next steps (look for future language)
        const nextStepsPatterns = [
            /next|todo|need to|should|will|plan to|going to/g,
            /follow up|continue|proceed|implement next|work on/g,
            /remaining|still need|outstanding|future/g
        ];
        
        messages.forEach(msg => {
            const content = (msg.content || '').toLowerCase();
            nextStepsPatterns.forEach(pattern => {
                if (pattern.test(content)) {
                    const sentences = msg.content.split(/[.!?]+/);
                    sentences.forEach(sentence => {
                        if (pattern.test(sentence.toLowerCase()) && sentence.length > 15) {
                            analysis.nextSteps.push(sentence.trim());
                        }
                    });
                }
            });
        });
        
        // Calculate confidence based on extracted information
        const totalExtracted = analysis.topics.length + analysis.decisions.length + 
                              analysis.insights.length + analysis.codeChanges.length + 
                              analysis.nextSteps.length;
        
        analysis.confidence = Math.min(1.0, totalExtracted / 10); // Max confidence at 10+ items
        
        // Limit arrays to prevent overwhelming output
        analysis.topics = analysis.topics.slice(0, 5);
        analysis.decisions = analysis.decisions.slice(0, 3);
        analysis.insights = analysis.insights.slice(0, 3);
        analysis.codeChanges = analysis.codeChanges.slice(0, 4);
        analysis.nextSteps = analysis.nextSteps.slice(0, 4);
        
        return analysis;
        
    } catch (error) {
        console.error('[Memory Hook] Error analyzing conversation:', error.message);
        return {
            topics: [],
            decisions: [],
            insights: [],
            codeChanges: [],
            nextSteps: [],
            sessionLength: 0,
            confidence: 0,
            error: error.message
        };
    }
}

/**
 * Call MCP service tools
 */
async function callMCPService(endpoint, apiKey, toolName, arguments_) {
    return new Promise((resolve, reject) => {
        const url = new URL('/mcp', endpoint);

        const postData = JSON.stringify({
            jsonrpc: '2.0',
            id: 1,
            method: 'tools/call',
            params: {
                name: toolName,
                arguments: arguments_
            }
        });

        const options = {
            hostname: url.hostname,
            port: url.port || (url.protocol === 'https:' ? 8443 : 8000),
            path: url.pathname,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(postData),
                'Authorization': `Bearer ${apiKey}`
            },
            rejectUnauthorized: false // For self-signed certificates
        };

        // Use http or https based on URL protocol
        const requestModule = url.protocol === 'https:' ? https : http;
        const req = requestModule.request(options, (res) => {
            let data = '';
            res.on('data', (chunk) => {
                data += chunk;
            });
            res.on('end', () => {
                try {
                    const response = JSON.parse(data);
                    if (response.result) {
                        resolve(response.result);
                    } else {
                        resolve({ success: false, error: 'No result in response', data });
                    }
                } catch (parseError) {
                    resolve({ success: false, error: 'Parse error', data });
                }
            });
        });

        req.on('error', (error) => {
            resolve({ success: false, error: error.message });
        });

        req.write(postData);
        req.end();
    });
}

/**
 * Store session consolidation as memory
 */
async function storeSessionMemory(endpoint, apiKey, content, projectContext, analysis, sessionId) {
    // Use MCP store_memory tool instead of direct API call
    const metadata = {
        source: 'session-end-hook',
        session_analysis: {
            topics: analysis.topics,
            decisions_count: analysis.decisions.length,
            insights_count: analysis.insights.length,
            code_changes_count: analysis.codeChanges.length,
            next_steps_count: analysis.nextSteps.length,
            session_length: analysis.sessionLength,
            confidence: analysis.confidence
        },
        project_context: {
            name: projectContext.name,
            language: projectContext.language,
            frameworks: projectContext.frameworks
        },
        session_id: sessionId,
        generated_by: 'claude-code-session-end-hook',
        generated_at: new Date().toISOString(),
        tags: [
            'claude-code-session',
            'session-consolidation',
            projectContext.name,
            `language:${projectContext.language}`,
            ...analysis.topics.slice(0, 3), // Top 3 topics as tags
            ...projectContext.frameworks.slice(0, 2), // Top 2 frameworks
            `confidence:${Math.round(analysis.confidence * 100)}`
        ].filter(Boolean)
    };

    return await callMCPService(endpoint, apiKey, 'store_memory', {
        content: content,
        domain: 'default',
        metadata: metadata,
        importance: Math.round(analysis.confidence * 10) // 0-10 scale
    });
}

/**
 * Main session end hook function
 */
async function onSessionEnd(context) {
    try {
        console.log('[Memory Hook] Session ending - consolidating outcomes...');
        
        // Load configuration
        const config = await loadConfig();
        
        if (!config.memoryService.enableSessionConsolidation) {
            console.log('[Memory Hook] Session consolidation disabled in config');
            return;
        }
        
        // Check if session is meaningful enough to store
        if (context.conversation && context.conversation.messages) {
            const totalLength = context.conversation.messages
                .map(msg => (msg.content || '').length)
                .reduce((sum, len) => sum + len, 0);
                
            if (totalLength < config.sessionAnalysis.minSessionLength) {
                console.log('[Memory Hook] Session too short for consolidation');
                return;
            }
        }
        
        // Detect project context
        const projectContext = await detectProjectContext(context.workingDirectory || process.cwd());
        console.log(`[Memory Hook] Consolidating session for project: ${projectContext.name}`);
        
        // Analyze conversation
        const analysis = analyzeConversation(context.conversation);
        
        if (analysis.confidence < 0.1) {
            console.log('[Memory Hook] Session analysis confidence too low, skipping consolidation');
            return;
        }
        
        console.log(`[Memory Hook] Session analysis: ${analysis.topics.length} topics, ${analysis.decisions.length} decisions, confidence: ${(analysis.confidence * 100).toFixed(1)}%`);
        
        // Try to get active session info or find recent session
        let sessionId = context.sessionId; // If provided by context
        let sessionInfo = null;

        if (!sessionId) {
            // Try to find recent active session for this project
            try {
                const sessions = await callMCPService(
                    config.memoryService.endpoint,
                    config.memoryService.apiKey,
                    'get_session_history',
                    {
                        project_name: projectContext.name,
                        limit: 1
                    }
                );

                if (sessions && sessions.recent_sessions && sessions.recent_sessions.length > 0) {
                    const lastSession = sessions.recent_sessions[0];
                    if (lastSession.status === 'active') {
                        sessionId = lastSession.id;
                        sessionInfo = lastSession;
                    }
                }
            } catch (error) {
                console.log('[Memory Hook] Could not retrieve session info');
            }
        }

        // Format session consolidation
        const consolidation = formatSessionConsolidation(analysis, projectContext);

        // End the session if we have session tracking
        if (sessionId) {
            try {
                const endResult = await callMCPService(
                    config.memoryService.endpoint,
                    config.memoryService.apiKey,
                    'end_session',
                    {
                        session_id: sessionId,
                        final_topics: analysis.topics,
                        conversation_summary: consolidation.slice(0, 500), // Truncate for summary
                        outcome_type: analysis.confidence > 0.7 ? 'completed' : 'partial'
                    }
                );

                if (endResult && !endResult.error) {
                    console.log(`[Memory Hook] Session ${sessionId} ended successfully`);
                } else {
                    console.log(`[Memory Hook] Failed to end session: ${endResult?.error || 'Unknown error'}`);
                }
            } catch (error) {
                console.log(`[Memory Hook] Error ending session: ${error.message}`);
            }
        }

        // Store session consolidation as memory if confidence is high enough
        if (analysis.confidence > 0.3) {
            const result = await storeSessionMemory(
                config.memoryService.endpoint,
                config.memoryService.apiKey,
                consolidation,
                projectContext,
                analysis,
                sessionId
            );

            if (result && (result.success || result.content_hash || result.id)) {
                const memoryId = result.id || result.content_hash;
                console.log(`[Memory Hook] Session consolidation stored successfully: ${memoryId}`);

                // Track the summary memory with the session if we have session ID
                if (sessionId && memoryId) {
                    try {
                        await callMCPService(
                            config.memoryService.endpoint,
                            config.memoryService.apiKey,
                            'track_session_memory',
                            {
                                session_id: sessionId,
                                memory_id: memoryId,
                                domain: 'default',
                                created_during_session: true,
                                interaction_type: 'created',
                                relevance_score: analysis.confidence
                            }
                        );
                    } catch (error) {
                        // Silently handle tracking errors
                    }
                }
            } else {
                console.warn('[Memory Hook] Failed to store session consolidation:', result?.error || 'Unknown error');
            }
        } else {
            console.log('[Memory Hook] Session confidence too low for memory storage');
        }
        
    } catch (error) {
        console.error('[Memory Hook] Error in session end:', error.message);
        // Fail gracefully - don't prevent session from ending
    }
}

/**
 * Hook metadata for Claude Code
 */
module.exports = {
    name: 'memory-awareness-session-end',
    version: '1.0.0',
    description: 'Automatically consolidate and store session outcomes',
    trigger: 'session-end',
    handler: onSessionEnd,
    config: {
        async: true,
        timeout: 15000, // 15 second timeout
        priority: 'normal'
    }
};

// Direct execution support for testing
if (require.main === module) {
    // Test the hook with mock context
    const mockConversation = {
        messages: [
            {
                role: 'user',
                content: 'I need to implement a memory awareness system for Claude Code'
            },
            {
                role: 'assistant',
                content: 'I\'ll help you create a memory awareness system. We decided to use hooks for session management and implement automatic context injection.'
            },
            {
                role: 'user', 
                content: 'Great! I learned that we need project detection and memory scoring algorithms.'
            },
            {
                role: 'assistant',
                content: 'Exactly. I implemented the project detector in project-detector.js and created scoring algorithms. Next we need to test the complete system.'
            }
        ]
    };
    
    const mockContext = {
        workingDirectory: process.cwd(),
        sessionId: 'test-session',
        conversation: mockConversation
    };
    
    onSessionEnd(mockContext)
        .then(() => console.log('Session end hook test completed'))
        .catch(error => console.error('Session end hook test failed:', error));
}