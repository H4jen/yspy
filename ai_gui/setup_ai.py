#!/usr/bin/env python3
"""
Quick setup script for YSpy AI Assistant
Helps configure the API key for the AI chat window.
"""

import os
import sys

def main():
    print("=" * 60)
    print("YSpy AI Assistant - Quick Setup")
    print("=" * 60)
    print()
    
    # Check if API key is already set
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if api_key:
        print("✓ ANTHROPIC_API_KEY is already set")
        print(f"  Key: {api_key[:10]}..." + "*" * 20)
        print()
        print("AI Assistant should work. Launch yspy to see the chat window.")
        return 0
    
    print("⚠ No API key found in environment")
    print()
    print("To use the AI Assistant, you need an API key from Anthropic.")
    print()
    print("Step-by-step setup:")
    print()
    print("1. Get an API key:")
    print("   Go to: https://console.anthropic.com/")
    print("   - Sign up for an account (if you don't have one)")
    print("   - Navigate to 'API Keys'")
    print("   - Create a new API key")
    print("   - Copy the key (starts with 'sk-ant-...')")
    print()
    print("2. Set the environment variable:")
    print()
    print("   For current session:")
    print("   export ANTHROPIC_API_KEY='your-key-here'")
    print()
    print("   To make it permanent, add to your shell config:")
    print()
    print("   For bash (~/.bashrc or ~/.bash_profile):")
    print("   echo 'export ANTHROPIC_API_KEY=\"your-key-here\"' >> ~/.bashrc")
    print("   source ~/.bashrc")
    print()
    print("   For zsh (~/.zshrc):")
    print("   echo 'export ANTHROPIC_API_KEY=\"your-key-here\"' >> ~/.zshrc")
    print("   source ~/.zshrc")
    print()
    print("3. Restart yspy:")
    print("   ./yspy.py")
    print()
    print("The AI chat window will open automatically when you start yspy.")
    print()
    print("=" * 60)
    print()
    
    # Offer to set it interactively
    response = input("Would you like to set the API key now for this session? (y/n): ").strip().lower()
    
    if response == 'y':
        print()
        api_key = input("Paste your API key here (it won't be shown): ").strip()
        
        if not api_key:
            print("❌ No key entered. Exiting.")
            return 1
        
        if not api_key.startswith('sk-ant-'):
            print("⚠ Warning: Anthropic API keys usually start with 'sk-ant-'")
            print("  Your key doesn't match this pattern. It might not work.")
        
        # Set for current process
        os.environ['ANTHROPIC_API_KEY'] = api_key
        
        print()
        print("✓ API key set for this session!")
        print()
        print("To test it, run:")
        print("  python3 test_ai_setup.py")
        print()
        print("Or launch yspy:")
        print("  ./yspy.py")
        print()
        print("⚠ Note: This only sets the key for the current terminal session.")
        print("  Add it to your ~/.bashrc or ~/.zshrc to make it permanent.")
        return 0
    else:
        print()
        print("No problem! Set the key manually using the instructions above.")
        return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        sys.exit(1)
