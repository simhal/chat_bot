# Topic Entitlement Filtering Plan

## Implementation Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: API Client Function | ⏳ PENDING | Add `getEntitledTopics(role)` to api.ts |
| Phase 2: Reader Section | ⏳ PENDING | Use entitled topics endpoint |
| Phase 3: Backend Filter | ⏳ PENDING | Add `visible=True` filter for reader |
| Phase 4-6: Other Sections | ⏳ PENDING | Update analyst/editor/admin sections |

---

## Overview

Ensure topics displayed in different sections are filtered server-side based on:
1. **Visibility** (`visible=True` for reader section)
2. **User entitlements** (user must have appropriate role for each topic)

## Current State

### Backend ✅
- `/api/topics/entitled?role=reader|analyst|editor|admin` endpoint exists
- Returns topics user is entitled to at the specified role level
- Handles `global:admin` scope (returns all topics)

### Frontend ⏳
- Currently loads all topics and filters client-side
- Missing `getEntitledTopics(role)` API function

---

## Remaining Implementation

### 1. Add API Client Function

**File: `frontend/src/lib/api.ts`**

```typescript
export async function getEntitledTopics(
    role: 'reader' | 'analyst' | 'editor' | 'admin'
): Promise<Topic[]> {
    return apiRequest(`/api/topics/entitled?role=${role}`);
}
```

### 2. Update Frontend Sections

| Section | Current | Change To |
|---------|---------|-----------|
| Reader (`+page.svelte`) | `getTopics(true, true)` | `getEntitledTopics('reader')` |
| Analyst | `getTopics()` + client filter | `getEntitledTopics('analyst')` |
| Editor | `getTopics()` + client filter | `getEntitledTopics('editor')` |
| Admin | `getTopics()` + client filter | `getEntitledTopics('admin')` |

### 3. Update Backend

**File: `backend/api/topics.py`** - `list_entitled_topics()`

Add visibility filter for reader role:
```python
if role == "reader":
    query = query.filter(Topic.visible == True)
```

---

## Benefits

1. **Security**: Server-side filtering based on actual entitlements
2. **Consistency**: All sections use same entitlement endpoint
3. **Reduced client code**: Remove duplicate scope-checking logic
4. **Performance**: Smaller payloads (only entitled topics returned)
