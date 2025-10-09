#!/bin/bash
# YSpy Root Directory Cleanup Script
# Reorganizes project into a clean, professional structure

set -e  # Exit on error

echo "🧹 YSpy Root Cleanup Script"
echo "======================================"
echo ""

# Backup first
BACKUP_FILE="yspy_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
echo "📦 Creating backup: $BACKUP_FILE"
tar --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' -czf "../$BACKUP_FILE" .
echo "✓ Backup saved to ../$BACKUP_FILE"
echo ""

# Create directories
echo "📁 Creating directory structure..."
mkdir -p src ai_gui short_selling remote tests
mkdir -p docs/{ai,implementation,proposals}
mkdir -p config
echo "✓ Directories created"
echo ""

# Move source code
echo "📦 Moving source code to src/..."
for file in app_config.py yspy_app.py portfolio_manager.py \
            correlation_analysis.py historical_portfolio_value.py \
            update_historical_prices.py menu_handlers.py ui_handlers.py; do
    if [ -f "$file" ]; then
        mv "$file" src/
        echo "  ✓ $file"
    fi
done
touch src/__init__.py
echo ""

# Move AI GUI
echo "🤖 Moving AI GUI components to ai_gui/..."
for file in ai_chat_window.py ai_menu_handler.py setup_ai.py; do
    if [ -f "$file" ]; then
        mv "$file" ai_gui/
        echo "  ✓ $file"
    fi
done
touch ai_gui/__init__.py
echo ""

# Move short selling
echo "📊 Moving short selling module to short_selling/..."
for file in short_selling_integration.py short_selling_tracker.py \
            short_selling_menu.py remote_short_data.py nordic_isin_mapping.py; do
    if [ -f "$file" ]; then
        mv "$file" short_selling/
        echo "  ✓ $file"
    fi
done
touch short_selling/__init__.py
echo ""

# Move remote
echo "🌐 Moving remote module to remote/..."
if [ -f "remote_integration_helper.py" ]; then
    mv remote_integration_helper.py remote/
    echo "  ✓ remote_integration_helper.py"
fi
touch remote/__init__.py
echo ""

# Move tests
echo "🧪 Moving test files to tests/..."
for file in test_*.py check_trend_readiness.py demo_short_trend.py; do
    if [ -f "$file" ]; then
        mv "$file" tests/
        echo "  ✓ $file"
    fi
done
echo ""

# Move documentation
echo "📚 Moving documentation to docs/..."
# AI docs
for file in AI_*.md CLOUD_AI_SECURITY.md; do
    if [ -f "$file" ]; then
        mv "$file" docs/ai/
        echo "  ✓ $file -> docs/ai/"
    fi
done

# Implementation docs
for file in FILE_MANAGEMENT_COMPLETE.md SHORT_TREND_IMPLEMENTATION_SUMMARY.md \
            IMPLEMENTATION_COMPLETE.txt; do
    if [ -f "$file" ]; then
        mv "$file" docs/implementation/
        echo "  ✓ $file -> docs/implementation/"
    fi
done

# Proposals
for file in SHORT_TREND_ARROWS_PROPOSAL.md TREND_ARROWS_STATUS.md; do
    if [ -f "$file" ]; then
        mv "$file" docs/proposals/
        echo "  ✓ $file -> docs/proposals/"
    fi
done
echo ""

# Move configs
echo "⚙️  Moving config files..."
if [ -f "ai_config.py" ]; then
    mv ai_config.py config/
    echo "  ✓ ai_config.py -> config/"
fi
if [ -f "ai_costs.json" ]; then
    mv ai_costs.json data/ai/
    echo "  ✓ ai_costs.json -> data/ai/"
fi
if [ -f "remote_config.json" ]; then
    mv remote_config.json config/
    echo "  ✓ remote_config.json -> config/"
fi
echo ""

# Clean up duplicates
echo "🗑️  Removing duplicates..."
if [ -f "AI_QUICK_REFERENCE.txt" ]; then
    rm AI_QUICK_REFERENCE.txt
    echo "  ✓ Removed AI_QUICK_REFERENCE.txt (keeping .md version)"
fi
echo ""

# Create docs index
echo "📖 Creating docs/README.md..."
cat > docs/README.md << 'DOCEOF'
# YSpy Documentation

## User Guides

### AI Assistant
- [Setup Guide](ai/AI_SETUP_GUIDE.md) - Getting started with AI features
- [Window Guide](ai/AI_WINDOW_READY.md) - Using the AI chat window
- [Quick Reference](ai/AI_QUICK_REFERENCE.md) - Common AI commands
- [Feature Guide](ai/AI_FEATURES_COMPLETE.md) - Complete feature list
- [File Management](ai/AI_FILE_MANAGEMENT.md) - Managing downloaded files
- [Report Downloads](ai/AI_PROACTIVE_DOWNLOADS.md) - Downloading company reports
- [Font Controls](ai/AI_FONT_SIZE_FEATURE.md) - Adjusting font size
- [Security](ai/CLOUD_AI_SECURITY.md) - Security and privacy

### Detailed Guides
- [Assistant Guide](ai/AI_ASSISTANT_GUIDE.md) - Complete AI assistant guide
- [Examples](ai/AI_EXAMPLES.md) - Usage examples
- [Visual Guide](ai/AI_VISUAL_GUIDE.md) - Visual walkthrough
- [Memory System](ai/AI_MEMORY_EXPLAINED.md) - How AI remembers context

## Implementation Notes

- [AI Implementation](implementation/AI_IMPLEMENTATION.md) - Core AI implementation
- [GUI Update](implementation/AI_GUI_UPDATE.md) - GUI window implementation
- [File Management](implementation/FILE_MANAGEMENT_COMPLETE.md) - File management features
- [Short Selling](implementation/SHORT_TREND_IMPLEMENTATION_SUMMARY.md) - Short selling integration

## Development

### Proposals
- [Terminal Interface](proposals/AI_TERMINAL_PROPOSAL.md) - Terminal-based chat proposal
- [Trend Arrows](proposals/SHORT_TREND_ARROWS_PROPOSAL.md) - Trend visualization proposal
- [Trend Status](proposals/TREND_ARROWS_STATUS.md) - Trend implementation status

## Quick Links

- Main README: [../README.md](../README.md)
- Requirements: [../requirements.txt](../requirements.txt)
- License: [../LICENSE](../LICENSE)
DOCEOF
echo "✓ docs/README.md created"
echo ""

# Create import update guide
echo "📝 Creating IMPORT_UPDATE_GUIDE.md..."
cat > IMPORT_UPDATE_GUIDE.md << 'UPDATEEOF'
# Import Update Guide

## Files That Need Import Updates

### yspy.py (main entry point)
```python
# OLD
from yspy_app import YSpyApp
from app_config import AppConfig

# NEW
from src.yspy_app import YSpyApp
from src.app_config import AppConfig
```

### Files in src/
Files moved to `src/` need to update imports:

**src/yspy_app.py:**
```python
# OLD
from app_config import AppConfig
from menu_handlers import MenuHandlers
from ui_handlers import UIHandlers

# NEW
from src.app_config import AppConfig
from src.menu_handlers import MenuHandlers
from src.ui_handlers import UIHandlers
```

### AI GUI Files
Files moved to `ai_gui/` need:

**ai_gui/ai_chat_window.py:**
```python
# OLD
from ai_agent.agent import YSpyAIAgent
from ai_config import AI_CONFIG

# NEW
from ai_agent.agent import YSpyAIAgent
from config.ai_config import AI_CONFIG
```

### Config Files
Files importing config:

```python
# OLD
from ai_config import AI_CONFIG

# NEW
from config.ai_config import AI_CONFIG
```

## Quick Fix Commands

```bash
# Find files that import from moved modules
grep -r "from app_config import" --include="*.py" .
grep -r "from yspy_app import" --include="*.py" .
grep -r "from ai_config import" --include="*.py" .

# Test imports
python3 -c "from src.app_config import AppConfig; print('✓ src imports OK')"
python3 -c "from config.ai_config import AI_CONFIG; print('✓ config imports OK')"
python3 -c "from ai_gui.ai_chat_window import AIChatWindow; print('✓ ai_gui imports OK')"
```

## Verification Steps

1. **Check main entry point:**
   ```bash
   python3 -m py_compile yspy.py
   ```

2. **Check all Python files:**
   ```bash
   find . -name "*.py" -not -path "./.git/*" -not -path "./__pycache__/*" | xargs python3 -m py_compile
   ```

3. **Test run:**
   ```bash
   ./yspy.py
   ```

## Rollback

If imports are broken:
```bash
tar -xzf ../yspy_backup_*.tar.gz
```
UPDATEEOF
echo "✓ IMPORT_UPDATE_GUIDE.md created"
echo ""

echo "======================================"
echo "✅ Cleanup Complete!"
echo ""
echo "📊 Summary:"
echo "  ✓ Source code moved to src/"
echo "  ✓ AI GUI moved to ai_gui/"
echo "  ✓ Tests moved to tests/"
echo "  ✓ Docs moved to docs/"
echo "  ✓ Configs moved to config/ and data/"
echo ""
echo "⚠️  NEXT STEPS:"
echo "1. Read IMPORT_UPDATE_GUIDE.md"
echo "2. Update imports in yspy.py and other files"
echo "3. Run: python3 -m py_compile yspy.py"
echo "4. Test: ./yspy.py"
echo ""
echo "💾 Backup saved: ../$BACKUP_FILE"
echo "🔄 Rollback: tar -xzf ../$BACKUP_FILE"
echo ""
echo "Root directory cleaned! 🎉"
