# Artikate Studio Backend Developer Assessment

This repository contains the completed technical assessment for the Backend Developer role at Artikate Studio. It includes implementations and written engineering analyses demonstrating structured systems thinking, ORM optimization, and atomic rate-limiting logic.

## Project Architecture

The submission is organized into clear modules corresponding to the assessment sections:
**`section_1_diagnose/`**: Contains the reproduction and fixed Django database views illustrating an optimized N+1 query baseline along with profiler evidence.
**`section_2_queue/`**: Houses the standalone, rate-limited background job system built natively with Redis pipelines, alongside its concurrent verification test suite.
**`section_3_tenant/`**: Implements automatic multi-tenant ORM scoping safe for async executions via Python's `contextvars`, accompanied by dynamic data-isolation tests.
**`DESIGN.md`**: Architectural breakdown covering trade-offs and edge cases for the job queue and rate limiter.
**`ANSWERS.md`**: Complete set of written engineering explanations and architecture reviews for all sections.

---

## Quick Start & Installation

Follow these steps to configure a clean local environment and execute all test suites.

### 1. Prerequisites
Ensure you have Python 3.10+ installed and a local Redis server instance running on its default port (`6379`). 

*If using Docker, you can spin up Redis instantly via:*
```bash
docker run -d -p 6379:6379 --name artikate-redis redis:alpine

## 2. Setup Virtual Environment
```bash
# Create environment
python3 -m venv venv

# Activate environment (macOS/Linux)
source venv/bin/activate

# Activate environment (Windows Command Prompt)
# venv\Scripts\activate.bat

## 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt

## 4. Run All Tests
```bash
# To run all tests of section_2_queue and section_3_tenant
pytest section_2_queue/test_queue.py
pytest section_3_tenant/test_tenant.py
