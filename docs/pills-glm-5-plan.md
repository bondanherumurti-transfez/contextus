# Dynamic Pills Enhancement Plan

## Overview

Transform static hardcoded pills into intelligent, context-aware conversation starters that adapt based on crawled content.

**Decisions:**
- **Approach:** Option C - Hybrid (backend-generated, frontend-rendered)
- **Pill count:** 3 pills
- **Behavior adaptation:** No (Phase 1 MVP only)

---

## Current State

| Aspect | Current Implementation |
|--------|----------------------|
| **Pill source** | Hardcoded in widget config |
| **Personalization** | None — same 3 pills for every business |
| **Backend integration** | Not used |

```javascript
// Current: Static, hardcoded
pills: ['How can you help?', 'Pricing & plans', 'How do I embed this?']
```

---

## Proposed Architecture

```
CRAWL FLOW:
1. User pastes URL
2. Backend crawls site
3. LLM extracts CompanyProfile + PillSuggestions
4. select_pills() picks best 3 pills
5. KnowledgeBase stored with suggested_pills
6. Widget loads pills from API

WIDGET FLOW:
1. Widget initialized with knowledgeBaseId
2. Fetches KB from /api/crawl/{job_id}
3. Renders suggested_pills (or fallback)
4. User sees contextual conversation starters
```

---

## Implementation Details

### 1. Backend Models

**File:** `backend/app/models.py`

```python
class PillSuggestions(BaseModel):
    """LLM-generated pill questions organized by category."""
    service_questions: list[str] = []
    gap_questions: list[str] = []
    industry_questions: list[str] = []


class CompanyProfile(BaseModel):
    """Extracted business information from crawled content."""
    name: str
    industry: str
    services: list[str]
    location: str | None = None
    contact: str | None = None
    summary: str
    gaps: list[str]
    pill_suggestions: PillSuggestions | None = None


class KnowledgeBase(BaseModel):
    """Complete knowledge base with company profile and suggested pills."""
    job_id: str
    status: Literal['crawling', 'analyzing', 'complete', 'failed']
    progress: str = ''
    pages_found: int = 0
    quality_tier: Literal['rich', 'thin', 'empty'] | None = None
    company_profile: CompanyProfile | None = None
    chunks: list[Chunk] = []
    suggested_pills: list[str] = []  # Final 3 pills to display
    created_at: int
```

---

### 2. LLM Prompt Update

**File:** `backend/app/services/llm.py`

```python
PROFILE_SYSTEM_PROMPT = """You are a business analyst. Extract company information and generate conversation starter questions.

Return a JSON object with this structure:
{
  "name": "Company name",
  "industry": "Industry or business type",
  "services": ["List of services/products they offer"],
  "location": "Location if found, or null",
  "contact": "Contact info (email, phone, WhatsApp) if found, or null",
  "summary": "2-3 sentence description of what the business does",
  "gaps": ["Important information missing from the website"],
  "pill_suggestions": {
    "service_questions": ["Question about main service?", "Question about secondary service?"],
    "gap_questions": ["Question that addresses missing info?"],
    "industry_questions": ["Industry-specific question?"]
  }
}

Rules for pill_suggestions:
- service_questions: 2-3 natural questions a potential customer would ask about their services
- gap_questions: 1-2 questions that help visitors get info missing from the website
- industry_questions: 1 question specific to their industry/niche
- Keep questions short (5-8 words)
- Make them conversational and friendly, not formal
- Questions should sound like something a real person would type

Example for a web design agency:
{
  "pill_suggestions": {
    "service_questions": ["What's included in web design?", "Do you offer SEO?"],
    "gap_questions": ["What are your pricing plans?"],
    "industry_questions": ["Do you work with small businesses?"]
  }
}
"""
```

---

### 3. Pill Selection Logic

**File:** `backend/app/services/llm.py`

```python
def select_pills(pill_suggestions: PillSuggestions | None, gaps: list[str]) -> list[str]:
    """
    Select the 3 best pills to display.
    
    Priority order:
    1. Gap questions (addresses missing info - high value for visitor)
    2. Service questions (main offerings)
    3. Industry questions (niche relevance)
    4. Fallback generic questions
    """
    if not pill_suggestions:
        return generate_fallback_pills()
    
    pills = []
    
    # 1 gap question (addresses missing website info)
    if pill_suggestions.gap_questions:
        pills.append(pill_suggestions.gap_questions[0])
    
    # 1-2 service questions
    remaining_slots = 3 - len(pills)
    pills.extend(pill_suggestions.service_questions[:remaining_slots])
    
    # Fill with industry question if needed
    if len(pills) < 3 and pill_suggestions.industry_questions:
        pills.append(pill_suggestions.industry_questions[0])
    
    # Fallback if still under 3
    while len(pills) < 3:
        fallbacks = generate_fallback_pills()
        for f in fallbacks:
            if f not in pills:
                pills.append(f)
                if len(pills) >= 3:
                    break
    
    return pills[:3]


def generate_fallback_pills() -> list[str]:
    """Generate default pills when LLM suggestions are unavailable."""
    return [
        "What services do you offer?",
        "How can you help me?",
        "How do I contact you?"
    ]
```

---

### 4. Router Integration

**File:** `backend/app/routers/crawl.py`

```python
async def run_crawl_job(job_id: str, url: str):
    """Background task to crawl, analyze, and generate profile."""
    try:
        kb = await get_knowledge_base(job_id)
        if not kb:
            return
        
        kb.status = "analyzing"
        kb.progress = "Analyzing website content..."
        await save_knowledge_base(job_id, kb)
        
        # Crawl site
        result = await crawl_site(url, on_progress)
        
        # Chunk content
        chunks = chunk_pages(result.pages)
        
        if chunks:
            kb.progress = "Generating company profile..."
            await save_knowledge_base(job_id, kb)
            
            # Generate profile with pills
            company_profile = generate_company_profile(chunks, url)
            kb.company_profile = company_profile
            kb.chunks = chunks
            kb.quality_tier = assess_quality_tier(chunks)
            
            # Generate suggested pills
            kb.suggested_pills = select_pills(
                company_profile.pill_suggestions,
                company_profile.gaps
            )
        
        kb.status = "complete"
        kb.progress = ""
        await save_knowledge_base(job_id, kb)
        
    except Exception as e:
        # ... error handling ...
```

---

### 5. Frontend Integration

**File:** `widget/widget.js`

```javascript
// Configuration
const cfg = Object.assign({
  root: document.getElementById('contextus-root') || document.body,
  name: 'contextus',
  greeting: 'Ask us anything...',
  lang: 'auto',
  transparent: false,
  dynamicHeight: false,
  pills: null,  // Will be loaded from API
  defaultPills: [
    'How can you help?',
    'What services do you offer?',
    'How do I contact you?'
  ],
  apiUrl: '',
  knowledgeBaseId: '',
}, config);

// State
const state = {
  // ... existing state ...
  pillsLoaded: false,
};

// Load pills from knowledge base
async function loadPillsFromKB() {
  if (!cfg.apiUrl || !cfg.knowledgeBaseId) {
    cfg.pills = cfg.defaultPills;
    state.pillsLoaded = true;
    return;
  }
  
  try {
    const res = await fetch(`${cfg.apiUrl}/api/crawl/${cfg.knowledgeBaseId}`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    
    const kb = await res.json();
    
    // Use API pills or fallback to defaults
    cfg.pills = (kb.suggested_pills && kb.suggested_pills.length > 0)
      ? kb.suggested_pills
      : cfg.defaultPills;
    
    state.pillsLoaded = true;
  } catch (error) {
    console.warn('Failed to load pills:', error);
    cfg.pills = cfg.defaultPills;
    state.pillsLoaded = true;
  }
}

// Render pills
function renderPills() {
  pillsContainer.innerHTML = '';
  
  if (!cfg.pills || cfg.pills.length === 0) {
    cfg.pills = cfg.defaultPills;
  }
  
  cfg.pills.forEach(label => {
    const pill = el('button', { className: 'ctx-pill', type: 'button' });
    pill.textContent = label;
    pill.addEventListener('click', () => sendMessage(label));
    pillsContainer.appendChild(pill);
  });
}

// Initialize widget
async function init() {
  // Load pills first (non-blocking for better UX)
  loadPillsFromKB().then(() => {
    renderPills();
  });
  
  // Render initial state
  render();
}

// Call init
init();
```

---

## Example Flow

### Scenario: User crawls a web design agency

**1. User pastes URL:** `https://acme-web-design.com`

**2. Backend crawls and analyzes:**
```
Pages found: 4 (Home, Services, About, Contact)
Services extracted: ["Web Design", "SEO", "Hosting"]
Gaps identified: ["pricing", "portfolio"]
Industry: Web Development
```

**3. LLM generates CompanyProfile:**
```json
{
  "name": "Acme Web Design",
  "industry": "Web Development",
  "services": ["Web Design", "SEO", "Hosting"],
  "location": "Jakarta, Indonesia",
  "contact": "hello@acme-web.com",
  "summary": "A web design agency specializing in small business websites.",
  "gaps": ["pricing", "portfolio"],
  "pill_suggestions": {
    "service_questions": [
      "What's included in web design?",
      "Do you offer SEO packages?"
    ],
    "gap_questions": [
      "What are your pricing plans?"
    ],
    "industry_questions": [
      "Do you work with small businesses?"
    ]
  }
}
```

**4. select_pills() outputs:**
```json
{
  "suggested_pills": [
    "What are your pricing plans?",
    "What's included in web design?",
    "Do you offer SEO packages?"
  ]
}
```

**5. Widget displays:**

```
┌─────────────────────────────────────┐
│  [C] contextus                      │
│                                     │
│  Hi! How can I help you today?      │
│                                     │
│  ┌─────────────────────────────────┐│
│  │ Ask us anything...          [→] ││
│  └─────────────────────────────────┘│
│                                     │
│  [What are your pricing plans?]     │
│  [What's included in web design?]   │
│  [Do you offer SEO packages?]       │
└─────────────────────────────────────┘
```

---

## Edge Cases & Fallbacks

| Scenario | Behavior | Reason |
|----------|----------|--------|
| API timeout | Use `defaultPills` | Graceful degradation |
| Empty `suggested_pills` | Use `defaultPills` | LLM returned nothing |
| Only 1 service | 1 service + 1 gap + 1 fallback | Fill remaining slots |
| No gaps identified | 2 service + 1 industry | Skip gap questions |
| Thin content (empty profile) | Use `defaultPills` | Not enough context |
| Widget without `knowledgeBaseId` | Use `defaultPills` | Static embed mode |
| `pill_suggestions` is null | Use `defaultPills` | Missing from response |

---

## Testing Checklist

| Test Case | Input | Expected Output |
|-----------|-------|-----------------|
| Rich site (3+ services) | E-commerce with many services | 3 contextual service/gap pills |
| Thin site (1 page) | Landing page only | Gap-focused pills |
| No services listed | Personal blog | Generic fallback pills |
| API unavailable | Network error | Default pills shown |
| Widget without KB ID | Static embed | Default pills shown |
| Partial pill_suggestions | Only service_questions | Service + fallback mix |
| Empty services array | `[]` | Gap/industry + fallbacks |
| LLM returns malformed JSON | Parse error | Default pills shown |

---

## Cost Impact

| Component | Additional Cost | Notes |
|-----------|-----------------|-------|
| LLM prompt tokens | +50-100 tokens | ~$0.0001 per crawl |
| API response size | +200-300 bytes | Negligible |
| Frontend JS | ~1KB added | Pill loading logic |
| Redis storage | +100 bytes | Pills in KB object |

**Verdict:** Minimal cost increase with significant UX improvement.

---

## Implementation Checklist

- [ ] Update `backend/app/models.py`
  - [ ] Add `PillSuggestions` model
  - [ ] Update `CompanyProfile` with `pill_suggestions` field
  - [ ] Update `KnowledgeBase` with `suggested_pills` field

- [ ] Update `backend/app/services/llm.py`
  - [ ] Update `PROFILE_SYSTEM_PROMPT` with pill generation instructions
  - [ ] Add `select_pills()` function
  - [ ] Add `generate_fallback_pills()` function
  - [ ] Update `generate_company_profile()` to parse pill_suggestions

- [ ] Update `backend/app/routers/crawl.py`
  - [ ] Call `select_pills()` after profile generation
  - [ ] Store `suggested_pills` in KnowledgeBase

- [ ] Update `widget/widget.js`
  - [ ] Add `defaultPills` config option
  - [ ] Add `loadPillsFromKB()` async function
  - [ ] Add `renderPills()` function
  - [ ] Update initialization to load pills

- [ ] Update `backend/tests/test_plan.md`
  - [ ] Add pill generation tests
  - [ ] Add fallback tests

- [ ] Manual testing
  - [ ] Test with rich content site
  - [ ] Test with thin content site
  - [ ] Test with API unavailable
  - [ ] Test fallback behavior

---

## Future Enhancements (Out of Scope for MVP)

### Phase 2: Behavior-Based Pill Adaptation

| Trigger | Behavior |
|---------|----------|
| User ignores pills for 10s | Highlight/animate first pill |
| User asks about pricing | Hide pricing pill, show follow-up |
| User mentions specific service | Show related service pills |
| Conversation goes idle | Show "Still interested in...?" pills |
| Contact captured | Show "Best time to call?" pill |

### Phase 3: A/B Testing

- Track pill click rates
- Test different phrasings
- Optimize for engagement

---

## Related Documents

- `docs/backend-plan.md` — Overall backend architecture
- `backend/tests/test_plan.md` — Testing strategy
- `widget/widget.js` — Current widget implementation
