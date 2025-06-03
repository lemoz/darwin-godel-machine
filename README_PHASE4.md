# Phase 4: End-to-End System Integration

This document provides instructions for Phase 4 of the Darwin Gödel Machine (DGM) MVP implementation.

## Phase 4.1: API Configuration & Setup ✅

### Prerequisites

1. **API Keys Required**:
   - Google Gemini API key (primary provider)
   - Anthropic Claude API key (secondary provider)

### Setup Instructions

1. **Create your .env file**:
   ```bash
   cp .env.example .env
   ```

2. **Add your API keys** to the `.env` file:
   ```env
   GEMINI_API_KEY=your-actual-gemini-api-key-here
   ANTHROPIC_API_KEY=your-actual-anthropic-api-key-here
   ```

3. **Install dependencies** (if not already done):
   ```bash
   pip install -r requirements.txt
   ```

4. **Test your FM connections**:
   ```bash
   python test_fm_connection.py
   ```

   This will:
   - Verify API keys are properly configured
   - Test connectivity to both Gemini and Anthropic APIs
   - Send a simple test message to each provider
   - Report success/failure for each provider

### Expected Output

When running `test_fm_connection.py`, you should see:

```
Darwin Gödel Machine - FM Provider Connection Test
==================================================

==================================================
Testing GEMINI Connection
==================================================
✓ Configuration loaded successfully
  Model: gemini-2.0-flash-exp
  Max tokens: 8192
  Temperature: 0.1
✓ API key found (length: XX)
✓ Handler initialized successfully
⏳ Sending test request...
✓ Response received successfully!
  Content: Hello from Gemini!
  Model: gemini-2.0-flash-exp
  Tokens used: XX

==================================================
Testing ANTHROPIC Connection
==================================================
✓ Configuration loaded successfully
  Model: claude-3-5-sonnet-20241022
  Max tokens: 8192
  Temperature: 0.1
✓ API key found (length: XX)
✓ Handler initialized successfully
⏳ Sending test request...
✓ Response received successfully!
  Content: Hello from Anthropic!
  Model: claude-3-5-sonnet-20241022
  Tokens used: XX

==================================================
SUMMARY
==================================================
Gemini     ✓ PASS
Anthropic  ✓ PASS

✓ All providers are properly configured!
  You can now proceed with Phase 4.2 - Benchmark Dataset Integration

Primary provider: gemini
✓ Primary provider is working correctly
```

### Troubleshooting

If you see authentication errors:
- Verify your API keys are correct in the `.env` file
- Ensure you have active accounts with both providers
- Check that your API keys have sufficient permissions

If you see rate limit errors:
- Wait a few minutes before retrying
- Check your account quotas with each provider

## Phase 4.2: Benchmark Dataset Integration (Next Steps)

Once Phase 4.1 is complete and both FM providers are working:

1. **SWE-bench Lite Integration**:
   - Configure a subset of SWE-bench tasks for initial validation
   - Target the paper's baseline improvement (~20% → 50%)

2. **Polyglot Tasks**:
   - Integrate programming language benchmark tasks
   - Target improvement (~14.2% → 30.7%)

3. **Validation Benchmarks**:
   - Set up simple coding tasks to verify the evaluation framework

## Phase 4.3: Complete DGM Evolution Loop Validation

After benchmarks are integrated:

1. **Initial Agent Creation**: Generate the first "parent" agent
2. **Self-Modification Test**: Run one complete evolution cycle
3. **Archive Management**: Verify storage and retrieval
4. **Safety Validation**: Confirm sandboxing works correctly

## Phase 4.4: Integration Verification

Final steps:

1. **End-to-End Test**: Execute a complete multi-generation evolution (3-5 generations)
2. **Performance Tracking**: Monitor improvement patterns
3. **System Monitoring**: Verify stability under real workloads

## Current Status

- ✅ Phase 4.1: API Configuration & Setup - **COMPLETE**
  - Created `.env.example` template
  - Implemented `ConfigLoader` with environment variable support
  - Fully implemented Anthropic provider (was placeholder)
  - Created `test_fm_connection.py` verification script
  
- ⏳ Phase 4.2: Benchmark Dataset Integration - **READY TO START**
- ⏳ Phase 4.3: Complete DGM Evolution Loop Validation
- ⏳ Phase 4.4: Integration Verification

## Next Actions

1. Run `python test_fm_connection.py` to verify your API setup
2. Once both providers pass, proceed to Phase 4.2
3. Begin implementing benchmark dataset integration