# 🧠 Session Start Injection Map

## Overview
This document maps out everything that gets injected into Claude sessions during startup, including the order, dependencies, and data flow.

## 📊 Injection Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    SESSION START TRIGGER                        │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. CONFIGURATION LOADING                                        │
│    ├─ Load config.json                                          │
│    ├─ Set verbosity flags (verbose, cleanMode, showMemoryDetails) │
│    └─ Set display modes (sourceDisplayMode, showProjectDetails) │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. PROJECT CONTEXT DETECTION                                    │
│    ├─ Detect project name (Git repo name or folder name)       │
│    ├─ Detect language(s) and frameworks                         │
│    ├─ Detect Git information (branch, last commit)              │
│    └─ Display: 📂 Project → [name] ([language])                 │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. STORAGE BACKEND DETECTION                                    │
│    ├─ Health check (if enabled)                                │
│    ├─ Parse storage info (backend, location, status)           │
│    ├─ Fallback to config detection if health check fails       │
│    └─ Display: 💾 Storage → [icon] [description]               │
│        └─ 📍 Path → [location]                                 │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. GIT CONTEXT ANALYSIS                                         │
│    ├─ Analyze recent commits (last 14 days, max 20 commits)    │
│    ├─ Extract development keywords                              │
│    ├─ Check for changelog entries                              │
│    └─ Display: 📊 Git Context → [X] commits, [Y] changelog     │
│        └─ 🔑 Keywords → [top 5 keywords]                       │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. MULTI-PHASE MEMORY RETRIEVAL                                │
│    │                                                             │
│    ├─ Phase 0: Git Context Phase (NEW - highest priority)      │
│    │   ├─ Build git context queries from development keywords   │
│    │   ├─ Execute git-context queries (max 2, 3 memories each) │
│    │   ├─ Mark memories with _gitContextType                    │
│    │   └─ Display: ⚡ Phase 0 → Git-aware memory search         │
│    │                                                             │
│    ├─ Phase 1: Recent Memories (high priority)                  │
│    │   ├─ Build enhanced semantic query with git context        │
│    │   ├─ Search recent memories (last-week, 60% of slots)     │
│    │   └─ Display: 🕒 Phase 1 → Searching recent memories       │
│    │                                                             │
│    ├─ Phase 2: Important Tagged Memories                        │
│    │   ├─ Search for key-decisions, architecture, etc.          │
│    │   ├─ Fill remaining slots                                  │
│    │   └─ Display: 🎯 Phase 2 → Searching important tagged     │
│    │                                                             │
│    └─ Phase 3: Fallback General Context                         │
│        ├─ Search general project context                        │
│        ├─ Only if still need more memories                      │
│        └─ Display: 🔄 Phase 3 → Fallback general context       │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. MEMORY PROCESSING & SCORING                                  │
│    ├─ Analyze memory recency (count recent memories)           │
│    ├─ Score memories for relevance                             │
│    ├─ Display: 📚 Memory Search → Found [X] relevant memories  │
│    ├─ Display: 📋 Git Query → [recent-development] found [Y]   │
│    └─ Display: 🎯 Scoring → Top relevance: [scores]            │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. CONTEXT FORMATTING & INJECTION                               │
│    ├─ Format memories for context injection                    │
│    ├─ Include storage info, timestamps, categorization         │
│    ├─ Inject via context.injectSystemMessage()                 │
│    └─ Display: ✅ Memory Hook → Context injected ([X] memories) │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ 8. FALLBACK DISPLAY (if injection fails)                       │
│    ├─ Display formatted box with memory context                │
│    ├─ Show memories for manual copying                         │
│    └─ Display: 🧠 Injected Memory Context                      │
└─────────────────────────────────────────────────────────────────┘
```

## 🔧 Configuration Options

### Memory Service Configuration
```json
{
  "memoryService": {
    "endpoint": "http://localhost:8000",
    "apiKey": "test-key-123",
    "maxMemoriesPerSession": 8,
    "recentFirstMode": true,
    "recentMemoryRatio": 0.6,
    "recentTimeWindow": "last-week",
    "fallbackTimeWindow": "last-month"
  }
}
```

### Output Configuration
```json
{
  "output": {
    "verbose": true,
    "cleanMode": false,
    "showMemoryDetails": false,
    "showProjectDetails": true,
    "showPhaseDetails": true,
    "showGitAnalysis": true
  }
}
```

### Git Analysis Configuration
```json
{
  "gitAnalysis": {
    "enabled": true,
    "commitLookback": 14,
    "maxCommits": 20,
    "includeChangelog": true,
    "maxGitMemories": 3,
    "gitContextWeight": 1.2
  }
}
```

## 📋 Data Structures

### Project Context
```javascript
{
  name: "project-name",
  language: "JavaScript",
  frameworks: ["Node.js", "Express"],
  git: {
    branch: "main",
    lastCommit: "abc123",
    repository: "user/repo"
  }
}
```

### Git Context
```javascript
{
  commits: [...],
  changelogEntries: [...],
  repositoryActivity: {...},
  developmentKeywords: {
    keywords: ["refactor", "fix", "feat"],
    weights: {...}
  }
}
```

### Storage Info
```javascript
{
  backend: "postgresql",
  type: "local",
  location: "postgresql://localhost:5432/memory_db",
  description: "PostgreSQL (Connected)",
  icon: "🐘",
  health: {
    status: "connected",
    totalMemories: 10,
    databaseSizeMB: 11.1,
    uniqueTags: 5
  }
}
```

### Memory Object
```javascript
{
  id: "memory-id",
  content: "Memory content...",
  created_at_iso: "2024-01-01T00:00:00Z",
  tags: ["tag1", "tag2"],
  _gitContextType: "recent-development", // Added by Phase 0
  _gitContextSource: "git-analysis",
  _gitContextWeight: 1.2
}
```

## 🎯 Display Output Examples

### Normal Mode (verbose: true, cleanMode: false)
```
🧠 Memory Hook → Initializing session awareness...
📂 Project → local-memory-mcp (JavaScript)
💾 Storage → 🐘 PostgreSQL (Connected) • 10 memories • 11.1MB
📍 Path → postgresql://localhost:5432/memory_db
📊 Git Analysis → Analyzing repository context...
📊 Git Context → 10 commits, 0 changelog entries
🔑 Keywords → refactor, chore, fix, feat, test
⚡ Phase 0 → Git-aware memory search (3 slots, 4 queries)
🕒 Phase 1 → Searching recent memories (last-week, 3 slots)
🎯 Phase 2 → Searching important tagged memories (5 slots)
📚 Memory Search → Found 3 relevant memories (2 recent)
📋 Git Query → [recent-development] found 3 memories
🎯 Scoring → Top relevance: 85%🕒, 78%📅, 72%
🔄 Processing → 3 memories selected
✅ Memory Hook → Context injected (3 memories)
```

### Clean Mode (cleanMode: true)
```
📂 Project → local-memory-mcp (JavaScript)
💾 Storage → 🐘 PostgreSQL (Connected)
📊 Git Context → 10 commits, 0 changelog entries
📚 Memory Search → Found 3 relevant memories
✅ Memory Hook → Context injected (3 memories)
```

### Fallback Mode (when injection fails)
```
╭────────────────────────────────────────────────────────────────────────────────╮
│ 🧠 Injected Memory Context                                                      │
╰────────────────────────────────────────────────────────────────────────────────╯
┌─ 🧠 Memory Context → node-project, npm
│
├─ 🐘 postgresql (Connected) (10 memories, 11.1MB)
├─ 📍 postgresql://localhost:5432/memory_db
├─ 📚 3 memories loaded
│
├─ This memory should now be automatically routed to the local-memory-mcp-v2 domain
├─ This memory should be automatically routed to the local-memory-mcp domain
└─ This is another test memory to verify the auto-routing is working consistently

╰────────────────────────────────────────────────────────────────────────────────╯
```

## 🔍 Debugging Tips

### Common Issues
1. **Missing Memory Context**: Check if `context.injectSystemMessage` is available
2. **Git Query not showing**: Ensure `showMemoryDetails` is true and git memories exist
3. **Storage info missing**: Check health check configuration and endpoint connectivity
4. **Project detection failing**: Verify project detector can access Git and package files

### Debug Flags
- Set `showMemoryDetails: true` to see detailed memory processing
- Set `verbose: true` to see all debug output
- Set `cleanMode: false` to see full output (default)

### Log Locations
- Hook logs: Console output during session start
- Memory service logs: Check server logs at configured endpoint
- Git analysis logs: Console output during git context analysis

## 🚀 Performance Considerations

### Memory Retrieval Phases
- **Phase 0**: Git context (3 memories max, 2 queries max)
- **Phase 1**: Recent memories (60% of remaining slots)
- **Phase 2**: Important tagged (remaining slots)
- **Phase 3**: Fallback (only if < 3 total memories)

### Timeouts
- Health check: 3000ms default
- Memory queries: No explicit timeout (relies on HTTP defaults)
- Git analysis: No explicit timeout (relies on Git command performance)

### Caching
- No explicit caching implemented
- Each session start triggers fresh analysis
- Consider implementing caching for git analysis results
