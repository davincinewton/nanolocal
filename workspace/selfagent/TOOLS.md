# SelfAgent Available Tools

## File Operations (with locking)

### read_file
Read contents of a file. Use this to inspect main agent's memory, configuration, or logs.

### write_file
Write content to a file. **Primary use**: Writing insights to MEMORY.md.

Important: When writing to MEMORY.md, the system will automatically prefix your content with "潜意识:".

### edit_file
Edit existing files. Use with caution and only on memory files.

### list_dir
List directory contents. Useful for exploring the workspace structure.

## Web Operations

### web_search
Search the web for information. Use when you need external knowledge to help the main agent.

### web_fetch
Fetch content from a specific URL.

## Usage Guidelines

1. **Prefer reading first**: Before writing, understand the current state
2. **Be specific**: When editing, provide exact old_string and new_string
3. **Log your actions**: The system logs all tool usage automatically
4. **Respect locks**: File operations may be delayed if main agent is using the file
