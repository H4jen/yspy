"""
Cloud AI Provider Interface
Handles communication with different cloud AI services (Anthropic, OpenAI, Gemini).
"""

import os
import json
from typing import Optional, Dict, List, Any
from config.ai_config import AI_CONFIG, get_api_key, get_model, estimate_cost, log_cost, check_daily_cost_limit


class CloudProvider:
    """Unified interface for cloud AI providers."""
    
    def __init__(self, provider: str = None, api_key: str = None):
        """
        Initialize cloud provider.
        
        Args:
            provider: 'anthropic', 'openai', or 'gemini'
            api_key: API key (if not provided, reads from environment)
        """
        self.provider = provider or AI_CONFIG['provider']
        self.api_key = api_key or get_api_key()
        self.model = get_model()
        self.client = None
        
        if not self.api_key:
            raise ValueError(
                f"API key not found. Please set {AI_CONFIG['api_key_env']} environment variable.\n"
                f"For {self.provider}, you can also set:\n"
                f"  - Anthropic: ANTHROPIC_API_KEY\n"
                f"  - OpenAI: OPENAI_API_KEY\n"
                f"  - Gemini: GOOGLE_API_KEY"
            )
        
        self._init_client()
    
    def _init_client(self):
        """Initialize the appropriate client based on provider."""
        try:
            if self.provider == 'anthropic':
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            elif self.provider == 'openai':
                import openai
                self.client = openai.OpenAI(api_key=self.api_key)
            elif self.provider == 'gemini':
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.client = genai.GenerativeModel(self.model)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
        except ImportError as e:
            raise ImportError(
                f"Provider '{self.provider}' requires additional packages.\n"
                f"Install with: pip install {self._get_package_name()}"
            ) from e
    
    def _get_package_name(self):
        """Get the package name for the provider."""
        packages = {
            'anthropic': 'anthropic',
            'openai': 'openai',
            'gemini': 'google-generativeai'
        }
        return packages.get(self.provider, 'unknown')
    
    def send_message(self, 
                    message: str, 
                    system_prompt: str = None,
                    conversation_history: List[Dict] = None,
                    tools: List[Dict] = None,
                    max_tokens: int = None) -> Dict[str, Any]:
        """
        Send a message to the AI and get response.
        
        Args:
            message: User message
            system_prompt: System instructions for the AI
            conversation_history: Previous messages in conversation
            tools: Available tools/functions for the AI to call
            max_tokens: Maximum tokens in response
            
        Returns:
            Dict with 'content', 'tool_calls', 'usage', 'cost'
        """
        # Check daily cost limit
        allowed, remaining, msg = check_daily_cost_limit()
        if not allowed:
            return {
                'content': f"❌ {msg}",
                'tool_calls': None,
                'usage': None,
                'cost': 0,
                'error': 'budget_exceeded'
            }
        
        max_tokens = max_tokens or AI_CONFIG['max_tokens']
        
        try:
            if self.provider == 'anthropic':
                return self._anthropic_request(message, system_prompt, conversation_history, tools, max_tokens)
            elif self.provider == 'openai':
                return self._openai_request(message, system_prompt, conversation_history, tools, max_tokens)
            elif self.provider == 'gemini':
                return self._gemini_request(message, system_prompt, conversation_history, tools, max_tokens)
        except Exception as e:
            return {
                'content': f"Error communicating with AI: {str(e)}",
                'tool_calls': None,
                'usage': None,
                'cost': 0,
                'error': str(e)
            }
    
    def _anthropic_request(self, message, system_prompt, history, tools, max_tokens):
        """Handle Anthropic Claude request."""
        messages = []
        
        # Add conversation history
        if history:
            messages.extend(history)
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        # Prepare request parameters
        params = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": AI_CONFIG['temperature']
        }
        
        if system_prompt:
            params["system"] = system_prompt
        
        if tools:
            params["tools"] = tools
        
        # Send request
        response = self.client.messages.create(**params)
        
        # Extract content
        content_text = ""
        tool_calls = []
        
        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })
        
        # Calculate cost
        usage = {
            'input_tokens': response.usage.input_tokens,
            'output_tokens': response.usage.output_tokens
        }
        cost = estimate_cost(usage['input_tokens'], usage['output_tokens'])
        
        # Log cost
        log_cost(usage['input_tokens'], usage['output_tokens'], cost)
        
        return {
            'content': content_text,
            'tool_calls': tool_calls if tool_calls else None,
            'usage': usage,
            'cost': cost,
            'stop_reason': response.stop_reason
        }
    
    def _openai_request(self, message, system_prompt, history, tools, max_tokens):
        """Handle OpenAI GPT request."""
        messages = []
        
        # Add system prompt
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Add conversation history
        if history:
            messages.extend(history)
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        # Prepare request parameters
        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": AI_CONFIG['temperature']
        }
        
        if tools:
            # Convert tool format if needed
            params["tools"] = tools
            params["tool_choice"] = "auto"
        
        # Send request
        response = self.client.chat.completions.create(**params)
        
        # Extract content
        message_obj = response.choices[0].message
        content_text = message_obj.content or ""
        
        tool_calls = None
        if message_obj.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json.loads(tc.function.arguments)
                }
                for tc in message_obj.tool_calls
            ]
        
        # Calculate cost
        usage = {
            'input_tokens': response.usage.prompt_tokens,
            'output_tokens': response.usage.completion_tokens
        }
        cost = estimate_cost(usage['input_tokens'], usage['output_tokens'])
        
        # Log cost
        log_cost(usage['input_tokens'], usage['output_tokens'], cost)
        
        return {
            'content': content_text,
            'tool_calls': tool_calls,
            'usage': usage,
            'cost': cost,
            'finish_reason': response.choices[0].finish_reason
        }
    
    def _gemini_request(self, message, system_prompt, history, tools, max_tokens):
        """Handle Google Gemini request."""
        # Gemini handles system prompts differently
        full_message = message
        if system_prompt:
            full_message = f"{system_prompt}\n\n{message}"
        
        # Send request
        response = self.client.generate_content(
            full_message,
            generation_config={
                'max_output_tokens': max_tokens,
                'temperature': AI_CONFIG['temperature']
            }
        )
        
        content_text = response.text
        
        # Gemini has free tier, so cost is 0
        usage = {
            'input_tokens': 0,  # Gemini doesn't expose token counts easily
            'output_tokens': 0
        }
        cost = 0
        
        return {
            'content': content_text,
            'tool_calls': None,  # Tool calling works differently in Gemini
            'usage': usage,
            'cost': cost
        }
    
    def test_connection(self) -> tuple[bool, str]:
        """
        Test connection to AI provider.
        
        Returns:
            (success, message)
        """
        try:
            response = self.send_message(
                "Respond with just 'OK' to confirm connection.",
                max_tokens=10
            )
            
            if response.get('error'):
                return False, f"Error: {response['error']}"
            
            return True, f"✓ Connected to {self.provider} ({self.model})"
        
        except Exception as e:
            return False, f"Connection failed: {str(e)}"


if __name__ == "__main__":
    # Test the provider
    try:
        provider = CloudProvider()
        success, msg = provider.test_connection()
        print(msg)
        
        if success:
            print("\nTesting a simple query...")
            response = provider.send_message("What is 2+2? Respond briefly.")
            print(f"Response: {response['content']}")
            print(f"Cost: ${response['cost']:.6f}")
            print(f"Tokens: {response['usage']['input_tokens']} in, {response['usage']['output_tokens']} out")
    
    except Exception as e:
        print(f"Error: {e}")
