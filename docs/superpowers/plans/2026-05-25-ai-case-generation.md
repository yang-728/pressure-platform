# AI Case Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent "用例生成" module that can create AI generation tasks, generate JMeter JMX artifacts from Markdown through Codex CLI, and support preview/download/log review.

**Architecture:** The backend owns a generic AI generation task model and artifact model, with the first generation type limited to `jmeter_jmx`. Generation runs asynchronously after task creation, stores input/output files under a configurable work directory, validates JMX XML before exposing downloads, and keeps task logs for troubleshooting. The frontend adds a dedicated route, sidebar entry, API wrapper, and Element Plus page based on the approved mockup.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Pydantic, pytest/httpx, Vue 3, Element Plus, Vite.

---

### Task 1: Backend Data Model And API Contract

**Files:**
- Create: `api/app/models/ai_generation.py`
- Create: `api/app/crud/ai_generation.py`
- Create: `api/app/schemas/ai_generation.py`
- Create: `api/tests/test_ai_generation.py`
- Modify: `api/app/models/__init__.py`

- [x] Write failing API tests for task creation, artifact listing, preview, download, log access, delete behavior, and invalid JMX failure.
- [x] Add ORM models for `mysterious_ai_generation_task` and `mysterious_ai_generation_artifact`.
- [x] Add CRUD helpers for filtered task paging and artifact lookup.
- [x] Add Pydantic schemas with camelCase output.

### Task 2: Backend Service And Codex Runner

**Files:**
- Create: `api/app/services/ai_generation.py`
- Create: `api/app/api/v1/ai_generation.py`
- Modify: `api/app/main.py`
- Modify: `api/app/db/schema.py`
- Modify: `api/app/core/config_catalog.py`
- Modify: `docker/init.sql`

- [x] Implement `POST /ai-generation/tasks` as multipart upload with generation params.
- [x] Store uploaded Markdown under `AI_GENERATION_WORK_DIR`.
- [x] Run Codex CLI in a background task with configurable timeout and binary path.
- [x] Validate generated JMX XML before creating artifacts.
- [x] Provide list/detail/log/artifacts/view/download/delete endpoints.
- [x] Add upgrade table creation for deployments without Alembic.
- [x] Add config catalog entries for AI generation settings.

### Task 3: Frontend API And Page

**Files:**
- Create: `src/api/aiGeneration.ts`
- Create: `src/views/caseGeneration.vue`
- Modify: `src/router/index.ts`
- Modify: `src/components/sidebar.vue`

- [x] Add API wrapper for task list/create/delete/log/artifact preview/download.
- [x] Add sidebar entry and route for `/case-generation`.
- [x] Build the task list, filters, metrics, new-task drawer, preview drawer, and log drawer.
- [x] Keep generation output manual-review only; do not auto-bind generated JMX to a testcase.

### Task 4: Verification

**Files:**
- Backend and frontend affected files.

- [x] Run focused backend tests for AI generation.
- [x] Run broader backend regression tests touching config and existing JMX behavior.
- [x] Run backend compile check.
- [x] Run frontend build.
- [x] Run `git diff --check` in both repositories.

Note: the broader command including `api/tests/test_testcase_run.py` still has existing failures around `/testcase/run/{id}` GET/POST expectations and async JMeter completion. These failures are outside the AI generation module; the focused AI generation/config/JMX tests passed.
