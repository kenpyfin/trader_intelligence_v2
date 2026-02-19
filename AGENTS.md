# Trading Intelligence Agent Architecture

## Current Implementation Overview

This codebase implements a sophisticated trading intelligence system that combines AI-powered analysis with real-time market data and broker integration. The system follows a microservices architecture with clear separation of concerns.

### Core Components

#### 1. AI Agent System (`ai_agent/`)
- **agent.py**: Wrapper around aider CLI tool for enhanced development accuracy
- **memory.md**: Persistent memory storage for context retention
- **Purpose**: Provides AI-assisted development and code generation capabilities

#### 2. Backend Analytics Engine (`backend/src/`)
- **analysis_service.py**: Core analytics engine with comprehensive option analysis
- **portfolio_service.py**: Portfolio management and position tracking
- **broker_service.py**: Broker integration for order execution
- **macro_service.py**: Macro-economic data and risk-free rate calculations

#### 3. Frontend Interface (`frontend/src/`)
- **Analysis.js**: Main analysis interface with real-time option chain visualization
- **Portfolio.js**: Portfolio management and monitoring dashboard
- **YieldCurve.js**: Macro-economic indicators display

#### 4. Data Providers (`backend/src/my_libs_py3/`)
- **FMP integration**: Real-time pricing and historical data
- **Finviz integration**: Option chains and stock fundamentals
- **Interactive Brokers**: Portfolio data and order execution

### Key Features Implemented

#### 1. Comprehensive Option Analysis
- **Multi-factor Analysis Engine**: Combines trend, sentiment, volatility, and quantitative valuation
- **Binomial Pricing Model**: Time-varying volatility with American/European exercise support
- **Greeks Calculation**: Delta, Gamma, Theta, Vega with portfolio aggregation
- **IV Surface Construction**: Term structure building with forward volatility extraction

#### 2. Market Intelligence
- **Trend Analysis**: SMA-based trend detection with candlestick pattern recognition
- **Sentiment Analysis**: Put/Call parity, volume ratios, unusual option activity detection
- **Volatility Analysis**: IV vs HV comparison, compression detection, earnings impact
- **Quantitative Valuation**: Model vs market price comparison with undervaluation screening

#### 3. Risk Management
- **Portfolio Greek Exposure**: Net Delta, Gamma, Vega, Theta tracking
- **Position Alerts**: Profit/stop alerts, delta saturation, gamma acceleration warnings
- **Strategy-Level Monitoring**: Multi-leg strategy aggregation and risk metrics

#### 4. Trading Integration
- **One-Click Execution**: Complex order construction and placement
- **Real-time Data**: Live pricing and option chain updates
- **Portfolio Tracking**: Open positions, P&L, recent orders monitoring

## Technical Architecture

### Backend Services (FastAPI)
```python
# Core Endpoints
GET /analysis/expirations/{ticker}
POST /analysis/stock
GET /macro-data
POST /calculate-risk-free-rate
GET /portfolio/open-positions
POST /orders/strategy
```

### Frontend (React)
- Component-based architecture with modern hooks
- Real-time data fetching with loading states
- Local storage for user preferences
- Responsive design with Tailwind CSS

### Data Flow
1. **User Input** → Frontend validation
2. **API Request** → Backend service orchestration
3. **Data Fetching** → Multi-source data aggregation
4. **Analysis Engine** → Multi-factor signal generation
5. **Result Synthesis** → Holistic recommendation
6. **Frontend Display** → Interactive visualization

## Development Guidelines

### Philosophy

#### Core Beliefs
- **Incremental progress over big bangs** - Small changes that compile and pass tests
- **Learning from existing code** - Study and plan before implementing
- **Pragmatic over dogmatic** - Adapt to project reality
- **Clear intent over clever code** - Be boring and obvious

#### Simplicity Means
- Single responsibility per function/class
- Avoid premature abstractions
- No clever tricks - choose the boring solution
- If you need to explain it, it's too complex

### Process

#### 1. Planning & Staging
Break complex work into 3-5 stages. Document in `IMPLEMENTATION_PLAN.md`:

```markdown
## Stage N: [Name]
**Goal**: [Specific deliverable]
**Success Criteria**: [Testable outcomes]
**Tests**: [Specific test cases]
**Status**: [Not Started|In Progress|Complete]
```

#### 2. Implementation Flow
1. **Understand** - Study existing patterns in codebase
2. **Test** - Write test first (red)
3. **Implement** - Minimal code to pass (green)
4. **Refactor** - Clean up with tests passing
5. **Commit** - With clear message linking to plan

#### 3. When Stuck (After 3 Attempts)
**CRITICAL**: Maximum 3 attempts per issue, then STOP.

1. **Document what failed**:
   - What you tried
   - Specific error messages
   - Why you think it failed

2. **Research alternatives**:
   - Find 2-3 similar implementations
   - Note different approaches used

3. **Question fundamentals**:
   - Is this the right abstraction level?
   - Can this be split into smaller problems?
   - Is there a simpler approach entirely?

4. **Try different angle**:
   - Different library/framework feature?
   - Different architectural pattern?
   - Remove abstraction instead of adding?

## Technical Standards

### Architecture Principles
- **Composition over inheritance** - Use dependency injection
- **Interfaces over singletons** - Enable testing and flexibility
- **Explicit over implicit** - Clear data flow and dependencies
- **Test-driven when possible** - Never disable tests, fix them

### Code Quality
- **Every commit must**:
  - Compile successfully
  - Pass all existing tests
  - Include tests for new functionality
  - Follow project formatting/linting

- **Before committing**:
  - Run formatters/linters
  - Self-review changes
  - Ensure commit message explains "why"

### Error Handling
- Fail fast with descriptive messages
- Include context for debugging
- Handle errors at appropriate level
- Never silently swallow exceptions

## Decision Framework
When multiple valid approaches exist, choose based on:

1. **Testability** - Can I easily test this?
2. **Readability** - Will someone understand this in 6 months?
3. **Consistency** - Does this match project patterns?
4. **Simplicity** - Is this the simplest solution that works?
5. **Reversibility** - How hard to change later?

## Project Integration

### Learning the Codebase
- Find 3 similar features/components
- Identify common patterns and conventions
- Use same libraries/utilities when possible
- Follow existing test patterns

### Tooling
- Use project's existing build system
- Use project's test framework
- Use project's formatter/linter settings
- Don't introduce new tools without strong justification

## Quality Gates

### Definition of Done
- [ ] Tests written and passing
- [ ] Code follows project conventions
- [ ] No linter/formatter warnings
- [ ] Commit messages are clear
- [ ] Implementation matches plan
- [ ] No TODOs without issue numbers

### Test Guidelines
- Test behavior, not implementation
- One assertion per test when possible
- Clear test names describing scenario
- Use existing test utilities/helpers
- Tests should be deterministic

## Important Reminders

**NEVER**:
- Use `--no-verify` to bypass commit hooks
- Disable tests instead of fixing them
- Commit code that doesn't compile
- Make assumptions - verify with existing code

**ALWAYS**:
- Commit working code incrementally
- Update plan documentation as you go
- Learn from existing implementations
- Stop after 3 failed attempts and reassess

---

# Guidance for Follow-up Engineers

## Quick Start Guide

### 1. Environment Setup
```bash
# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend setup
cd frontend
npm install
npm start
```

### 2. Key Files to Understand First
1. **`backend/src/services/analysis_service.py`** - Core analytics engine
2. **`backend/src/analytics/analysis.py`** - Analysis orchestration
3. **`frontend/src/pages/Analysis.js`** - Main user interface
4. **`backend/src/my_libs_py3/my_data.py`** - Data fetching utilities

### 3. Running the System
```bash
# Start backend
cd backend
uvicorn src.main:app --reload --port 8000

# Start frontend (new terminal)
cd frontend
npm start
```

## Development Patterns

### Adding New Analysis Features
1. **Add analysis function** in `analysis_service.py`
2. **Update synthesis logic** in `generate_holistic_conclusion()`
3. **Add frontend display** in `Analysis.js`
4. **Write tests** in `backend/tests/`

### Adding New Data Sources
1. **Create client class** in `backend/src/my_libs_py3/`
2. **Add integration** in `my_data.py`
3. **Update service layer** to use new source
4. **Add error handling** and fallback logic

### Frontend Component Patterns
- Use custom hooks for data fetching
- Implement loading states and error handling
- Store user preferences in localStorage
- Follow existing component structure

## Common Pitfalls to Avoid

### 1. Data Quality Issues
- **Always validate** data from external sources
- **Implement fallbacks** for missing or corrupted data
- **Log data quality issues** for monitoring
- **Test with edge cases** (empty responses, malformed data)

### 2. Async/Sync Mismatches
- **Backend services are async**, frontend calls are sync
- **Use proper await/await patterns** in backend
- **Handle connection lifecycle** for broker clients
- **Test error paths** for network failures

### 3. State Management
- **Avoid frontend state sync issues** with backend state
- **Use optimistic updates** sparingly
- **Implement proper error boundaries**
- **Test with concurrent users**

## Testing Strategy

### Backend Testing
```bash
# Run all tests
cd backend
pytest

# Run specific test file
pytest tests/test_analysis_service.py

# Run with coverage
pytest --cov=src tests/
```

### Frontend Testing
```bash
cd frontend
npm test
npm run test:coverage
```

### Integration Testing
- Test API endpoints with real data
- Test broker integration with paper accounts
- Test error handling and edge cases
- Test performance with large datasets

## Performance Considerations

### Backend Optimization
- **Cache expensive calculations** (IV surfaces, historical vol)
- **Use async I/O** for external API calls
- **Implement rate limiting** for data providers
- **Monitor memory usage** with large option chains

### Frontend Optimization
- **Implement virtual scrolling** for large datasets
- **Use React.memo** for expensive components
- **Debounce API calls** during user input
- **Optimize bundle size** with code splitting

## Security Considerations

### API Security
- **Validate all inputs** at service boundaries
- **Sanitize outputs** to prevent XSS
- **Implement rate limiting** for public endpoints
- **Use environment variables** for sensitive data

### Broker Integration
- **Never log credentials** or account details
- **Implement proper permissions** for order types
- **Add order size limits** as safety checks
- **Test with paper accounts** first

## Monitoring and Observability

### Logging
- **Use structured logging** with correlation IDs
- **Log performance metrics** for analysis functions
- **Monitor error rates** by endpoint
- **Set up alerts** for critical failures

### Metrics to Track
- **Analysis response times**
- **API error rates**
- **Data quality scores**
- **User engagement metrics**

## Future Enhancement Ideas

### High Priority
1. **Real-time streaming** for option prices
2. **Advanced order types** (conditional orders, OCO)
3. **Portfolio optimization** algorithms
4. **Backtesting engine** for strategy validation

### Medium Priority
1. **Machine learning** for signal generation
2. **Social sentiment** integration
3. **Advanced charting** and technical indicators
4. **Mobile app** development

### Infrastructure Improvements
1. **Microservices decomposition** for scalability
2. **Event-driven architecture** for real-time updates
3. **Database optimization** for historical data
4. **Cloud deployment** and auto-scaling

## Getting Help

### Codebase Resources
- **`methodology.md`** - Detailed analysis methodology
- **`new_plan.md`** - Technical implementation roadmap
- **`improved_methodology.md`** - Enhanced quantitative framework
- **Inline documentation** in key modules

### Development Tools
- **Use the AI agent** (`ai_agent/agent.py`) for code generation
- **Follow the style guide** in `CONVENTIONS.md`
- **Check architecture docs** in `architecture_and_plan.md`

Remember: The goal is to build a reliable, sophisticated trading intelligence system. Focus on incremental progress, thorough testing, and clear documentation.