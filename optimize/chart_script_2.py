import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

# Parse the data
data = [
  {
    "section": "Token Efficiency",
    "metrics": [
      {"name": "Compression Events", "current": 4, "target": "<1", "unit": "per month", "status": "warning"},
      {"name": "Session Length", "current": 245, "target": "<150", "unit": "messages", "status": "critical"}, 
      {"name": "Token Burn Rate", "current": 45000, "target": "<30000", "unit": "tokens/hour", "status": "warning"},
      {"name": "Context Efficiency", "current": 0.73, "target": ">0.85", "unit": "ratio", "status": "warning"}
    ]
  },
  {
    "section": "Database Performance",
    "metrics": [
      {"name": "Buffer Cache Hit", "current": 0.94, "target": ">0.95", "unit": "ratio", "status": "good"},
      {"name": "Index Cache Hit", "current": 0.91, "target": ">0.90", "unit": "ratio", "status": "good"},
      {"name": "Query Latency", "current": 12, "target": "<10", "unit": "ms", "status": "warning"},
      {"name": "HNSW Effect", "current": 0.88, "target": ">0.85", "unit": "recall", "status": "good"}
    ]
  },
  {
    "section": "Memory System",
    "metrics": [
      {"name": "L1 Cache Hit", "current": 0.82, "target": ">0.85", "unit": "ratio", "status": "warning"},
      {"name": "L2 Cache Hit", "current": 0.78, "target": ">0.80", "unit": "ratio", "status": "warning"},
      {"name": "Memory Relevance", "current": 0.76, "target": ">0.80", "unit": "score", "status": "warning"},
      {"name": "Retrieval Acc", "current": 0.84, "target": ">0.85", "unit": "score", "status": "warning"}
    ]
  },
  {
    "section": "System Health",
    "metrics": [
      {"name": "CPU Usage", "current": 45, "target": "<70", "unit": "percent", "status": "good"},
      {"name": "Memory Usage", "current": 68, "target": "<80", "unit": "percent", "status": "good"},
      {"name": "Storage I/O", "current": 125, "target": "<200", "unit": "IOPS", "status": "good"},
      {"name": "Active Alerts", "current": 3, "target": "0", "unit": "alerts", "status": "warning"}
    ]
  }
]

# Process data
rows = []
for section_data in data:
    section = section_data['section']
    for metric in section_data['metrics']:
        target_str = metric['target']
        current = metric['current']
        
        # Calculate health score (0-100, capped at 100)
        if target_str.startswith('>'):
            target_val = float(target_str[1:])
            score = min((current / target_val) * 100, 100)
        elif target_str.startswith('<'):
            target_val = float(target_str[1:])
            score = min((target_val / current) * 100, 100) if current > 0 else 100
        else:
            target_val = float(target_str)
            score = 100 if current <= target_val else 50
        
        # Format values for display
        if metric['unit'] in ['ratio', 'recall', 'score']:
            current_fmt = f"{current:.2f}"
            target_fmt = target_str.replace('>', '').replace('<', '')
        elif 'tokens' in metric['unit']:
            current_fmt = f"{current/1000:.0f}k"
            target_fmt = target_str.replace('<', '<').replace('30000', '30k')
        elif metric['unit'] == 'percent':
            current_fmt = f"{current}%"
            target_fmt = target_str + '%'
        else:
            current_fmt = str(current)
            target_fmt = target_str
            
        rows.append({
            'section': section,
            'metric': metric['name'],
            'current': current,
            'current_fmt': current_fmt,
            'target_fmt': target_fmt,
            'status': metric['status'],
            'score': score,
            'unit': metric['unit']
        })

df = pd.DataFrame(rows)

# Create the figure with subplots approach but using a single chart with grouping
fig = go.Figure()

# Color mapping
status_colors = {
    'good': '#2E8B57',      # Sea green
    'warning': '#D2BA4C',   # Moderate yellow  
    'critical': '#DB4545'   # Bright red
}

# Create grouped layout
sections = df['section'].unique()
y_pos = 0
y_labels = []
y_positions = []
section_breaks = []

for section in sections:
    section_df = df[df['section'] == section].copy()
    
    # Add section header space
    if y_pos > 0:
        y_pos += 1
        section_breaks.append(y_pos - 0.5)
    
    section_start = y_pos
    
    for _, row in section_df.iterrows():
        # Add current value bar
        fig.add_trace(go.Bar(
            x=[row['score']],
            y=[y_pos],
            orientation='h',
            marker=dict(color=status_colors[row['status']]),
            name=row['status'].title(),
            text=f"{row['current_fmt']}",
            textposition='inside',
            hovertemplate=f"<b>{row['metric']}</b><br>" +
                         f"Current: {row['current_fmt']}<br>" +
                         f"Target: {row['target_fmt']}<br>" +
                         f"Health: {row['score']:.0f}%<br>" +
                         f"Status: {row['status'].title()}<extra></extra>",
            showlegend=False
        ))
        
        y_labels.append(row['metric'])
        y_positions.append(y_pos)
        y_pos += 1
    
    # Add section label
    section_mid = (section_start + y_pos - 1) / 2
    fig.add_annotation(
        x=-15,
        y=section_mid,
        text=f"<b>{section}</b>",
        showarrow=False,
        font=dict(size=12),
        xanchor='right',
        textangle=0
    )

# Add target line at 100%
fig.add_vline(x=100, line_dash="dash", line_color="#666666", line_width=2)
fig.add_annotation(x=100, y=-1, text="Target", showarrow=False, font=dict(size=10))

# Create legend manually
legend_y_start = max(y_positions) + 1
for i, (status, color) in enumerate(status_colors.items()):
    fig.add_trace(go.Scatter(
        x=[None], y=[None],
        mode='markers',
        marker=dict(color=color, size=10, symbol='square'),
        name=status.title(),
        showlegend=True
    ))

# Update layout
fig.update_layout(
    title="MCP Server Dashboard - Health Metrics",
    xaxis_title="Health Score (%)",
    yaxis_title="",
    yaxis=dict(
        tickmode='array',
        tickvals=y_positions,
        ticktext=y_labels,
        autorange='reversed',
        showgrid=False
    ),
    xaxis=dict(
        range=[-20, 120],
        ticksuffix="%",
        showgrid=True,
        gridcolor='lightgray'
    ),
    legend=dict(
        orientation='h', 
        yanchor='bottom', 
        y=1.05, 
        xanchor='center', 
        x=0.5
    ),
    plot_bgcolor='white'
)

fig.update_traces(cliponaxis=False)

# Save files
fig.write_image("dashboard.png")
fig.write_image("dashboard.svg", format="svg")