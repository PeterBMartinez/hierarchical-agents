FROM python:3.12-slim

# Node + Claude Code CLI: only needed if you enable the claude_code worker.
# Delete this block to slim the image if you won't use that worker.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agents_app ./agents_app
COPY dashboard ./dashboard
COPY cost-monitor ./cost-monitor

ENV AGENT_OUTPUT_DIR=/app/outputs

ENTRYPOINT ["python", "-m", "agents_app.runner"]
