# Create a flowchart for proactive session management strategy
diagram_code = """
flowchart TD
    A[Session Start] --> B[Monitor Metrics<br/>Msg Count<br/>Token Usage<br/>Duration<br/>Quality Score]
    B --> C{Threshold Check<br/>Msg > 150?<br/>Tokens > 80K?<br/>Time > 3hrs?<br/>Quality < 0.7?}
    C -->|No| D[Continue Sess]
    C -->|Yes| E[Consolidate<br/>Extract keys<br/>Compress ctx<br/>Store memory<br/>Reset session]
    D --> B
    E --> F[New Session<br/>w/ Context<br/>Consolidated<br/>memories<br/>Key decisions]
    F --> B
    
    classDef startEnd fill:#1FB8CD
    classDef process fill:#2E8B57
    classDef decision fill:#DB4545
    
    class A startEnd
    class B,D,E,F process
    class C decision
"""

# Create the mermaid diagram and save as both PNG and SVG
# Note: create_mermaid_diagram function needs to be implemented
# For now, save the diagram code to a file for manual processing
with open('session_management_flowchart.mmd', 'w') as f:
    f.write(diagram_code)
print(f"Flowchart saved as Mermaid file: session_management_flowchart.mmd")
print("Note: Use a Mermaid renderer to convert to PNG/SVG")