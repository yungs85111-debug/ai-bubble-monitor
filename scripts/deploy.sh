#!/bin/bash
# AI Bubble Monitor - Deployment Script
# Usage: ./scripts/deploy.sh [commit-message]

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 AI Bubble Monitor Deployment${NC}"
echo "================================="
echo ""

# Get commit message
COMMIT_MSG="${1:-Update dashboard: $(date +%Y-%m-%d)}"

# Step 1: Generate dashboard
echo -e "${YELLOW}📊 Step 1: Generating dashboard...${NC}"
python scripts/generate_debate_dashboard_v2.py

if [ $? -ne 0 ]; then
    echo "❌ Dashboard generation failed"
    exit 1
fi

echo -e "${GREEN}✓ Dashboard generated${NC}"
echo ""

# Step 2: Copy to index.html
echo -e "${YELLOW}📋 Step 2: Creating index.html...${NC}"
cp debate.html index.html

echo -e "${GREEN}✓ index.html created${NC}"
echo ""

# Step 3: Git operations
echo -e "${YELLOW}📦 Step 3: Committing changes...${NC}"

# Check if there are changes
if git diff --quiet index.html debate.html 2>/dev/null; then
    echo -e "${YELLOW}⚠️  No changes detected. Skipping commit.${NC}"
else
    git add index.html debate.html
    git commit -m "$COMMIT_MSG"
    echo -e "${GREEN}✓ Changes committed${NC}"
fi

echo ""

# Step 4: Push to GitHub
echo -e "${YELLOW}🌐 Step 4: Pushing to GitHub...${NC}"
git push origin main

if [ $? -ne 0 ]; then
    echo "❌ Push failed. Please check your git configuration."
    exit 1
fi

echo -e "${GREEN}✓ Pushed to GitHub${NC}"
echo ""

# Done
echo "================================="
echo -e "${GREEN}✅ Deployment complete!${NC}"
echo ""
echo -e "Your dashboard will be live in ~1 minute at:"
echo -e "${BLUE}https://$(git config --get remote.origin.url | sed 's/.*github.com[:/]\(.*\)\.git/\1/' | sed 's/\//.github.io\//').${NC}"
echo ""
echo -e "Check deployment status at:"
echo -e "${BLUE}https://github.com/$(git config --get remote.origin.url | sed 's/.*github.com[:/]\(.*\)\.git/\1/')/deployments${NC}"
