# Admin Role Context Enforcement & Global Topic Plan

## Implementation Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Admin Navigation | ✅ DONE | `goto_admin_content`, `goto_admin_global` implemented |
| Phase 2: Global Topic | ✅ DONE | "global" removed from reserved keywords |
| Phase 3: Topic Visibility | ✅ DONE | `visible` field in Topic model |

---

## Completed Implementation

### Phase 1: Admin Role Context Enforcement ✅

**Intent Classification** (`intent_classifier.py`):
- Admin navigation patterns detect "take me to {topic} admin"
- Routes to `goto_admin_content` or `goto_admin_global`
- Few-shot examples guide LLM classification

**UI Action Node** (`ui_action_node.py`):
- New permission model uses `roles`, `topic_scoped`, `any_topic`, `global_only`
- Role context checks guide users to correct dashboard
- `_check_role_context_for_action()` handles navigation guidance

**Actions Synced**:
| Frontend (actions.ts) | Backend (ui_action_node.py) | Intent Classifier |
|-----------------------|-----------------------------|-------------------|
| `goto_admin_content` | ✅ | ✅ |
| `goto_admin_global` | ✅ | ✅ |
| ~~`goto_admin`~~ | ❌ Removed (redundant) | N/A |

### Phase 2: Global Topic ✅

**Topic Manager** (`topic_manager.py`):
- "global" is NOT in `RESERVED_KEYWORDS`
- Documented as "special topic for system-wide content"
- Can be created in database like any other topic

**Remaining**: Add deletion protection in `api/topics.py` (minor)

### Phase 3: Topic Visibility ✅

**Already Implemented**:
- `Topic.visible` field exists in model
- API returns `visible` field
- Admin can toggle visibility

---

## Permission Model (Implemented)

```python
UI_ACTION_PERMISSIONS = {
    # topic_scoped: requires role for CURRENT topic
    "save_draft": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},

    # any_topic: requires role on ANY topic (for navigation)
    "goto_analyst": {"section": "*", "roles": ["analyst"], "any_topic": True},

    # global_only: requires global:admin scope
    "goto_admin_global": {"section": "*", "roles": ["admin"], "global_only": True},
}
```

---

## Testing Checklist

- [x] Admin navigation patterns work in intent classifier
- [x] `goto_admin_content` navigates to topic admin
- [x] `goto_admin_global` requires global:admin
- [x] "global" can be used as topic slug
- [x] Permission model uses specific roles, not hierarchy
- [ ] Integration test: Reader → guided to analyst dashboard
- [ ] Integration test: Analyst → guided to editor for publish
