# Domain Management Tools for Claude Code AI

This document describes the comprehensive domain management tools available to Claude Code AI for manipulating memory domains in the Local Context Memory system.

## 🎯 Overview

Domains provide logical separation of memories by context, project, or topic. The system now includes powerful tools for:

- **Auto-detecting** project domains based on Git repository names
- **Creating** new domains for different contexts
- **Switching** between domains for focused work
- **Copying** memories between domains
- **Monitoring** domain usage and statistics

## 🛠️ Available MCP Tools

### 1. `get_current_project_domain()`
**Purpose**: Automatically detect the current project domain

**Returns**: `str` - The detected project domain name

**Example**:
```python
domain = get_current_project_domain()
# Returns: "local-memory-mcp-v2"
```

**Use Cases**:
- Understanding which domain memories will be stored in by default
- Setting up project-specific memory organization
- Automatically routing memories to the correct project context

---

### 2. `list_memory_domains()`
**Purpose**: List all available memory domains

**Returns**: `List[str]` - List of domain names

**Example**:
```python
domains = list_memory_domains()
# Returns: ["default", "startup", "health", "personal", "local-memory-mcp-v2"]
```

**Use Cases**:
- Discovering what domains are available before storing/searching
- Understanding the organization of stored memories
- Validating domain names before use

---

### 3. `create_domain(domain_name: str)`
**Purpose**: Create a new memory domain

**Parameters**:
- `domain_name` (str): The name of the domain to create

**Returns**: `bool` - True if created successfully, False if already exists

**Example**:
```python
success = create_domain("startup")
# Returns: True (new domain created)

success = create_domain("startup") 
# Returns: False (already exists)
```

**Use Cases**:
- Setting up new project contexts
- Organizing memories by topic or category
- Preparing domains before storing memories

---

### 4. `get_domain_info(domain_name: str)`
**Purpose**: Get detailed information about a specific domain

**Parameters**:
- `domain_name` (str): The name of the domain to get information about

**Returns**: `Dict[str, Any]` - Domain information including:
- `domain` (str): The domain name
- `memory_count` (int): Number of memories in this domain
- `table_size` (str): Approximate size of the domain table
- `exists` (bool): Whether the domain exists
- `last_activity` (str): Timestamp of the most recent memory

**Example**:
```python
info = get_domain_info("startup")
# Returns: {
#   "domain": "startup", 
#   "memory_count": 15, 
#   "table_size": "2.1 MB", 
#   "exists": True, 
#   "last_activity": "2024-01-15 10:30:00"
# }
```

**Use Cases**:
- Understanding domain usage and size
- Monitoring memory storage across domains
- Validating domain existence before operations

---

### 5. `switch_to_domain(domain_name: str)`
**Purpose**: Switch the current working domain context

**Parameters**:
- `domain_name` (str): The domain to switch to (will be created if doesn't exist)

**Returns**: `Dict[str, Any]` - Information about the domain switch:
- `success` (bool): Whether the switch was successful
- `domain` (str): The domain that was switched to
- `created` (bool): Whether the domain was created
- `memory_count` (int): Number of memories in this domain
- `message` (str): Human-readable status message

**Example**:
```python
result = switch_to_domain("startup")
# Returns: {
#   "success": True, 
#   "domain": "startup", 
#   "created": False, 
#   "memory_count": 15, 
#   "message": "Switched to existing domain 'startup' with 15 memories"
# }
```

**Use Cases**:
- Changing context between different projects or topics
- Setting up new project domains
- Organizing memory operations by context

---

### 6. `copy_memories_between_domains(source_domain: str, target_domain: str, query: Optional[str] = None, limit: Optional[int] = None)`
**Purpose**: Copy memories from one domain to another

**Parameters**:
- `source_domain` (str): The domain to copy memories from
- `target_domain` (str): The domain to copy memories to (will be created if doesn't exist)
- `query` (str, optional): Search query to filter which memories to copy
- `limit` (int, optional): Maximum number of memories to copy

**Returns**: `Dict[str, Any]` - Copy operation results:
- `success` (bool): Whether the copy operation was successful
- `source_domain` (str): The source domain name
- `target_domain` (str): The target domain name
- `memories_copied` (int): Number of memories successfully copied
- `target_created` (bool): Whether the target domain was created
- `message` (str): Human-readable status message

**Example**:
```python
result = copy_memories_between_domains("old-project", "archive")
# Returns: {
#   "success": True, 
#   "memories_copied": 25, 
#   "message": "Copied 25 memories from 'old-project' to 'archive'"
# }

result = copy_memories_between_domains("startup", "backup", "funding", 10)
# Returns: {
#   "success": True, 
#   "memories_copied": 3, 
#   "message": "Copied 3 memories matching 'funding' from 'startup' to 'backup'"
# }
```

**Use Cases**:
- Archiving old project memories
- Creating domain backups
- Reorganizing memory structure
- Moving memories between contexts

## 🔄 Workflow Examples

### Setting Up a New Project
```python
# 1. Check current project domain
current_domain = get_current_project_domain()
print(f"Current project: {current_domain}")

# 2. Create a new domain for this project
success = create_domain("my-new-project")
if success:
    print("New project domain created!")

# 3. Switch to the new domain
result = switch_to_domain("my-new-project")
print(result["message"])

# 4. Store memories in the new domain
memory_id = store_memory("Project setup completed", "my-new-project")
```

### Organizing Existing Memories
```python
# 1. List all domains
domains = list_memory_domains()
print(f"Available domains: {domains}")

# 2. Get info about each domain
for domain in domains:
    info = get_domain_info(domain)
    print(f"{domain}: {info['memory_count']} memories, {info['table_size']}")

# 3. Copy important memories to a backup domain
result = copy_memories_between_domains("default", "backup", "important", 50)
print(f"Backed up {result['memories_copied']} important memories")
```

### Switching Between Project Contexts
```python
# 1. Switch to startup domain
startup_result = switch_to_domain("startup")
print(f"Switched to startup: {startup_result['memory_count']} memories")

# 2. Search for funding-related memories
funding_memories = search_memories("funding", "startup", 10)

# 3. Switch to personal domain
personal_result = switch_to_domain("personal")
print(f"Switched to personal: {personal_result['memory_count']} memories")

# 4. Store a personal memory
store_memory("User prefers morning workouts", "personal")
```

## 🎯 Best Practices

### Domain Naming
- Use lowercase letters, numbers, underscores, and hyphens
- Avoid special characters and spaces
- Examples: `"startup"`, `"health"`, `"project-alpha"`, `"user_preferences"`

### Domain Organization
- **Project-based**: Use Git repository names (auto-detected)
- **Topic-based**: Organize by subject matter (`"health"`, `"finance"`, `"travel"`)
- **Context-based**: Separate by work context (`"startup"`, `"personal"`, `"learning"`)

### Memory Management
- Use `switch_to_domain()` to set context before storing memories
- Use `copy_memories_between_domains()` for reorganization
- Monitor domain sizes with `get_domain_info()`

### Error Handling
- Always check return values for success/failure
- Use `list_memory_domains()` to validate domain existence
- Handle cases where domains don't exist gracefully

## 🔧 Integration with Existing Tools

These domain management tools work seamlessly with existing memory tools:

- **`store_memory()`**: Can specify domain or use current default
- **`search_memories()`**: Can search within specific domains
- **`update_memory()`**: Can update memories in specific domains
- **`ingest_document()`**: Can ingest documents into specific domains

## 🚀 Advanced Usage

### Automatic Project Detection
The system automatically detects project domains based on:
1. Git repository name (primary)
2. Project directory name (fallback)
3. Configuration files (package.json, requirements.txt, etc.)

### Domain Statistics
Monitor domain health with:
- Memory counts per domain
- Storage sizes
- Last activity timestamps
- Growth trends over time

### Memory Migration
Use `copy_memories_between_domains()` for:
- Project archiving
- Memory reorganization
- Backup creation
- Cross-domain memory sharing

This comprehensive domain management system gives Claude Code AI powerful tools for organizing and manipulating memories across different contexts and projects! 🎉
