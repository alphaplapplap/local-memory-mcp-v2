const fs = require('fs');
const path = require('path');

console.log('\n╔══════════════════════════════════════════════════════════════════╗');
console.log('║     🧠 COMPLETE SESSION HOOK MEMORY PROCESSING DEMONSTRATION     ║');
console.log('╚══════════════════════════════════════════════════════════════════╝\n');

// Step 1: Show stored memories
console.log('📦 STEP 1: MEMORIES IN DATABASE');
console.log('================================');
const { execSync } = require('child_process');
const memories = execSync('cd /Users/linuxbabe/local-memory-mcp && python3 -c "import sys; sys.path.append(\'src\'); from postgres_memory_api import PostgresMemoryAPI; from ollama_embeddings import OllamaEmbeddings; api = PostgresMemoryAPI(ollama_embeddings=OllamaEmbeddings()); results = api.retrieve_memories(\'session hook\', 8, \'local-memory-mcp\'); [print(f\'  • {r[\"content\"][:80]}...\') for r in results]"', { encoding: 'utf8' });
console.log(memories);

// Step 2: Show processing phases
console.log('\n🔄 STEP 2: MULTI-PHASE MEMORY RETRIEVAL');
console.log('========================================');
console.log('  ⚡ Phase 0: Git-aware context (analyzes recent commits)');
console.log('  🕒 Phase 1: Recent memories (60% allocation, last week)');
console.log('  🎯 Phase 2: Important tagged memories (architecture/decisions)');
console.log('  🔄 Phase 3: Fallback context (general project memories)');

// Step 3: Show scoring algorithm
console.log('\n📊 STEP 3: MEMORY SCORING ALGORITHM');
console.log('====================================');
console.log('  Scoring factors:');
console.log('    • Time decay: 25% weight (recent = higher score)');
console.log('    • Tag relevance: 35% weight (project match)');
console.log('    • Content relevance: 15% weight (semantic similarity)');
console.log('    • Content quality: 25% weight (non-generic content)');

// Step 4: Run actual hook
console.log('\n🚀 STEP 4: RUNNING SESSION HOOK');
console.log('================================\n');

// Override to show full processing
process.chdir('/Users/linuxbabe/local-memory-mcp');
const hook = require('./hooks/core/session-start.js');

const mockContext = {
    workingDirectory: process.cwd(),
    sessionId: 'demo-' + Date.now(),
    userMessage: 'session hook memory git',
    injectSystemMessage: async (message) => {
        console.log('\n╔══════════════════════════════════════════════════════════════════╗');
        console.log('║                    📝 FINAL FORMATTED OUTPUT                      ║');
        console.log('╚══════════════════════════════════════════════════════════════════╝');
        
        // Parse and display the formatted message
        const lines = message.split('\n');
        lines.forEach(line => {
            if (line.includes('Memory Context')) {
                console.log('\n🧠 ' + line);
            } else if (line.includes('Project:')) {
                console.log('📂 ' + line);
            } else if (line.includes('Storage:')) {
                console.log('💾 ' + line);
            } else if (line.includes('memories loaded')) {
                console.log('📚 ' + line);
            } else if (line.includes('•')) {
                console.log('  ' + line);
            } else {
                console.log(line);
            }
        });
    }
};

hook.handler(mockContext).then(() => {
    console.log('\n✅ Demonstration complete!');
});
