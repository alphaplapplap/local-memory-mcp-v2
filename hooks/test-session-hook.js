#!/usr/bin/env node

/**
 * Complete Session Hook Demonstration
 * Shows the full memory processing pipeline from start to finish
 */

const path = require('path');
const { handler } = require('./core/session-start.js');

// Mock context that simulates a real Claude session
const mockContext = {
    workingDirectory: process.cwd(),
    sessionId: 'demo-session-' + Date.now(),
    userMessage: 'session hook git memory',
    trigger: 'session-start',

    // This function would normally inject memories into Claude
    injectSystemMessage: async (message) => {
        console.log('\n╔══════════════════════════════════════════════════════════════════╗');
        console.log('║              🧠 FINAL MEMORY CONTEXT OUTPUT                      ║');
        console.log('╚══════════════════════════════════════════════════════════════════╝');
        console.log(message);
        console.log('╚══════════════════════════════════════════════════════════════════╝\n');
    }
};

// Run the complete session hook
console.log('🚀 Starting Complete Session Hook Demonstration...\n');
console.log('This will show:');
console.log('  1. Project detection and confidence scoring');
console.log('  2. Storage backend detection');
console.log('  3. Git context analysis');
console.log('  4. Multi-phase memory retrieval');
console.log('  5. Memory scoring and ranking');
console.log('  6. Final formatted output\n');
console.log('═══════════════════════════════════════════════════════════════════\n');

handler(mockContext)
    .then(() => {
        console.log('\n✅ Session hook demonstration complete!');
    })
    .catch(error => {
        console.error('❌ Error:', error.message);
    });